package br.arara.domain;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.locationtech.jts.geom.Geometry;

/** Identidade de uma análise: SHA-256 de tudo o que muda o resultado. Mesmo pedido = mesmo id (cache). */
public final class AnalysisId {
    public static final String SENSOR = "NISAR-LSAR-GCOV-HH";
    public static final String METHOD = "limiar_bimodal";
    public static final int ID_LENGTH = 24;

    private AnalysisId() {
    }

    public static String hash(Geometry aoi, String start, String end, String groupId, String maturity, String version) {
        String canon = String.join("\n", Geo.canonicalWkt(aoi), nz(start), nz(end), SENSOR, METHOD,
                "group=" + nz(groupId), "maturity=" + nz(maturity).toUpperCase(), "version=" + version);
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canon.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    public static String shortId(String hash) {
        return hash.substring(0, ID_LENGTH);
    }

    private static String nz(String s) {
        return s == null ? "" : s.trim();
    }
}
