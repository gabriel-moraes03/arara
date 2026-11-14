package br.arara.application;

import br.arara.adapters.asf.AsfCatalogClient;
import br.arara.domain.Geo;
import br.arara.domain.Scene;
import br.arara.domain.SceneGroup;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import org.locationtech.jts.geom.Geometry;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

/** Catálogo ao vivo (com cache de 1 h) e grupos de geometria para uma área. */
@Service
public class SceneService {
    public static final double MIN_COVERAGE = 0.95;
    private final AsfCatalogClient asf;

    public SceneService(AsfCatalogClient asf) {
        this.asf = asf;
    }

    @Cacheable(cacheNames = "scenes", key = "#wkt + '|' + #start + '|' + #end")
    public List<Scene> search(String wkt, String start, String end) {
        return asf.search(wkt, start, end);
    }

    public static List<Scene> filter(List<Scene> scenes, String maturity) {
        if (maturity == null || maturity.isBlank()) return scenes;
        return scenes.stream().filter(s -> maturity.equalsIgnoreCase(s.maturity())).toList();
    }

    /** Agrupa por (coleção, trilha, direção, frame); uma cena por data (processamento mais recente). */
    public static List<SceneGroup> group(List<Scene> scenes, Geometry aoi) {
        Map<String, TreeMap<String, Scene>> byGroup = new LinkedHashMap<>();
        for (Scene s : scenes) {
            if (s.date() == null) continue;
            byGroup.computeIfAbsent(s.groupId(), k -> new TreeMap<>()).merge(s.date(), s,
                    (a, b) -> nz(b.processingDate()).compareTo(nz(a.processingDate())) > 0 ? b : a);
        }
        List<SceneGroup> groups = new ArrayList<>();
        for (var e : byGroup.entrySet()) {
            List<Scene> list = new ArrayList<>(e.getValue().values());
            double coverage = list.stream().mapToDouble(s -> coverage(s, aoi)).min().orElse(0);
            Scene first = list.get(0);
            groups.add(new SceneGroup(e.getKey(), first.collection(), first.maturity(), first.track(), first.direction(),
                    first.frame(), list.size(), list.stream().map(Scene::date).toList(), first.date(),
                    list.get(list.size() - 1).date(), Math.round(coverage * 1e4) / 1e4,
                    new ArrayList<>(new TreeSet<>(list.stream().map(Scene::crid).filter(c -> c != null).toList())),
                    new ArrayList<>(new TreeSet<>(list.stream().flatMap(s -> s.polarizations().stream()).toList())),
                    (int) list.stream().filter(s -> s.polarizations().contains("HV")).count(),
                    coverage >= MIN_COVERAGE, list));
        }
        groups.sort(Comparator.comparing((SceneGroup g) -> !g.eligible())
                .thenComparing(g -> -g.nDates()).thenComparing(g -> -g.datesWithHv())
                .thenComparing(g -> -g.aoiCoverage()).thenComparing(SceneGroup::id));
        return groups;
    }

    static double coverage(Scene s, Geometry aoi) {
        if (s.footprint() == null || s.footprint().isNull() || aoi.getArea() == 0) return 0;
        try {
            return Geo.fromGeoJson(s.footprint()).intersection(aoi).getArea() / aoi.getArea();
        } catch (RuntimeException e) {
            return 0;
        }
    }

    private static String nz(String s) {
        return s == null ? "" : s;
    }
}
