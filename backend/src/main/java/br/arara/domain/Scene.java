package br.arara.domain;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;

/** Uma cena NISAR GCOV do catálogo (mesmos campos do catalog_nisar.py). */
public record Scene(
        String granule, String collection, String maturity, String crid, String startTime, String stopTime,
        String date, Integer track, String direction, Integer frame, String mode, String polCode,
        List<String> polarizations, String processingDate, JsonNode footprint, String url, Long sizeBytes) {

    public String groupId() {
        return collection + "|" + track + "|" + direction + "|" + frame;
    }

    public static String maturityOf(String collection) {
        String c = collection == null ? "" : collection.toUpperCase();
        if (c.contains("BETA")) return "BETA";
        if (c.contains("PROVISIONAL")) return "PROVISIONAL";
        return c.isEmpty() ? "UNKNOWN" : "VALIDATED";
    }
}
