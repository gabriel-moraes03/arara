package br.arara.adapters.persistence;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

/** Observações por passagem (tabela observation): o histórico que sobrevive à limpeza dos arquivos. */
@Repository
public class ObservationRepository {
    public record Observation(String analysisId, String passDate, String name, double west, double south, double east, double north,
                              String granule, String crid, String algorithmVersion, String quality,
                              Double waterKm2, Double waterPct, Double floodKm2, Double floodedVegetationKm2, String referenceDate,
                              Double rain3dMm, Double rain7dMm, Boolean wind, Double validFraction, Double thresholdDb,
                              String confidence, String confidenceReasons, Instant computedAt) {
    }

    /** Tolerância (graus) para "mesmo retângulo", a mesma de AnalysisRepository.markSuperseded. */
    public static final double SAME_BOX = 1e-4;
    private final JdbcTemplate jdbc;

    public ObservationRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void replace(String analysisId, List<Observation> obs) {
        jdbc.update("delete from observation where analysis_id = ?", analysisId);
        for (Observation o : obs) {
            jdbc.update("insert into observation (analysis_id, pass_date, name, west, south, east, north, granule, crid, algorithm_version, "
                            + "quality, water_km2, water_pct, flood_km2, flooded_vegetation_km2, reference_date, rain_3d_mm, rain_7d_mm, wind, "
                            + "valid_fraction, threshold_db, confidence, confidence_reasons, computed_at) "
                            + "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    o.analysisId(), o.passDate(), o.name(), o.west(), o.south(), o.east(), o.north(), o.granule(), o.crid(),
                    o.algorithmVersion(), o.quality(), o.waterKm2(), o.waterPct(), o.floodKm2(), o.floodedVegetationKm2(),
                    o.referenceDate(), o.rain3dMm(), o.rain7dMm(), o.wind(), o.validFraction(), o.thresholdDb(),
                    o.confidence(), o.confidenceReasons(), Timestamp.from(o.computedAt()));
        }
    }

    public boolean exists(String analysisId) {
        Integer n = jdbc.queryForObject("select count(*) from observation where analysis_id = ?", Integer.class, analysisId);
        return n != null && n > 0;
    }

    public long count() {
        Long n = jdbc.queryForObject("select count(*) from observation", Long.class);
        return n == null ? 0 : n;
    }

    /**
     * Série de um lugar (mesmo nome e mesmo retângulo): para cada data, a medição mais recente
     * (a de maior computed_at). Ordenada por data.
     */
    public List<Observation> history(String name, double west, double south, double east, double north) {
        List<Observation> all = jdbc.query("select * from observation where name = ? and abs(west - ?) < ? and abs(south - ?) < ? "
                        + "and abs(east - ?) < ? and abs(north - ?) < ? order by pass_date, computed_at",
                this::observation, name, west, SAME_BOX, south, SAME_BOX, east, SAME_BOX, north, SAME_BOX);
        Map<String, Observation> latest = new LinkedHashMap<>();
        for (Observation o : all) latest.put(o.passDate(), o);     // ordenado por computed_at: a última vence
        return new ArrayList<>(latest.values());
    }

    private Observation observation(ResultSet r, int i) throws SQLException {
        return new Observation(r.getString("analysis_id"), r.getString("pass_date"), r.getString("name"),
                r.getDouble("west"), r.getDouble("south"), r.getDouble("east"), r.getDouble("north"),
                r.getString("granule"), r.getString("crid"), r.getString("algorithm_version"), r.getString("quality"),
                dbl(r, "water_km2"), dbl(r, "water_pct"), dbl(r, "flood_km2"), dbl(r, "flooded_vegetation_km2"),
                r.getString("reference_date"), dbl(r, "rain_3d_mm"), dbl(r, "rain_7d_mm"), bool(r, "wind"),
                dbl(r, "valid_fraction"), dbl(r, "threshold_db"), r.getString("confidence"), r.getString("confidence_reasons"),
                r.getTimestamp("computed_at").toInstant());
    }

    private static Double dbl(ResultSet r, String c) throws SQLException {
        double v = r.getDouble(c);
        return r.wasNull() ? null : v;
    }

    private static Boolean bool(ResultSet r, String c) throws SQLException {
        boolean v = r.getBoolean(c);
        return r.wasNull() ? null : v;
    }
}
