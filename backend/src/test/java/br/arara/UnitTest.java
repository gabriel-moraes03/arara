package br.arara;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import br.arara.adapters.pipeline.ProcessPipelineRunner;
import br.arara.config.AraraProperties;
import br.arara.domain.AnalysisId;
import br.arara.domain.Geo;
import br.arara.domain.JobStatus;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.locationtech.jts.geom.Geometry;

class UnitTest {
    final ObjectMapper json = new ObjectMapper();

    Geometry poly(String coords) throws Exception {
        return Geo.fromGeoJson(json.readTree("{\"type\":\"Polygon\",\"coordinates\":[" + coords + "]}"));
    }

    @Test
    void sameAreaDrawnDifferentlyHasTheSameId() throws Exception {
        Geometry a = poly("[[-57.6,-18.6],[-57.2,-18.6],[-57.2,-18.2],[-57.6,-18.2],[-57.6,-18.6]]");
        Geometry b = poly("[[-57.2,-18.2],[-57.6,-18.2],[-57.6,-18.6],[-57.2,-18.6],[-57.2,-18.2]]");   // outro início e sentido
        String v = "arara-water-0.1.0";
        String h = AnalysisId.hash(a, "2026-06-01", "2026-11-14", null, null, v);
        assertThat(h).hasSize(64).isEqualTo(AnalysisId.hash(b, "2026-06-01", "2026-11-14", "", "", v))
                .isEqualTo(AnalysisId.hash(Geo.fromBbox("-57.6,-18.6,-57.2,-18.2"), "2026-06-01", "2026-11-14", null, null, v));
        assertThat(h).isNotEqualTo(AnalysisId.hash(a, "2026-06-02", "2026-11-14", null, null, v))
                .isNotEqualTo(AnalysisId.hash(a, "2026-06-01", "2026-11-14", "g|1|A|2", null, v))
                .isNotEqualTo(AnalysisId.hash(a, "2026-06-01", "2026-11-14", null, null, "arara-water-0.2.0"));
    }

    @Test
    void geometryAreaAndValidation() throws Exception {
        double km2 = Geo.areaKm2(Geo.fromBbox("-57.6,-18.6,-57.2,-18.2"));
        assertThat(km2).isBetween(1850.0, 1900.0);        // 0,4° x 0,4° a 18,4°S (geodésico: ~1870 km²)
        assertThatThrownBy(() -> poly("[[0,0],[1,1],[0,1],[1,0],[0,0]]")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> poly("[[0,0],[1,0],[1,1],[0,1]]")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> Geo.fromBbox("1,2,3")).isInstanceOf(IllegalArgumentException.class);
        assertThat(JobStatus.ofStage("acquire")).isEqualTo(JobStatus.DOWNLOADING);
        assertThat(JobStatus.ofStage("classify")).isEqualTo(JobStatus.PROCESSING);
    }

    @Test
    void processRunnerReadsProgressAndPassesCredentialsOnlyThroughEnvironment(@TempDir Path tmp) throws Exception {
        Path script = tmp.resolve("fake.sh");
        Files.writeString(script, """
                #!/bin/sh
                # pipeline falsa: $1=--spec $2=<spec> $3=--out $4=<dir>
                echo '{"stage":"acquire","progress":0.35,"message":"lendo janela 1/2"}'
                echo 'linha que não é JSON'
                echo '{"stage":"classify","progress":0.62,"message":"classificando"}'
                if [ -n "$EARTHDATA_USERNAME" ] && [ -n "$EARTHDATA_PASSWORD" ]; then cred=true; else cred=false; fi
                args=$(echo "$*" | tr '\\\\' '/')     # caminhos do Windows: barra invertida quebraria o JSON
                echo "{\\"status\\":\\"completed\\",\\"credenciais_no_ambiente\\":$cred,\\"args\\":\\"$args\\"}" > "$4/result.json"
                """);
        Path out = Files.createDirectories(tmp.resolve("out"));
        Path spec = Files.writeString(tmp.resolve("spec.json"), "{}");
        var props = new AraraProperties(tmp.toString(), ".", ".", "python3", "v", "http://x", 2500, 12, 7, 100, 1, "fulano", "s3nh4-secreta");
        List<String> seen = new ArrayList<>();
        JsonNode r = new ProcessPipelineRunner(List.of("sh", script.toString()), tmp, props)
                .run(spec, out, (stage, p, msg) -> seen.add(stage + ":" + p));
        assertThat(seen).containsExactly("acquire:0.35", "classify:0.62");
        assertThat(r.get("credenciais_no_ambiente").asBoolean()).isTrue();
        assertThat(r.get("args").asText()).doesNotContain("s3nh4-secreta").doesNotContain("fulano");
        assertThat(props.toString()).doesNotContain("s3nh4-secreta").doesNotContain("fulano");

        var semCredencial = new AraraProperties(tmp.toString(), ".", ".", "python3", "v", "http://x", 2500, 12, 7, 100, 1, "", "");
        JsonNode r2 = new ProcessPipelineRunner(List.of("sh", script.toString()), tmp, semCredencial).run(spec, out, (s, p, m) -> { });
        assertThat(r2.get("credenciais_no_ambiente").asBoolean()).isFalse();
    }

