package br.arara.domain;

import java.util.List;

/** Grupo de geometria: UMA coleção, trilha, direção e frame. Nunca se misturam numa análise. */
public record SceneGroup(
        String id, String collection, String maturity, Integer track, String direction, Integer frame,
        int nDates, List<String> dates, String firstDate, String lastDate, double aoiCoverage,
        List<String> crids, List<String> polarizations, int datesWithHv, boolean eligible, List<Scene> scenes) {
}
