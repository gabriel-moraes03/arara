package br.arara.application;

import br.arara.adapters.persistence.AnalysisRepository;
import br.arara.adapters.persistence.AnalysisRepository.Analysis;
import br.arara.config.AraraProperties;
import br.arara.application.RegionCatalog.Region;
import br.arara.config.MonitorProperties;
import br.arara.domain.Geo;
import br.arara.domain.JobStatus;
import br.arara.domain.SceneGroup;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import org.locationtech.jts.geom.Geometry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Monitor das regiões (frontend/globe/regioes.json): de tempos em tempos consulta o catálogo do NISAR e,
 * quando há passagem mais nova que a última análise da região, pede a análise de novo até hoje. Com o
 * cache por passagem da pipeline, só a passagem nova é lida na NASA; quem abre o globo já encontra pronto.
 * Uma passagem que já foi tentada (mesma data no catálogo) não é tentada de novo até o próximo reinício.
 */
@Component
public class RegionMonitor {
    private static final Logger log = LoggerFactory.getLogger(RegionMonitor.class);
    private static final ObjectMapper JSON = new ObjectMapper();

    private final AnalysisService analyses;
    private final AnalysisRepository repo;
    private final SceneService scenes;
    private final AraraProperties props;
    private final MonitorProperties monitor;
    private final RegionCatalog catalog;
    private final Map<String, String> attempted = new ConcurrentHashMap<>();
    private volatile List<Map<String, Object>> lastReport = List.of();
    private volatile Instant lastRun;

    public RegionMonitor(AnalysisService analyses, AnalysisRepository repo, SceneService scenes, AraraProperties props,
                         MonitorProperties monitor, RegionCatalog catalog) {
        this.catalog = catalog;
        this.analyses = analyses;
        this.repo = repo;
        this.scenes = scenes;
        this.props = props;
        this.monitor = monitor;
    }

    @Scheduled(initialDelay = 2, fixedDelayString = "${arara.monitor.interval-minutes:360}", timeUnit = TimeUnit.MINUTES)
    public void tick() {
        if (monitor.enabled()) check(LocalDate.now());
    }

    public synchronized List<Map<String, Object>> check(LocalDate today) {
        List<Map<String, Object>> report = new ArrayList<>();
        String start;
        List<Region> regions;
        try {
            var cat = catalog.load();
            start = cat.start();
            regions = cat.regions();
        } catch (Exception e) {
            log.warn("monitor: não foi possível ler as regiões: {}", e.toString());
            return List.of(Map.of("status", "erro", "reason", "arquivo de regiões ilegível"));
        }
        List<Analysis> all = repo.list(null);
        for (Region r : regions) {
            Map<String, Object> line = new LinkedHashMap<>();
            line.put("region", r.id());
            line.put("name", r.name());
            try {
                line.putAll(checkOne(r, start, today, all));
            } catch (RuntimeException e) {
                line.put("action", "erro");
                line.put("reason", e.getMessage());
            }
            report.add(line);
        }
        lastReport = report;
        lastRun = Instant.now();
        report.stream().filter(l -> "submitted".equals(l.get("action")))
                .forEach(l -> log.info("monitor: região {} reanalisada até {} (passagem nova {})", l.get("region"), today, l.get("catalog_last_date")));
        return report;
    }

    Map<String, Object> checkOne(Region r, String start, LocalDate today, List<Analysis> all) {
        Map<String, Object> m = new LinkedHashMap<>();
        if (all.stream().anyMatch(a -> r.name().equals(a.name()) && isActive(a.status()))) {
            m.put("action", "busy");
            return m;
        }
        Geometry aoi = Geo.fromBbox(r.bbox()[0], r.bbox()[1], r.bbox()[2], r.bbox()[3]);
        List<SceneGroup> groups = SceneService.group(scenes.search(Geo.wkt(aoi), start, today.toString()), aoi);
        SceneGroup best = groups.isEmpty() ? null : groups.get(0);
        if (best == null || !best.eligible()) {
            m.put("action", "no_coverage");
            return m;
        }
        m.put("catalog_last_date", best.lastDate());
        String analysed = all.stream()
                .filter(a -> r.name().equals(a.name()) && a.status() == JobStatus.COMPLETED && a.supersededBy() == null)
                .map(RegionMonitor::lastDate).filter(d -> d != null).max(String::compareTo).orElse(null);
        m.put("analysis_last_date", analysed);
        if (analysed != null && analysed.compareTo(best.lastDate()) >= 0) {
            m.put("action", "up_to_date");
            return m;
        }
        if (best.lastDate().equals(attempted.get(r.id()))) {
            m.put("action", "already_attempted");
            return m;
        }
        if (!props.earthdataConfigured()) {
            m.put("action", "no_credentials");
            return m;
        }
        String w = r.bbox()[0] + "," + r.bbox()[1] + "," + r.bbox()[2] + "," + r.bbox()[3];
        var s = analyses.submit(new AnalysisService.Request(r.name(), null, w, start, today.toString(), null, null, false));
        attempted.put(r.id(), best.lastDate());
        m.put("action", "submitted");
        m.put("analysis_id", s.analysisId());
        m.put("job_id", s.jobId());
        return m;
    }

    private static boolean isActive(JobStatus s) {
        return s != null && s.active();
    }

    private static String lastDate(Analysis a) {
        if (a.summaryJson() == null) return null;
        try {
            return JSON.readTree(a.summaryJson()).path("last_date").asText(null);
        } catch (Exception e) {
            return null;
        }
    }

    public Map<String, Object> status() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("enabled", monitor.enabled());
        m.put("interval_minutes", monitor.intervalMinutes());
        m.put("last_run", lastRun == null ? null : lastRun.toString());
        m.put("regions", lastReport);
        return m;
    }
}