    @Test
    void processRunnerReadsAccentedProgressAsUtf8(@TempDir Path tmp) throws Exception {
        Path script = tmp.resolve("fake.sh");
        Files.writeString(script, """
                #!/bin/sh
                printf '{"stage":"publish","progress":0.9,"message":"gravando COGs, PNGs, tiles e métricas (%s)"}\\n' "$PYTHONIOENCODING"
                echo '{"status":"completed"}' > "$4/result.json"
                """, java.nio.charset.StandardCharsets.UTF_8);
        Path out = Files.createDirectories(tmp.resolve("out"));
        var props = new AraraProperties(tmp.toString(), ".", ".", "python3", "v", "http://x", 2500, 12, 7, 100, 1, "", "");
        List<String> msgs = new ArrayList<>();
        new ProcessPipelineRunner(List.of("sh", script.toString()), tmp, props)
                .run(tmp.resolve("spec.json"), out, (s, p, m) -> msgs.add(m));
        assertThat(msgs).containsExactly("gravando COGs, PNGs, tiles e métricas (utf-8)");
    }

    @Test
    void qualityIsNeverPromoted() throws Exception {
        var experimental = (com.fasterxml.jackson.databind.node.ObjectNode) json.readTree(
                "{\"quality\":\"experimental\",\"quality_reasons\":[\"vento\"],\"experimental\":false,\"dates\":[]}");
        assertThat(br.arara.application.Quality.apply(experimental).get("quality").asText()).isEqualTo("experimental");
        assertThat(experimental.get("experimental").asBoolean()).isTrue();
        var legacyBadIou = json.readTree("{\"experimental\":false,\"params\":{\"threshold_db\":-16.3},"
                + "\"dates\":[{\"water_pct\":18.5,\"margin_blocks\":17}],"
                + "\"optical_validation\":{\"status\":\"validated\",\"n_dates_validated\":10,\"mean_iou\":0.69}}");
        assertThat(br.arara.application.Quality.of(legacyBadIou).quality()).isEqualTo("experimental");
        var legacyWithForecast = (com.fasterxml.jackson.databind.node.ObjectNode) legacyBadIou.deepCopy();
        legacyWithForecast.putObject("forecast").put("status", "ok");
        assertThat(br.arara.application.Quality.apply(legacyWithForecast).path("forecast").path("status").asText()).isEqualTo("unavailable");
        var legacyNoMargin = json.readTree("{\"experimental\":true,\"params\":{\"threshold_db\":-11.2,"
                + "\"threshold\":{\"source\":\"limiar_bimodal\",\"date_index\":0}},\"dates\":[{\"water_pct\":63.1,\"margin_blocks\":0}]}");
        assertThat(br.arara.application.Quality.of(legacyNoMargin).quality()).isEqualTo("no_reliable_water");
    }

    @Test
    void radarAndSentinelOnlyAgreeWithinFivePoints() throws Exception {
        // resultado gravado antes do rótulo: Nanuque 21/07 (vento) tinha 24,7% x 0% e a tabela dizia "concordam"
        var r = (com.fasterxml.jackson.databind.node.ObjectNode) json.readTree("{\"quality\":\"no_reliable_water\",\"dates\":[],"
                + "\"optical_validation\":{\"divergence\":{\"per_date\":["
                + "{\"sar_water_fraction\":0.247,\"optical_water_fraction\":0.0,\"level\":\"wind\"},"
                + "{\"sar_water_fraction\":0.22,\"optical_water_fraction\":0.17,\"level\":\"none\"},"
                + "{\"sar_water_fraction\":0.2502,\"optical_water_fraction\":0.2536,\"level\":\"none\"}]}}}");
        var rows = br.arara.application.Quality.apply(r).path("optical_validation").path("divergence").path("per_date");
        assertThat(rows.get(0).path("agreement").asText()).isEqualTo("optical_no_water");
        assertThat(rows.get(0).path("difference_pp").asDouble()).isEqualTo(24.7);
        assertThat(rows.get(1).path("agreement").asText()).isEqualTo("diverge");
        assertThat(rows.get(2).path("agreement").asText()).isEqualTo("agree");
    }

    @Test
    void processRunnerFailsLoudlyWithoutResult(@TempDir Path tmp) throws Exception {
        Path out = Files.createDirectories(tmp.resolve("out"));
        var props = new AraraProperties(tmp.toString(), ".", ".", "python3", "v", "http://x", 2500, 12, 7, 100, 1, "", "");
        assertThatThrownBy(() -> new ProcessPipelineRunner(List.of("sh", "-c", "exit 3"), tmp, props)
                .run(tmp.resolve("spec.json"), out, (s, p, m) -> { })).hasMessageContaining("sem gravar result.json");
    }
}
