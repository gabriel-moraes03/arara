package br.arara.adapters.web;

import br.arara.adapters.persistence.AnalysisRepository;
import br.arara.adapters.persistence.AnalysisRepository.Analysis;
import br.arara.adapters.storage.AnalysisStorage;
import br.arara.application.AnalysisService;
import br.arara.application.RegionCatalog;
import br.arara.application.RegionMonitor;
import br.arara.adapters.persistence.ObservationRepository;
import br.arara.application.Quality;
import br.arara.application.SceneService;
import br.arara.config.AraraProperties;
import br.arara.domain.Geo;
import br.arara.domain.JobStatus;
import br.arara.domain.Scene;
import br.arara.domain.SceneGroup;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.TimeUnit;
import org.locationtech.jts.geom.Geometry;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/arara")
public class AraraController {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final SceneService scenes;
    private final AnalysisService analyses;
    private final AnalysisRepository repo;
    private final AnalysisStorage storage;
    private final AraraProperties props;
    private final RegionMonitor monitor;
    private final RegionCatalog regions;
    private final ObservationRepository observations;

    public AraraController(SceneService scenes, AnalysisService analyses, AnalysisRepository repo,
                           AnalysisStorage storage, AraraProperties props, RegionMonitor monitor,
                           RegionCatalog regions, ObservationRepository observations) {
        this.monitor = monitor;
        this.regions = regions;
        this.observations = observations;
        this.scenes = scenes;
        this.analyses = analyses;
        this.repo = repo;
        this.storage = storage;
        this.props = props;
    }

