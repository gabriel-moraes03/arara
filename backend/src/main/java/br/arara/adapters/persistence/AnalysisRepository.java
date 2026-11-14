package br.arara.adapters.persistence;

import br.arara.domain.JobStatus;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AnalysisRepository {
    public record Analysis(String id, String hash, String name, JobStatus status, String aoiGeojson,
                           double west, double south, double east, double north, double areaKm2,
                           String startDate, String endDate, String groupId, String maturity, String algorithmVersion,
                           String reason, Boolean experimental, String summaryJson,
                           Instant createdAt, Instant updatedAt, Instant completedAt) {
    }

    public record Job(String id, String analysisId, JobStatus status, String stage, double progress,
                      String message, String reason, Instant createdAt, Instant updatedAt) {
    }

    private final JdbcTemplate jdbc;

    public AnalysisRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void upsert(Analysis a) {
        jdbc.update("delete from analysis where id = ?", a.id());
        jdbc.update("insert into analysis (id, hash, name, status, aoi_geojson, west, south, east, north, area_km2, start_date, "
                        + "end_date, group_id, maturity, algorithm_version, created_at, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                a.id(), a.hash(), a.name(), a.status().name(), a.aoiGeojson(), a.west(), a.south(), a.east(), a.north(),
                a.areaKm2(), a.startDate(), a.endDate(), a.groupId(), a.maturity(), a.algorithmVersion(),
                Timestamp.from(a.createdAt()), Timestamp.from(a.updatedAt()));
    }

    public void finish(String id, JobStatus status, String reason, Boolean experimental, String summaryJson) {
        Timestamp now = Timestamp.from(Instant.now());
        jdbc.update("update analysis set status = ?, reason = ?, experimental = ?, summary_json = ?, updated_at = ?, completed_at = ? where id = ?",
                status.name(), reason, experimental, summaryJson, now, status == JobStatus.COMPLETED ? now : null, id);
    }

    public void setStatus(String id, JobStatus status) {
        jdbc.update("update analysis set status = ?, updated_at = ? where id = ?", status.name(), Timestamp.from(Instant.now()), id);
    }

    public Optional<Analysis> find(String id) {
        return jdbc.query("select * from analysis where id = ?", this::analysis, id).stream().findFirst();
    }

    public List<Analysis> list(JobStatus status) {
        return status == null
                ? jdbc.query("select * from analysis order by updated_at desc", this::analysis)
                : jdbc.query("select * from analysis where status = ? order by updated_at desc", this::analysis, status.name());
    }

    public List<Analysis> olderThan(Instant limit) {
        return jdbc.query("select * from analysis where updated_at < ? order by updated_at", this::analysis, Timestamp.from(limit));
    }

    public void delete(String id) {
        jdbc.update("delete from job where analysis_id = ?", id);
        jdbc.update("delete from analysis where id = ?", id);
    }

    public void insert(Job j) {
        jdbc.update("insert into job (id, analysis_id, status, stage, progress, message, reason, created_at, updated_at) values (?,?,?,?,?,?,?,?,?)",
                j.id(), j.analysisId(), j.status().name(), j.stage(), j.progress(), j.message(), j.reason(),
                Timestamp.from(j.createdAt()), Timestamp.from(j.updatedAt()));
    }

    public void progress(String jobId, JobStatus status, String stage, double progress, String message) {
        jdbc.update("update job set status = ?, stage = ?, progress = ?, message = ?, updated_at = ? where id = ?",
                status.name(), stage, progress, message, Timestamp.from(Instant.now()), jobId);
    }

    public void finishJob(String jobId, JobStatus status, String reason) {
        jdbc.update("update job set status = ?, reason = ?, progress = 1, updated_at = ? where id = ?",
                status.name(), reason, Timestamp.from(Instant.now()), jobId);
    }

    public Optional<Job> findJob(String id) {
        return jdbc.query("select * from job where id = ?", this::job, id).stream().findFirst();
    }

    public Optional<Job> activeJob(String analysisId) {
        return jdbc.query("select * from job where analysis_id = ? and status in ('QUEUED','DOWNLOADING','PROCESSING') order by created_at desc",
                this::job, analysisId).stream().findFirst();
    }

    public List<Job> activeJobs() {
        return jdbc.query("select * from job where status in ('QUEUED','DOWNLOADING','PROCESSING') order by created_at", this::job);
    }

    private Analysis analysis(ResultSet r, int i) throws SQLException {
        Timestamp done = r.getTimestamp("completed_at");
        boolean exp = r.getBoolean("experimental");
        Boolean experimental = r.wasNull() ? null : exp;
        return new Analysis(r.getString("id"), r.getString("hash"), r.getString("name"), JobStatus.valueOf(r.getString("status")),
                r.getString("aoi_geojson"), r.getDouble("west"), r.getDouble("south"), r.getDouble("east"), r.getDouble("north"),
                r.getDouble("area_km2"), r.getString("start_date"), r.getString("end_date"), r.getString("group_id"),
                r.getString("maturity"), r.getString("algorithm_version"), r.getString("reason"), experimental,
                r.getString("summary_json"), r.getTimestamp("created_at").toInstant(), r.getTimestamp("updated_at").toInstant(),
                done == null ? null : done.toInstant());
    }

    private Job job(ResultSet r, int i) throws SQLException {
        return new Job(r.getString("id"), r.getString("analysis_id"), JobStatus.valueOf(r.getString("status")), r.getString("stage"),
                r.getDouble("progress"), r.getString("message"), r.getString("reason"),
                r.getTimestamp("created_at").toInstant(), r.getTimestamp("updated_at").toInstant());
    }
}
