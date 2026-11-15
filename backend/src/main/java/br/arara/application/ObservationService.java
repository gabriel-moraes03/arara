package br.arara.application;

import br.arara.adapters.persistence.AnalysisRepository;
import br.arara.adapters.persistence.AnalysisRepository.Analysis;
import br.arara.adapters.persistence.ObservationRepository;
import br.arara.adapters.persistence.ObservationRepository.Observation;
import br.arara.adapters.storage.AnalysisStorage;
import br.arara.domain.JobStatus;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Service;

/**
 * Grava uma observação por passagem quando uma análise termina e, ao subir, preenche o histórico a partir
 * dos resultados que ainda estão no disco. Sem água confiável, nenhuma área entra (Quality.apply zera).
 */
@Service
public class ObservationService {
    private static final Logger log = LoggerFactory.getLogger(ObservationService.class);
    private static final ObjectMapper JSON = new ObjectMapper();

    private final ObservationRepository observations;
    private final AnalysisRepository analyses;
    private final AnalysisStorage storage;

    public ObservationService(ObservationRepository observations, AnalysisRepository analyses, AnalysisStorage storage) {
        this.observations = observations;
        this.analyses = analyses;
        this.storage = storage;
    }

    public static List<Observation> fromResult(Analysis a, JsonNode raw, Instant computedAt) {
        ObjectNode r = Quality.apply((ObjectNode) raw.deepCopy());
        JsonNode flood = r.path("flood");
        String ref = "ok".equals(flood.path("status").asText()) ? flood.path("reference_date").asText(null) : null;
        Double threshold = num(r.path("params").path("threshold_db"));
        List<Observation> out = new ArrayList<>();
        for (JsonNode d : r.path("dates")) {
            List<String> reasons = new ArrayList<>();
            d.path("confidence").path("reasons").forEach(x -> reasons.add(x.asText()));
            out.add(new Observation(a.id(), d.path("date").asText(), a.name(), a.west(), a.south(), a.east(), a.north(),
                    d.path("granule").asText(null), d.path("crid").asText(null), r.path("algorithm_version").asText(a.algorithmVersion()),
                    r.path("quality").asText(null), num(d.path("water_km2")), num(d.path("water_pct")), num(d.path("flood_km2")),
                    num(d.path("flooded_vegetation_km2")), ref, num(d.path("rain_3d_mm")), num(d.path("rain_7d_mm")),
                    d.hasNonNull("suspeita_vento") ? d.get("suspeita_vento").asBoolean() : null, num(d.path("valid_fraction_aoi")),
                    threshold, d.path("confidence").path("level").asText(null), reasons.isEmpty() ? null : String.join("; ", reasons),
                    computedAt));
        }
        return out;
    }

    /** Depois de um job concluído: o resultado vira linhas no histórico. Falha aqui não derruba a análise. */
    public void record(String analysisId, JsonNode result) {
        try {
            analyses.find(analysisId).ifPresent(a -> observations.replace(a.id(), fromResult(a, result, Instant.now())));
        } catch (RuntimeException e) {
            log.warn("histórico: não gravou as observações da análise {}: {}", analysisId, e.toString());
        }
    }

    /** Ao subir: análises concluídas sem observações e com result.json no disco entram no histórico. */
    @EventListener(ApplicationReadyEvent.class)
    @Order(10)
    public int backfill() {
        int n = 0;
        for (Analysis a : analyses.list(JobStatus.COMPLETED)) {
            if (observations.exists(a.id())) continue;
            var file = storage.file(a.id(), "result.json");
            if (file.isEmpty()) continue;
            try {
                observations.replace(a.id(), fromResult(a, JSON.readTree(file.get().toFile()),
                        a.completedAt() != null ? a.completedAt() : a.updatedAt()));
                n++;
            } catch (Exception e) {
                log.warn("histórico: resultado ilegível da análise {}: {}", a.id(), e.toString());
            }
        }
        if (n > 0) log.info("histórico: {} análises antigas entraram no banco ({} observações no total)", n, observations.count());
        return n;
    }

    private static Double num(JsonNode n) {
        return n == null || n.isNull() || n.isMissingNode() || !n.isNumber() ? null : n.asDouble();
    }
}
