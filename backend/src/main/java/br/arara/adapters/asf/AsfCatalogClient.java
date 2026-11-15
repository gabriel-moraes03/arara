package br.arara.adapters.asf;

import br.arara.config.AraraProperties;
import br.arara.domain.Scene;
import br.arara.domain.Unavailable;
import com.fasterxml.jackson.databind.JsonNode;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.retry.annotation.Retry;
import java.net.URI;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;

/** Consulta pública (sem credencial) à ASF Search API: cenas NISAR GCOV que intersectam uma área. */
@Component
public class AsfCatalogClient {
    private static final Logger log = LoggerFactory.getLogger(AsfCatalogClient.class);
    private final RestClient http;
    private final AraraProperties props;

    public AsfCatalogClient(RestClient asfRestClient, AraraProperties props) {
        this.http = asfRestClient;
        this.props = props;
    }

    @CircuitBreaker(name = "asf", fallbackMethod = "unavailable")
    @Retry(name = "asf")
    public List<Scene> search(String wkt, String start, String end) {
        UriComponentsBuilder b = UriComponentsBuilder.fromUriString(props.asfUrl())
                .queryParam("dataset", "NISAR").queryParam("processingLevel", "GCOV")
                .queryParam("intersectsWith", wkt).queryParam("maxResults", 1000).queryParam("output", "geojson");
        if (start != null && !start.isBlank()) b.queryParam("start", start + "T00:00:00Z");
        if (end != null && !end.isBlank()) b.queryParam("end", end + "T23:59:59Z");
        URI uri = b.encode().build().toUri();
        JsonNode body = http.get().uri(uri).retrieve().body(JsonNode.class);
        if (body == null || !body.has("features")) throw new IllegalStateException("resposta da ASF sem 'features'");
        List<Scene> scenes = new ArrayList<>();
        for (JsonNode f : body.get("features")) scenes.add(toScene(f));
        scenes.sort(Comparator.comparing(s -> s.startTime() == null ? "" : s.startTime()));
        return scenes;
    }

    @SuppressWarnings("unused")
    List<Scene> unavailable(String wkt, String start, String end, Throwable t) {
        log.warn("catálogo ASF indisponível: {}", t.toString());
        throw new Unavailable("catálogo NISAR (ASF) indisponível no momento: " + t.getClass().getSimpleName(), t);
    }

    static Scene toScene(JsonNode f) {
        JsonNode p = f.get("properties");
        String name = text(p, "sceneName") != null ? text(p, "sceneName") : text(p, "fileID");
        String[] parts = name == null ? new String[0] : name.split("_");
        String file = text(p, "fileName") != null ? text(p, "fileName") : name + ".h5";
        Long size = null;
        JsonNode bytes = p.get("bytes");
        if (bytes != null && bytes.isObject() && bytes.has(file) && bytes.get(file).has("bytes")) size = bytes.get(file).get("bytes").asLong();
        else if (bytes != null && bytes.isNumber()) size = bytes.asLong();
        String dir = text(p, "flightDirection");
        List<String> pols = new ArrayList<>();
        if (p.has("mainBandPolarization")) p.get("mainBandPolarization").forEach(x -> pols.add(x.asText()));
        String start = text(p, "startTime");
        String collection = text(p, "collectionName");
        return new Scene(name, collection, Scene.maturityOf(collection), text(p, "crid"), start, text(p, "stopTime"),
                start == null ? null : start.substring(0, Math.min(10, start.length())),
                p.hasNonNull("pathNumber") ? p.get("pathNumber").asInt() : null,
                dir == null || dir.isEmpty() ? null : dir.substring(0, 1).toUpperCase(),
                p.hasNonNull("frameNumber") ? p.get("frameNumber").asInt() : null,
                parts.length > 9 ? parts[8] : null, parts.length > 9 ? parts[9] : null, pols,
                text(p, "processingDate"), f.get("geometry"), text(p, "url"), size);
    }

    private static String text(JsonNode p, String k) {
        return p.hasNonNull(k) ? p.get(k).asText() : null;
    }
}
