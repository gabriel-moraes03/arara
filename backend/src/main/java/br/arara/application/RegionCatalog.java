package br.arara.application;

import br.arara.config.AraraProperties;
import br.arara.config.MonitorProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** As regiões monitoradas (frontend/globe/regioes.json), o mesmo arquivo que o globo lê. */
@Component
public class RegionCatalog {
    private static final ObjectMapper JSON = new ObjectMapper();

    public record Region(String id, String name, String uf, double[] bbox) {
    }

    public record Catalog(String start, List<Region> regions) {
    }

    private final AraraProperties props;
    private final MonitorProperties monitor;

    public RegionCatalog(AraraProperties props, MonitorProperties monitor) {
        this.props = props;
        this.monitor = monitor;
    }

    public Catalog load() throws IOException {
        JsonNode file = JSON.readTree(Path.of(props.frontendDir()).resolve(monitor.regionsFile()).toFile());
        List<Region> out = new ArrayList<>();
        for (JsonNode r : file.path("regioes")) {
            JsonNode b = r.path("b");
            out.add(new Region(r.path("id").asText(), r.path("n").asText(), r.path("uf").asText(""),
                    new double[]{b.get(0).asDouble(), b.get(1).asDouble(), b.get(2).asDouble(), b.get(3).asDouble()}));
        }
        return new Catalog(file.path("inicio").asText("2026-06-01"), out);
    }

    public Optional<Region> find(String id) throws IOException {
        return load().regions().stream().filter(r -> r.id().equals(id)).findFirst();
    }
}
