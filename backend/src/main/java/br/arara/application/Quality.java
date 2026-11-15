package br.arara.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Qualidade de uma análise (reliable | experimental | no_reliable_water). Vem da pipeline; para
 * resultados antigos, sem o campo, é recalculada a partir dos números gravados, sempre para baixo:
 * o backend nunca promove uma análise.
 */
public final class Quality {
    public static final String RELIABLE = "reliable", EXPERIMENTAL = "experimental", NO_RELIABLE_WATER = "no_reliable_water";
    static final int MIN_MARGIN_BLOCKS = 5;
    static final double THRESHOLD_MIN_DB = -22, THRESHOLD_MAX_DB = -12, WATER_PCT_MIN = 0.5, WATER_PCT_MAX = 90, MIN_IOU = 0.7;
    /** Mesmos cortes da pipeline (quality.py): "concordam" só com diferença de fração abaixo de 5 pontos. */
    static final double AGREE_PP = 5, OPTICAL_NO_WATER = 0.005, SAR_WITH_WATER = 0.05;
    private static final Pattern STAGE_FAILED = Pattern.compile("^etapa (\\w+) falhou e foi ignorada: .*", Pattern.DOTALL);

    public record Verdict(String quality, List<String> reasons) {
    }

    private Quality() {
    }

    public static Verdict of(JsonNode r) {
        if (r.hasNonNull("quality")) {
            List<String> reasons = new ArrayList<>();
            r.path("quality_reasons").forEach(n -> reasons.add(n.asText()));
            return new Verdict(r.get("quality").asText(), reasons);
        }
        List<String> grave = new ArrayList<>(), mild = new ArrayList<>();
        JsonNode dates = r.path("dates"), params = r.path("params");
        int idx = params.path("threshold").path("date_index").asInt(0);
        if ("limiar_bimodal".equals(params.path("threshold").path("source").asText()) && dates.size() > idx
                && dates.get(idx).has("margin_blocks") && dates.get(idx).path("margin_blocks").asInt() < MIN_MARGIN_BLOCKS) {
            grave.add("o radar não achou margem água/terra nítida (só " + dates.get(idx).path("margin_blocks").asInt()
                    + " blocos de margem, mínimo " + MIN_MARGIN_BLOCKS + ")");
        }
        if (params.hasNonNull("threshold_db")) {
            double t = params.get("threshold_db").asDouble();
            if (t < THRESHOLD_MIN_DB || t > THRESHOLD_MAX_DB) {
                grave.add(String.format(java.util.Locale.ROOT, "o limiar água/terra saiu em %.1f dB, fora da faixa da água calma (-22 a -12 dB)", t));
            }
        }
        int out = 0, n = 0;
        for (JsonNode d : dates) {
            if (!d.hasNonNull("water_pct")) continue;
            n++;
            double p = d.get("water_pct").asDouble();
            if (p < WATER_PCT_MIN || p > WATER_PCT_MAX) out++;
        }
        if (n > 0 && out > n / 2.0) grave.add("em " + out + " de " + n + " datas a água ficou fora de 0,5% a 90% da área");
        JsonNode v = r.path("optical_validation");
        if ("validated".equals(v.path("status").asText()) && v.path("n_dates_validated").asInt() >= 3
                && v.hasNonNull("mean_iou") && v.get("mean_iou").asDouble() < MIN_IOU) {
            mild.add(String.format(java.util.Locale.ROOT, "o radar diverge do Sentinel-2 (IoU médio %.2f)", v.get("mean_iou").asDouble()));
        }
        if (r.path("experimental").asBoolean(false) && grave.isEmpty()) r.path("experimental_reasons").forEach(m -> mild.add(m.asText()));
        if (!grave.isEmpty()) {
            grave.add("análise feita antes do controle de qualidade; refaça para o resultado atual");
            return new Verdict(NO_RELIABLE_WATER, grave);
        }
        return mild.isEmpty() ? new Verdict(RELIABLE, List.of()) : new Verdict(EXPERIMENTAL, mild);
    }

    /** Grava quality/quality_reasons no resultado e, sem água confiável, tira todo número de água. */
    public static ObjectNode apply(ObjectNode r) {
        Verdict q = of(r);
        r.put("quality", q.quality());
        ArrayNode reasons = r.putArray("quality_reasons");
        q.reasons().forEach(reasons::add);
        r.put("experimental", !RELIABLE.equals(q.quality()));
        ArrayNode warnings = r.putArray("warnings_clean");
        r.path("warnings").forEach(w -> {
            String t = friendly(w.asText());
            if (NO_RELIABLE_WATER.equals(q.quality()) && t.startsWith("datas com suspeita de vento")) return;
            warnings.add(t);
        });
        r.set("warnings", warnings);
        r.remove("warnings_clean");
        for (JsonNode p : r.path("optical_validation").path("divergence").path("per_date")) {
            if (p.has("agreement") || !p.isObject()) continue;              // resultados de antes do rótulo
            double sar = p.path("sar_water_fraction").asDouble(), opt = p.path("optical_water_fraction").asDouble();
            String level = p.path("level").asText();
            double pp = Math.round(Math.abs(sar - opt) * 1000) / 10.0;
            ((ObjectNode) p).put("difference_pp", pp);
            ((ObjectNode) p).put("agreement", opt < OPTICAL_NO_WATER && sar >= SAR_WITH_WATER ? "optical_no_water"
                    : pp >= AGREE_PP || "strong".equals(level) || "moderate".equals(level) ? "diverge" : "agree");
        }
        if (EXPERIMENTAL.equals(q.quality()) && "ok".equals(r.path("forecast").path("status").asText())) {
            ObjectNode none = r.putObject("forecast");      // experimental não tem projeção (resultados antigos tinham)
            none.put("status", "unavailable");
            none.put("experimental", true);
            none.put("reason", "análise experimental: sem projeção");
        }
        if (NO_RELIABLE_WATER.equals(q.quality())) {
            for (JsonNode d : r.path("dates")) {
                ObjectNode o = (ObjectNode) d;
                o.putNull("water_km2");
                o.putNull("water_pct");
                o.putNull("hh_water_median_db");
                o.putNull("suspeita_vento");
            }
            r.putNull("comparison");
            r.putNull("patterns");
            r.putNull("forecast");
            r.putNull("insights");
            if (!r.hasNonNull("what_to_try")) {
                r.put("what_to_try", "desenhe uma área menor em volta do corpo d'água, com margem de terra dos dois lados, "
                        + "ou escolha outra geometria (trilha/frame) no catálogo");
            }
            ArrayNode keep = r.arrayNode();
            r.path("layers").forEach(l -> {
                String type = l.path("type").asText();
                if ("backscatter".equals(type) || "optical_water".equals(type)) keep.add(l);
            });
            r.set("layers", keep);
        }
        return r;
    }

    /** Exceção crua de uma etapa opcional (resultados antigos) vira uma frase para o usuário. */
    static String friendly(String warning) {
        Matcher m = STAGE_FAILED.matcher(warning);
        if (!m.matches()) return warning;
        return switch (m.group(1)) {
            case "optical_stage" -> "validação óptica indisponível nesta análise (erro ao comparar com o Sentinel-2)";
            case "forecast" -> "projeção indisponível nesta análise";
            case "insights" -> "leitura da mudança indisponível nesta análise";
            default -> "uma etapa opcional não rodou nesta análise";
        };
    }
}
