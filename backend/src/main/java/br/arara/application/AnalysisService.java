package br.arara.application;

import br.arara.adapters.persistence.AnalysisRepository;
import br.arara.adapters.persistence.AnalysisRepository.Analysis;
import br.arara.adapters.persistence.AnalysisRepository.Job;
import br.arara.adapters.pipeline.PipelineRunner;
import br.arara.adapters.storage.AnalysisStorage;
import br.arara.config.AraraProperties;
import br.arara.domain.AnalysisId;
import br.arara.domain.Geo;
import br.arara.domain.JobStatus;
import br.arara.domain.Unavailable;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.annotation.PreDestroy;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.locationtech.jts.geom.Envelope;
import org.locationtech.jts.geom.Geometry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/** Pedidos de análise, fila (um job pesado por vez), retomada de órfãos e limpeza de derivados. */
@Service
public class AnalysisService {
    private static final Logger log = LoggerFactory.getLogger(AnalysisService.class);
    private static final ObjectMapper JSON = new ObjectMapper();

    public record Request(String name, JsonNode aoi, String bbox, String start, String end, String groupId, String maturity) {
    }

    public record Submitted(String analysisId, String jobId, JobStatus status, boolean reused) {
    }

    private final AnalysisRepository repo;
    private final AnalysisStorage storage;
    private final PipelineRunner pipeline;
    private final AraraProperties props;
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "arara-pipeline");
        t.setDaemon(true);
        return t;
    });

    public AnalysisService(AnalysisRepository repo, AnalysisStorage storage, PipelineRunner pipeline, AraraProperties props) {
        this.repo = repo;
        this.storage = storage;
        this.pipeline = pipeline;
        this.props = props;
    }

    public synchronized Submitted submit(Request rq) {
        Geometry aoi = rq.aoi() != null && !rq.aoi().isNull() ? Geo.fromGeoJson(rq.aoi())
                : rq.bbox() != null ? Geo.fromBbox(rq.bbox()) : null;
        if (aoi == null) throw new IllegalArgumentException("informe a área: 'aoi' (GeoJSON) ou 'bbox' (oeste,sul,leste,norte)");
        LocalDate start = date(rq.start(), "start"), end = date(rq.end(), "end");
        if (start != null && end != null && start.isAfter(end)) throw new IllegalArgumentException("'start' depois de 'end'");
        double km2 = Geo.areaKm2(aoi);
        if (km2 > props.aoiMaxKm2()) {
            throw new IllegalArgumentException(String.format("área de %.0f km² acima do limite de %.0f km²; desenhe uma área menor",
                    km2, props.aoiMaxKm2()));
        }
        String hash = AnalysisId.hash(aoi, rq.start(), rq.end(), rq.groupId(), rq.maturity(), props.algorithmVersion());
        String id = AnalysisId.shortId(hash);

        var existing = repo.find(id);
        if (existing.isPresent() && existing.get().status() == JobStatus.COMPLETED && storage.file(id, "result.json").isPresent()) {
            return new Submitted(id, null, JobStatus.COMPLETED, true);
        }
        var active = repo.activeJob(id);
        if (active.isPresent()) return new Submitted(id, active.get().id(), active.get().status(), true);

        if (storage.usedBytes() > props.diskLimitMb() * 1024 * 1024) {
            cleanup();
            if (storage.usedBytes() > props.diskLimitMb() * 1024 * 1024) {
                throw new Unavailable("limite de disco das análises atingido (" + props.diskLimitMb() + " MB); tente mais tarde");
            }
        }
        Instant now = Instant.now();
        Envelope e = aoi.getEnvelopeInternal();
        String geojson = rq.aoi() != null && !rq.aoi().isNull() ? geometryOf(rq.aoi()).toString() : bboxPolygon(e).toString();
        repo.upsert(new Analysis(id, hash, clean(rq.name()), JobStatus.QUEUED, geojson, e.getMinX(), e.getMinY(), e.getMaxX(), e.getMaxY(),
                km2, rq.start(), rq.end(), blank(rq.groupId()), blank(rq.maturity()), props.algorithmVersion(),
                null, null, null, now, now, null));
        Job job = new Job(UUID.randomUUID().toString(), id, JobStatus.QUEUED, "queued", 0, "na fila", null, now, now);
        repo.insert(job);
        worker.submit(() -> run(job.id(), id));
        return new Submitted(id, job.id(), JobStatus.QUEUED, false);
    }

    void run(String jobId, String id) {
        Analysis a = repo.find(id).orElse(null);
        if (a == null) return;
        JobStatus status;
        String reason = null;
        JsonNode result = null;
        try {
            Path out = storage.prepare(id);
            ObjectNode spec = JSON.createObjectNode();
            spec.put("analysis_id", id);
            spec.set("aoi", JSON.readTree(a.aoiGeojson()));
            if (a.startDate() != null) spec.put("start", a.startDate());
            if (a.endDate() != null) spec.put("end", a.endDate());
            if (a.groupId() != null) spec.put("group_id", a.groupId());
            if (a.maturity() != null) spec.put("maturity", a.maturity());
            spec.put("max_scenes", props.maxScenes());
            Path specFile = out.resolve("spec.json");
            Files.writeString(specFile, spec.toString());
            repo.progress(jobId, JobStatus.DOWNLOADING, "discover", 0, "iniciando");
            repo.setStatus(id, JobStatus.DOWNLOADING);
            result = pipeline.run(specFile, out, (stage, progress, message) -> {
                if ("unavailable".equals(stage) || "failed".equals(stage)) return;
                repo.progress(jobId, JobStatus.ofStage(stage), stage, progress, message);
            });
            status = switch (result.path("status").asText("failed")) {
                case "completed" -> JobStatus.COMPLETED;
                case "unavailable" -> JobStatus.UNAVAILABLE;
                default -> JobStatus.FAILED;
            };
            reason = result.hasNonNull("reason") ? result.get("reason").asText() : null;
        } catch (Exception ex) {
            log.error("job {} falhou: {}", jobId, ex.toString());
            status = JobStatus.FAILED;
            reason = ex.getClass().getSimpleName() + ": " + ex.getMessage();
        }
        if (status != JobStatus.COMPLETED) {
            storage.delete(id);                       // nada de derivado parcial fica no disco
        }
        repo.finish(id, status, reason, status == JobStatus.COMPLETED ? result.path("experimental").asBoolean(false) : null,
                status == JobStatus.COMPLETED ? summary(result).toString() : null);
        repo.finishJob(jobId, status, reason);
    }

    /** Resumo para os cards do globo (só números que a pipeline mediu). */
    static ObjectNode summary(JsonNode r) {
        ObjectNode s = JSON.createObjectNode();
        JsonNode dates = r.path("dates");
        s.put("n_dates", dates.size());
        if (dates.size() > 0) {
            JsonNode first = dates.get(0), last = dates.get(dates.size() - 1);
            s.put("first_date", first.path("date").asText());
            s.put("last_date", last.path("date").asText());
            s.set("water_km2_first", first.path("water_km2"));
            s.set("water_km2_last", last.path("water_km2"));
            s.set("water_pct_last", last.path("water_pct"));
        }
        ArrayNode wind = s.putArray("wind_dates");
        dates.forEach(d -> {
            if (d.path("suspeita_vento").asBoolean(false)) wind.add(d.path("date").asText());
        });
        if (r.hasNonNull("comparison")) s.set("net_change_ha", r.get("comparison").path("net_change_ha"));
        s.put("validation_status", r.path("optical_validation").path("status").asText("not_optically_validated"));
        if (r.path("optical_validation").hasNonNull("mean_iou")) s.set("mean_iou", r.get("optical_validation").get("mean_iou"));
        s.set("group", r.path("group"));
        s.put("sensor", r.path("sensor").asText("NISAR"));
        s.put("experimental", r.path("experimental").asBoolean(false));
        return s;
    }

    /** Ao reiniciar: jobs que estavam na fila ou rodando voltam para a fila (o processo filho morreu junto). */
    @EventListener(ApplicationReadyEvent.class)
    public void recoverOrphans() {
        for (Job j : repo.activeJobs()) {
            log.info("retomando job órfão {} ({})", j.id(), j.status());
            repo.progress(j.id(), JobStatus.QUEUED, "queued", 0, "retomado após reinício do servidor");
            repo.setStatus(j.analysisId(), JobStatus.QUEUED);
            worker.submit(() -> run(j.id(), j.analysisId()));
        }
    }

    /** Derivados com mais de N dias (padrão 7) são apagados; a análise pode ser refeita a qualquer hora. */
    @Scheduled(fixedDelay = 6 * 60 * 60 * 1000L, initialDelay = 60 * 1000L)
    public void cleanup() {
        Instant limit = Instant.now().minus(Duration.ofDays(props.retentionDays()));
        for (Analysis a : repo.olderThan(limit)) {
            if (a.status().active()) continue;
            log.info("limpando análise {} (mais de {} dias)", a.id(), props.retentionDays());
            storage.delete(a.id());
            repo.delete(a.id());
        }
    }

    @PreDestroy
    void stop() {
        worker.shutdownNow();
    }

    private static LocalDate date(String s, String field) {
        if (s == null || s.isBlank()) return null;
        try {
            return LocalDate.parse(s);
        } catch (DateTimeParseException e) {
            throw new IllegalArgumentException("'" + field + "' deve ser AAAA-MM-DD");
        }
    }

    private static JsonNode geometryOf(JsonNode n) {
        return switch (n.path("type").asText()) {
            case "Feature" -> n.get("geometry");
            case "FeatureCollection" -> geometryOf(n.get("features").get(0));
            default -> n;
        };
    }

    private static ObjectNode bboxPolygon(Envelope e) {
        ObjectNode g = JSON.createObjectNode();
        g.put("type", "Polygon");
        ArrayNode ring = g.putArray("coordinates").addArray();
        double[][] pts = {{e.getMinX(), e.getMinY()}, {e.getMaxX(), e.getMinY()}, {e.getMaxX(), e.getMaxY()},
                {e.getMinX(), e.getMaxY()}, {e.getMinX(), e.getMinY()}};
        for (double[] p : pts) ring.addArray().add(p[0]).add(p[1]);
        return g;
    }

    private static String blank(String s) {
        return s == null || s.isBlank() ? null : s.trim();
    }

    private static String clean(String s) {
        if (s == null || s.isBlank()) return null;
        String t = s.replaceAll("[<>\\p{Cntrl}]", "").trim();
        return t.length() > 120 ? t.substring(0, 120) : t;
    }
}
