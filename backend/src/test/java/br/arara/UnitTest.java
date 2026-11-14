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
                echo "{\\"status\\":\\"completed\\",\\"credenciais_no_ambiente\\":$cred,\\"args\\":\\"$*\\"}" > "$4/result.json"
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
    void processRunnerFailsLoudlyWithoutResult(@TempDir Path tmp) throws Exception {
        Path out = Files.createDirectories(tmp.resolve("out"));
        var props = new AraraProperties(tmp.toString(), ".", ".", "python3", "v", "http://x", 2500, 12, 7, 100, 1, "", "");
        assertThatThrownBy(() -> new ProcessPipelineRunner(List.of("sh", "-c", "exit 3"), tmp, props)
                .run(tmp.resolve("spec.json"), out, (s, p, m) -> { })).hasMessageContaining("sem gravar result.json");
    }
}
