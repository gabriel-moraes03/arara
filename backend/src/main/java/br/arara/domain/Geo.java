package br.arara.domain;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.locationtech.jts.geom.Coordinate;
import org.locationtech.jts.geom.Envelope;
import org.locationtech.jts.geom.Geometry;
import org.locationtech.jts.geom.GeometryFactory;
import org.locationtech.jts.geom.LinearRing;
import org.locationtech.jts.geom.Polygon;

/** GeoJSON (lon/lat) <-> JTS, área aproximada e forma canônica para o hash da análise. */
public final class Geo {
    private static final GeometryFactory GF = new GeometryFactory();
    private static final double R_KM = 6371.0088;

    private Geo() {
    }

    public static Geometry fromBbox(double west, double south, double east, double north) {
        if (!(west < east && south < north)) throw new IllegalArgumentException("bbox inválido: use oeste,sul,leste,norte");
        return GF.toGeometry(new Envelope(west, east, south, north));
    }

    public static Geometry fromBbox(String bbox) {
        String[] p = bbox.split(",");
        if (p.length != 4) throw new IllegalArgumentException("bbox inválido: use oeste,sul,leste,norte");
        try {
            return fromBbox(Double.parseDouble(p[0].trim()), Double.parseDouble(p[1].trim()),
                    Double.parseDouble(p[2].trim()), Double.parseDouble(p[3].trim()));
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("bbox inválido: use oeste,sul,leste,norte");
        }
    }

    public static Geometry fromGeoJson(JsonNode node) {
        if (node == null || node.isNull() || !node.has("type")) throw new IllegalArgumentException("GeoJSON sem 'type'");
        String type = node.get("type").asText();
        switch (type) {
            case "Feature":
                return fromGeoJson(node.get("geometry"));
            case "FeatureCollection":
                if (!node.has("features") || node.get("features").isEmpty()) throw new IllegalArgumentException("FeatureCollection vazia");
                return fromGeoJson(node.get("features").get(0));
            case "Polygon":
                return validated(polygon(node.get("coordinates")));
            case "MultiPolygon":
                List<Polygon> parts = new ArrayList<>();
                for (JsonNode p : node.get("coordinates")) parts.add(polygon(p));
                return validated(GF.createMultiPolygon(parts.toArray(new Polygon[0])));
            default:
                throw new IllegalArgumentException("geometria não suportada: " + type + " (use Polygon ou MultiPolygon)");
        }
    }

    private static Geometry validated(Geometry g) {
        if (g.isEmpty() || !g.isValid()) throw new IllegalArgumentException("geometria inválida (anel aberto ou que se cruza)");
        Envelope e = g.getEnvelopeInternal();
        if (e.getMinX() < -180 || e.getMaxX() > 180 || e.getMinY() < -90 || e.getMaxY() > 90)
            throw new IllegalArgumentException("coordenadas fora de lon/lat (EPSG:4326)");
        return g;
    }

    private static Polygon polygon(JsonNode rings) {
        if (rings == null || !rings.isArray() || rings.isEmpty()) throw new IllegalArgumentException("polígono sem anéis");
        LinearRing shell = ring(rings.get(0));
        LinearRing[] holes = new LinearRing[rings.size() - 1];
        for (int i = 1; i < rings.size(); i++) holes[i - 1] = ring(rings.get(i));
        return GF.createPolygon(shell, holes);
    }

    private static LinearRing ring(JsonNode pts) {
        if (pts == null || pts.size() < 4) throw new IllegalArgumentException("anel com menos de 4 pontos");
        Coordinate[] c = new Coordinate[pts.size()];
        for (int i = 0; i < pts.size(); i++) c[i] = new Coordinate(pts.get(i).get(0).asDouble(), pts.get(i).get(1).asDouble());
        if (!c[0].equals2D(c[c.length - 1])) throw new IllegalArgumentException("anel não fechado");
        return GF.createLinearRing(c);
    }

    /** Área em km² na esfera (suficiente para o limite de tamanho; a pipeline refaz no elipsoide). */
    public static double areaKm2(Geometry g) {
        double total = 0;
        for (int i = 0; i < g.getNumGeometries(); i++) {
            if (!(g.getGeometryN(i) instanceof Polygon p)) continue;
            total += Math.abs(ringArea(p.getExteriorRing().getCoordinates()));
            for (int h = 0; h < p.getNumInteriorRing(); h++) total -= Math.abs(ringArea(p.getInteriorRingN(h).getCoordinates()));
        }
        return total;
    }

    private static double ringArea(Coordinate[] c) {
        double s = 0;
        for (int i = 0; i < c.length - 1; i++) {
            s += Math.toRadians(c[i + 1].x - c[i].x)
                    * (2 + Math.sin(Math.toRadians(c[i].y)) + Math.sin(Math.toRadians(c[i + 1].y)));
        }
        return s * R_KM * R_KM / 2;
    }

    /** WKT com 6 casas e anéis normalizados: a mesma área desenhada de outro jeito dá o mesmo texto. */
    public static String canonicalWkt(Geometry g) {
        Geometry n = g.copy();
        n.normalize();
        StringBuilder sb = new StringBuilder(n.getGeometryType().toUpperCase(Locale.ROOT)).append('(');
        for (int i = 0; i < n.getNumGeometries(); i++) {
            Polygon p = (Polygon) n.getGeometryN(i);
            if (i > 0) sb.append(',');
            sb.append('(');
            appendRing(sb, p.getExteriorRing().getCoordinates());
            for (int h = 0; h < p.getNumInteriorRing(); h++) {
                sb.append(',');
                appendRing(sb, p.getInteriorRingN(h).getCoordinates());
            }
            sb.append(')');
        }
        return sb.append(')').toString();
    }

    private static void appendRing(StringBuilder sb, Coordinate[] c) {
        sb.append('(');
        for (int i = 0; i < c.length; i++) {
            if (i > 0) sb.append(',');
            sb.append(String.format(Locale.ROOT, "%.6f %.6f", c[i].x, c[i].y));
        }
        sb.append(')');
    }

    /** WKT simples (POLYGON/MULTIPOLYGON) para a consulta ao catálogo. */
    public static String wkt(Geometry g) {
        return g.toText();
    }
}
