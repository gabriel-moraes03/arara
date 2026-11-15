package br.arara;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import br.arara.adapters.persistence.AnalysisRepository;
import br.arara.adapters.persistence.AnalysisRepository.Analysis;
import br.arara.application.AnalysisService;
import br.arara.application.RegionCatalog;
import br.arara.application.RegionMonitor;
import br.arara.application.SceneService;
import br.arara.config.AraraProperties;
import br.arara.config.MonitorProperties;
import br.arara.domain.JobStatus;
import br.arara.domain.Scene;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** O monitor só pede análise quando o catálogo tem passagem mais nova que a última análise da região. */
class RegionMonitorTest {
    private static final ObjectMapper JSON = new ObjectMapper();

    private static Scene scene(String date) throws Exception {
        var fp = JSON.readTree("{\"type\":\"Polygon\",\"coordinates\":[[[-53,-31],[-50,-31],[-50,-29],[-53,-29],[-53,-31]]]}");
        return new Scene("G" + date, "NISAR_L2_GCOV_PROVISIONAL_V1", "PROVISIONAL", "P05023", date + "T10:00:00Z", null, date,
                53, "D", 103, "2005", "DHDH", List.of("HH", "HV"), "2026-11-01", fp, "https://x/" + date + ".h5", 1L);
    }

    private static Analysis analysis(String name, JobStatus st, String lastDate) {
        String summary = lastDate == null ? null : "{\"last_date\":\"" + lastDate + "\",\"quality\":\"reliable\"}";
        Instant t = Instant.parse("2026-11-01T00:00:00Z");
        return new Analysis("a" + lastDate, "h", name, st, "{}", -51.4, -30.15, -51.1, -29.9, 800, "2026-06-01", "2026-11-01",
                null, null, "v", null, false, summary, t, t, t, null);
    }

    @Test
    void submitsOnlyWhenThereIsANewPass(@TempDir Path tmp) throws Exception {
        Files.createDirectories(tmp.resolve("globe"));
        Files.writeString(tmp.resolve("globe/regioes.json"), """
                {"inicio":"2026-06-01","regioes":[
                 {"id":"guaiba","n":"Delta do Jacuí e Guaíba","b":[-51.40,-30.15,-51.10,-29.90]},
                 {"id":"taquari","n":"Vale do Taquari","b":[-52.05,-29.55,-51.85,-29.35]}]}""");
        var props = new AraraProperties(tmp.toString(), ".", tmp.toString(), "python3", "v", "http://x", 2500, 12, 7, 100, 1, "u", "p");
        var mon = new MonitorProperties(true, 360, "globe/regioes.json", 100, 2);
        AnalysisService analyses = mock(AnalysisService.class);
        AnalysisRepository repo = mock(AnalysisRepository.class);
        SceneService scenes = mock(SceneService.class);
        when(scenes.search(anyString(), anyString(), anyString())).thenReturn(List.of(scene("2026-10-15"), scene("2026-10-27")));
        when(repo.list(null)).thenReturn(List.of(
                analysis("Delta do Jacuí e Guaíba", JobStatus.COMPLETED, "2026-10-15"),   // falta a de 27/10
                analysis("Vale do Taquari", JobStatus.COMPLETED, "2026-10-27")));         // em dia
        when(analyses.submit(any())).thenReturn(new AnalysisService.Submitted("novo", "job", JobStatus.QUEUED, false));

        var monitor = new RegionMonitor(analyses, repo, scenes, props, mon, new RegionCatalog(props, mon));
        List<Map<String, Object>> r = monitor.check(LocalDate.parse("2026-11-15"));
        assertThat(r).extracting(m -> m.get("action")).containsExactly("submitted", "up_to_date");
        verify(analyses, times(1)).submit(any());

        // a mesma passagem já tentada não é pedida de novo (ex.: a análise ficou indisponível)
        when(repo.list(null)).thenReturn(List.of(analysis("Delta do Jacuí e Guaíba", JobStatus.COMPLETED, "2026-10-15"),
                analysis("Vale do Taquari", JobStatus.COMPLETED, "2026-10-27")));
        assertThat(monitor.check(LocalDate.parse("2026-11-15")).get(0).get("action")).isEqualTo("already_attempted");

        // região com job em andamento: espera
        var fresh = new RegionMonitor(analyses, repo, scenes, props, mon, new RegionCatalog(props, mon));
        when(repo.list(null)).thenReturn(List.of(analysis("Delta do Jacuí e Guaíba", JobStatus.DOWNLOADING, null),
                analysis("Vale do Taquari", JobStatus.COMPLETED, "2026-10-27")));
        assertThat(fresh.check(LocalDate.parse("2026-11-15")).get(0).get("action")).isEqualTo("busy");
        verify(analyses, times(1)).submit(any());
    }

    @Test
    void disabledMonitorDoesNothing(@TempDir Path tmp) {
        var props = new AraraProperties(tmp.toString(), ".", tmp.toString(), "python3", "v", "http://x", 2500, 12, 7, 100, 1, "u", "p");
        AnalysisService analyses = mock(AnalysisService.class);
        var off = new MonitorProperties(false, 0, null, 0, 0);
        var monitor = new RegionMonitor(analyses, mock(AnalysisRepository.class), mock(SceneService.class), props, off,
                new RegionCatalog(props, off));
        monitor.tick();
        verify(analyses, never()).submit(any());
    }
}
