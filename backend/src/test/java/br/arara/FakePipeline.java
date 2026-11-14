package br.arara;

import br.arara.adapters.pipeline.PipelineRunner;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;

/** Pipeline falsa SÓ para os testes do backend: grava os mesmos arquivos que a real gravaria. */
public class FakePipeline implements PipelineRunner {
    private static final ObjectMapper JSON = new ObjectMapper();

    @Override
    public JsonNode run(Path specFile, Path outDir, Progress progress) throws Exception {
        JsonNode spec = JSON.readTree(specFile.toFile());
        String id = spec.get("analysis_id").asText();
        progress.update("discover", 0.02, "catálogo");
        progress.update("acquire", 0.3, "lendo janelas");
        if ("1999-01-01".equals(spec.path("start").asText())) {
            String r = "{\"status\":\"unavailable\",\"analysis_id\":\"" + id + "\",\"reason\":\"nenhuma cena NISAR GCOV intersecta a área no período\"}";
            Files.writeString(outDir.resolve("result.json"), r);
            return JSON.readTree(r);
        }
        if ("1998-01-01".equals(spec.path("start").asText())) throw new IllegalStateException("pipeline quebrou");
        progress.update("classify", 0.6, "classificando");
        String result = """
                {"status":"completed","analysis_id":"%s","algorithm_version":"arara-water-0.1.0","sensor":"NISAR L-band SAR (GCOV L2), HH",
                 "experimental":false,"group":{"id":"NISAR_L2_GCOV_PROVISIONAL_V1|132|A|168","maturity":"PROVISIONAL"},
                 "dates":[{"date":"2026-07-05","water_km2":120.5,"water_pct":6.1,"suspeita_vento":false,"crid":"P05023"},
                          {"date":"2026-10-09","water_km2":98.25,"water_pct":5.0,"suspeita_vento":true,"crid":"P05023"}],
                 "comparison":{"before":"2026-07-05","after":"2026-10-09","net_change_ha":-2225.0},
                 "optical_validation":{"status":"validated","mean_iou":0.81},
                 "layers":[{"id":"change","type":"change","png":"png/change.png","tiles":"tiles/change/{z}/{x}/{y}.png",
                            "bounds":{"west":-57.6,"south":-18.6,"east":-57.2,"north":-18.2},"zooms":[6]}]}
                """.formatted(id);
        Files.writeString(outDir.resolve("result.json"), result);
        Files.writeString(outDir.resolve("metrics.json"), "{\"dates\":[{\"date\":\"2026-07-05\",\"water_km2\":120.5}]}");
        Files.writeString(outDir.resolve("metrics.csv"), "date,water_km2\n2026-07-05,120.5\n2026-10-09,98.25\n");
        Files.writeString(outDir.resolve("sources.json"), "{\"scenes\":[{\"granule\":\"G1\",\"crid\":\"P05023\"}]}");
        Files.createDirectories(outDir.resolve("png"));
        Files.createDirectories(outDir.resolve("tiles/change/6/21"));
        byte[] png = {(byte) 0x89, 'P', 'N', 'G'};
        Files.write(outDir.resolve("png/change.png"), png);
        Files.write(outDir.resolve("tiles/change/6/21/35.png"), png);
        progress.update("publish", 1.0, "pronto");
        return JSON.readTree(result);
    }
}
