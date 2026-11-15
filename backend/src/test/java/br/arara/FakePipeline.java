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
        String result = switch (spec.path("start").asText()) {
            case "2026-06-02" -> NO_WATER.formatted(id);
            case "2026-06-03" -> LEGACY_NO_WATER.formatted(id);
            default -> RELIABLE.formatted(id);
        };
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

    static final String RELIABLE = """
                {"status":"completed","analysis_id":"%s","algorithm_version":"arara-water-0.1.0","sensor":"NISAR L-band SAR (GCOV L2), HH",
                 "experimental":false,"group":{"id":"NISAR_L2_GCOV_PROVISIONAL_V1|132|A|168","maturity":"PROVISIONAL"},
                 "dates":[{"date":"2026-07-05","water_km2":120.5,"water_pct":6.1,"suspeita_vento":false,"crid":"P05023"},
                          {"date":"2026-10-09","water_km2":98.25,"water_pct":5.0,"suspeita_vento":true,"crid":"P05023"}],
                 "comparison":{"before":"2026-07-05","after":"2026-10-09","net_change_ha":-2225.0},
                 "optical_validation":{"status":"validated","mean_iou":0.81},
                 "layers":[{"id":"change","type":"change","png":"png/change.png","tiles":"tiles/change/{z}/{x}/{y}.png",
                            "bounds":{"west":-57.6,"south":-18.6,"east":-57.2,"north":-18.2},"zooms":[6]}]}
                """;

    /** Como a pipeline nova grava uma área sem água: status, motivos, cenas e só o radar HH. */
    static final String NO_WATER = """
            {"status":"completed","analysis_id":"%s","quality":"no_reliable_water",
             "quality_reasons":["o radar não achou margem água/terra nítida (só 0 blocos de margem, mínimo 5)"],
             "what_to_try":"desenhe uma área menor em volta do corpo de água","experimental":true,
             "group":{"id":"NISAR_L2_GCOV_PROVISIONAL_V1|16|A|169","maturity":"PROVISIONAL"},
             "params":{"threshold_db":-11.23},
             "dates":[{"date":"2026-06-27","water_km2":null,"water_pct":null,"suspeita_vento":null,"crid":"P05023","margin_blocks":0},
                      {"date":"2026-10-13","water_km2":null,"water_pct":null,"suspeita_vento":null,"crid":"P05023","margin_blocks":0}],
             "comparison":null,"patterns":null,"forecast":null,"insights":null,
             "optical_validation":{"status":"not_optically_validated","reason":"x"},
             "layers":[{"id":"hh_20260627","type":"backscatter","bounds":{"west":-40.5,"south":-17.9,"east":-40.4,"north":-17.8}}]}
            """;

    /** Resultado gravado antes do controle de qualidade (a análise de Nanuque): números de água sem base. */
    static final String LEGACY_NO_WATER = """
            {"status":"completed","analysis_id":"%s","experimental":true,
             "experimental_reasons":["só 0 blocos de margem água/terra (mínimo 5)"],
             "group":{"id":"NISAR_L2_GCOV_PROVISIONAL_V1|16|A|169","maturity":"PROVISIONAL"},
             "params":{"threshold_db":-11.23,"threshold":{"source":"limiar_bimodal","date_index":0}},
             "dates":[{"date":"2026-06-27","water_km2":34.55,"water_pct":50.3,"suspeita_vento":false,"margin_blocks":0},
                      {"date":"2026-07-21","water_km2":16.95,"water_pct":24.7,"suspeita_vento":true,"margin_blocks":0},
                      {"date":"2026-10-13","water_km2":43.29,"water_pct":63.1,"suspeita_vento":false,"margin_blocks":0}],
             "comparison":{"before":"2026-06-27","after":"2026-10-13","net_change_ha":874.0},
             "patterns":{"trend":{"status":"ok","km2_per_week":0.5}},
             "forecast":{"status":"ok","points":[{"date":"2026-11-18","water_km2":44.0}]},
             "warnings":["datas com suspeita de vento (água mais clara que o normal da série): 2026-07-21",
                         "etapa optical_stage falhou e foi ignorada: TypeError: unsupported operand type(s) for +: 'float' and 'NoneType'"],
             "optical_validation":{"status":"not_optically_validated","reason":"validação óptica não executada nesta versão"},
             "layers":[{"id":"water_20261013","type":"water"},{"id":"hh_20261013","type":"backscatter"},{"id":"change","type":"change"}]}
            """;
}