    /** O que este servidor consegue fazer agora (sem expor credencial alguma). */
    @GetMapping("/config")
    public Map<String, Object> config() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("algorithm_version", props.algorithmVersion());
        m.put("aoi_max_km2", props.aoiMaxKm2());
        m.put("max_scenes", props.maxScenes());
        m.put("retention_days", props.retentionDays());
        m.put("on_demand_available", props.earthdataConfigured());
        if (!props.earthdataConfigured()) {
            m.put("on_demand_reason", "servidor sem credenciais Earthdata (EARTHDATA_USERNAME / EARTHDATA_PASSWORD): "
                    + "o catálogo funciona, mas novas análises ficam indisponíveis");
        }
        return m;
    }

    /** Monitor das regiões: último relatório (o que foi reanalisado, o que está em dia). */
    @GetMapping("/monitor")
    public Map<String, Object> monitorStatus() {
        return monitor.status();
    }

    /** Roda o monitor agora (consulta o catálogo de cada região e pede as análises com passagem nova). */
    @PostMapping("/monitor/run")
    public Map<String, Object> monitorRun() {
        monitor.check(java.time.LocalDate.now());
        return monitor.status();
    }

    /**
     * Histórico de uma região monitorada: uma linha por passagem, a medição mais recente de cada data,
     * vindo do banco (sobrevive à limpeza dos arquivos e às análises superadas). ?format=csv para planilha.
     */
    @GetMapping("/regions/{id}/history")
    public ResponseEntity<?> regionHistory(@PathVariable String id, @RequestParam(defaultValue = "json") String format) throws IOException {
        var r = regions.find(id).orElseThrow(() -> new NoSuchElementException("região não encontrada"));
        double[] b = r.bbox();
        var rows = observations.history(r.name(), b[0], b[1], b[2], b[3]);
        if ("csv".equalsIgnoreCase(format)) {
            StringBuilder csv = new StringBuilder("date,water_km2,flood_km2,flooded_vegetation_km2,reference_date,rain_3d_mm,rain_7d_mm,"
                    + "wind,confidence,confidence_reasons,quality,threshold_db,crid,granule,algorithm_version,analysis_id\n");
            for (var o : rows) {
                csv.append(String.join(",", o.passDate(), s(o.waterKm2()), s(o.floodKm2()), s(o.floodedVegetationKm2()), s(o.referenceDate()),
                        s(o.rain3dMm()), s(o.rain7dMm()), s(o.wind()), s(o.confidence()), quote(o.confidenceReasons()), s(o.quality()),
                        s(o.thresholdDb()), s(o.crid()), s(o.granule()), s(o.algorithmVersion()), o.analysisId())).append('\n');
            }
            return ResponseEntity.ok().contentType(new MediaType("text", "csv", java.nio.charset.StandardCharsets.UTF_8))
                    .header("Content-Disposition", "attachment; filename=\"arara_" + r.id() + "_historico.csv\"").body(csv.toString());
        }
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("region", r.id());
        m.put("name", r.name());
        m.put("source", "banco do Arara (tabela observation): a medição mais recente de cada passagem");
        m.put("count", rows.size());
        m.put("observations", rows);
        return ResponseEntity.ok(m);
    }

    private static String s(Object v) {
        return v == null ? "" : v.toString();
    }

    private static String quote(String v) {
        return v == null ? "" : "\"" + v.replace("\"", "\"\"") + "\"";
    }

    @GetMapping("/scenes")
    public Map<String, Object> scenes(@RequestParam(required = false) String bbox, @RequestParam(required = false) String aoi,
                                      @RequestParam(required = false) String start, @RequestParam(required = false) String end,
                                      @RequestParam(required = false) String maturity) {
        Geometry geom = area(bbox, aoi);
        List<Scene> found = SceneService.filter(scenes.search(Geo.wkt(geom), start, end), maturity);
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("status", "ok");
        m.put("source", "ASF DAAC Search API (NISAR L2 GCOV)");
        m.put("count", found.size());
        m.put("groups", SceneService.group(found, geom).stream().map(AraraController::groupView).toList());
        m.put("scenes", found);
        return m;
    }

    @GetMapping("/coverage")
    public Map<String, Object> coverage(@RequestParam(required = false) String bbox, @RequestParam(required = false) String aoi,
                                        @RequestParam(required = false) String start, @RequestParam(required = false) String end,
                                        @RequestParam(required = false) String maturity) {
        Geometry geom = area(bbox, aoi);
        List<SceneGroup> groups = SceneService.group(SceneService.filter(scenes.search(Geo.wkt(geom), start, end), maturity), geom);
        Map<String, Object> m = new LinkedHashMap<>();
        boolean ok = !groups.isEmpty() && groups.get(0).eligible();
        m.put("status", ok ? "available" : "unavailable");
        if (!ok) {
            m.put("reason", groups.isEmpty() ? "nenhuma cena NISAR GCOV intersecta a área no período"
                    : String.format("nenhuma geometria cobre %.0f%% da área (a melhor cobre %.0f%%); reduza ou desloque a área",
                    SceneService.MIN_COVERAGE * 100, groups.stream().mapToDouble(SceneGroup::aoiCoverage).max().orElse(0) * 100));
        } else {
            m.put("best_group", groupView(groups.get(0)));
        }
        m.put("area_km2", Math.round(Geo.areaKm2(geom) * 10) / 10.0);
        m.put("area_within_limit", Geo.areaKm2(geom) <= props.aoiMaxKm2());
        m.put("min_coverage", SceneService.MIN_COVERAGE);
        m.put("groups", groups.stream().map(AraraController::groupView).toList());
        return m;
    }

    @PostMapping("/analysis")
    public ResponseEntity<Map<String, Object>> create(@RequestBody AnalysisService.Request rq) {
        var s = analyses.submit(rq);
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("analysis_id", s.analysisId());
        m.put("job_id", s.jobId());
        m.put("status", s.status().api());
        m.put("reused", s.reused());
        return ResponseEntity.status(s.status() == JobStatus.COMPLETED ? HttpStatus.OK : HttpStatus.ACCEPTED).body(m);
    }

    @GetMapping("/jobs/{id}")
    public Map<String, Object> job(@PathVariable String id) {
        var j = repo.findJob(id).orElseThrow(() -> new NoSuchElementException("job não encontrado"));
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("job_id", j.id());
        m.put("analysis_id", j.analysisId());
        m.put("status", j.status().api());
        m.put("stage", j.stage());
        m.put("progress", j.progress());
        m.put("message", j.message());
        if (j.reason() != null) m.put("reason", j.reason());
        m.put("created_at", j.createdAt().toString());
        m.put("updated_at", j.updatedAt().toString());
        return m;
    }

    @GetMapping("/analyses")
    public Map<String, Object> list(@RequestParam(required = false) String status,
                                    @RequestParam(name = "include_superseded", defaultValue = "false") boolean includeSuperseded) {
        JobStatus st = status == null || status.isBlank() ? null : JobStatus.of(status);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Analysis a : repo.list(st)) {
            if (includeSuperseded || a.supersededBy() == null) items.add(card(a));   // superada: só pelo id
        }
        return Map.of("count", items.size(), "analyses", items);
    }

    @GetMapping("/analyses/{id}")
    public ObjectNode analysis(@PathVariable String id) throws IOException {
        Analysis a = find(id);
        ObjectNode out = JSON.valueToTree(card(a));
        var result = storage.file(id, "result.json");
        if (a.status() == JobStatus.COMPLETED && result.isPresent()) {
            ObjectNode r = Quality.apply((ObjectNode) JSON.readTree(result.get().toFile()));
            r.remove("status");
            out.setAll(r);
            out.put("layers_url", "/api/arara/analyses/" + id + "/layers");
        }
        return out;
    }

    @GetMapping("/analyses/{id}/metrics")
    public ResponseEntity<?> metrics(@PathVariable String id, @RequestParam(defaultValue = "json") String format) throws IOException {
        find(id);
        if ("csv".equalsIgnoreCase(format)) {
            Path csv = storage.file(id, "metrics.csv").orElseThrow(() -> new NoSuchElementException("análise sem métricas"));
            String body = Files.readString(csv);
            var result = storage.file(id, "result.json");
            if (result.isPresent()) {
                JsonNode r = JSON.readTree(result.get().toFile());
                if (Quality.NO_RELIABLE_WATER.equals(Quality.of(r).quality())) body = scenesOnlyCsv(r);   // sem área de água
            }
            return ResponseEntity.ok().contentType(new MediaType("text", "csv", java.nio.charset.StandardCharsets.UTF_8))
                    .header("Content-Disposition", "attachment; filename=\"arara_" + id + ".csv\"").body(body);
        }
        Path json = storage.file(id, "metrics.json").orElseThrow(() -> new NoSuchElementException("análise sem métricas"));
        return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(Quality.apply((ObjectNode) JSON.readTree(json.toFile())));
    }

    @GetMapping("/analyses/{id}/layers")
    public ObjectNode layers(@PathVariable String id) throws IOException {
        find(id);
        Path result = storage.file(id, "result.json").orElseThrow(() -> new NoSuchElementException("análise sem camadas"));
        ObjectNode out = JSON.createObjectNode();
        out.put("analysis_id", id);
        var arr = out.putArray("layers");
        for (JsonNode l : JSON.readTree(result.toFile()).path("layers")) {
            ObjectNode o = l.deepCopy();
            String layerId = id + "-" + l.path("id").asText();
            o.put("layer_id", layerId);
            o.put("png", "/api/arara/analyses/" + id + "/png/" + l.path("id").asText() + ".png");
            o.put("tiles", "/api/arara/tiles/" + layerId + "/{z}/{x}/{y}.png");
            arr.add(o);
        }
        return out;
    }

    @GetMapping("/analyses/{id}/sources")
    public JsonNode sources(@PathVariable String id) throws IOException {
        find(id);
        return JSON.readTree(storage.file(id, "sources.json").orElseThrow(() -> new NoSuchElementException("análise sem fontes")).toFile());
    }

    @GetMapping("/analyses/{id}/png/{layer}.png")
    public ResponseEntity<Resource> png(@PathVariable String id, @PathVariable String layer) {
        if (!AnalysisStorage.validId(id) || !AnalysisStorage.validName(layer)) throw new NoSuchElementException("camada não encontrada");
        return image(storage.file(id, "png", layer + ".png").orElseThrow(() -> new NoSuchElementException("camada não encontrada")));
    }

    /** layer_id = {id da análise}-{camada}. Tile que não existe (fora da área ou vazio) responde 404. */
    @GetMapping("/tiles/{layerId}/{z}/{x}/{y}.png")
    public ResponseEntity<Resource> tile(@PathVariable String layerId, @PathVariable int z, @PathVariable int x, @PathVariable int y) {
        int cut = layerId.indexOf('-');
        if (cut < 1) throw new NoSuchElementException("camada não encontrada");
        String id = layerId.substring(0, cut), layer = layerId.substring(cut + 1);
        if (!AnalysisStorage.validId(id) || !AnalysisStorage.validName(layer)) throw new NoSuchElementException("camada não encontrada");
        return image(storage.file(id, "tiles", layer, String.valueOf(z), String.valueOf(x), y + ".png")
                .orElseThrow(() -> new NoSuchElementException("tile não encontrado")));
    }

    /** CSV de uma análise sem água confiável: só as cenas usadas, nenhum número de água. */
    static String scenesOnlyCsv(JsonNode r) {
        StringBuilder sb = new StringBuilder("date,quality,margin_blocks,valid_fraction_aoi,crid,granule\n");
        for (JsonNode d : r.path("dates")) {
            sb.append(d.path("date").asText()).append(",no_reliable_water,").append(d.path("margin_blocks").asText(""))
                    .append(',').append(d.path("valid_fraction_aoi").asText("")).append(',').append(d.path("crid").asText(""))
                    .append(',').append(d.path("granule").asText("")).append('\n');
        }
        return sb.toString();
    }

    private static ResponseEntity<Resource> image(Path p) {
        return ResponseEntity.ok().contentType(MediaType.IMAGE_PNG).cacheControl(CacheControl.maxAge(1, TimeUnit.HOURS))
                .body(new FileSystemResource(p));
    }

    private Analysis find(String id) {
        if (!AnalysisStorage.validId(id)) throw new NoSuchElementException("análise não encontrada");
        return repo.find(id).orElseThrow(() -> new NoSuchElementException("análise não encontrada"));
    }

    private Geometry area(String bbox, String aoi) {
        try {
            if (aoi != null && !aoi.isBlank()) return Geo.fromGeoJson(JSON.readTree(aoi));
        } catch (IOException e) {
            throw new IllegalArgumentException("'aoi' não é um GeoJSON válido");
        }
        if (bbox != null && !bbox.isBlank()) return Geo.fromBbox(bbox);
        throw new IllegalArgumentException("informe a área: 'bbox' (oeste,sul,leste,norte) ou 'aoi' (GeoJSON)");
    }

    private Map<String, Object> card(Analysis a) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("analysis_id", a.id());
        m.put("name", a.name());
        m.put("status", a.status().api());
        if (a.reason() != null) m.put("reason", a.reason());
        m.put("bbox", List.of(a.west(), a.south(), a.east(), a.north()));
        m.put("center", List.of((a.west() + a.east()) / 2, (a.south() + a.north()) / 2));
        m.put("area_km2", Math.round(a.areaKm2() * 10) / 10.0);
        m.put("start", a.startDate());
        m.put("end", a.endDate());
        m.put("algorithm_version", a.algorithmVersion());
        if (a.supersededBy() != null) m.put("superseded_by", a.supersededBy());
        m.put("created_at", a.createdAt().toString());
        m.put("updated_at", a.updatedAt().toString());
        if (a.summaryJson() != null) {
            try {
                JsonNode s = JSON.readTree(a.summaryJson());
                var result = storage.file(a.id(), "result.json");
                if (!s.has("quality") && result.isPresent()) s = AnalysisService.summary(JSON.readTree(result.get().toFile()));
                m.put("summary", s);
                m.put("quality", s.path("quality").asText(Quality.EXPERIMENTAL));
            } catch (IOException ignored) {
                // resumo ilegível: o card sai sem ele
            }
        }
        return m;
    }

    static Map<String, Object> groupView(SceneGroup g) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", g.id());
        m.put("collection", g.collection());
        m.put("maturity", g.maturity());
        m.put("track", g.track());
        m.put("direction", g.direction());
        m.put("frame", g.frame());
        m.put("n_dates", g.nDates());
        m.put("dates", g.dates());
        m.put("first_date", g.firstDate());
        m.put("last_date", g.lastDate());
        m.put("aoi_coverage", g.aoiCoverage());
        m.put("crids", g.crids());
        m.put("polarizations", g.polarizations());
        m.put("dates_with_hv", g.datesWithHv());
        m.put("eligible", g.eligible());
        return m;
    }
}
