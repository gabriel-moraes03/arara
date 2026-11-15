package br.arara.adapters.persistence;

import br.arara.config.AraraProperties;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * Migração única do banco antigo (H2 em data/db/arara.mv.db) para o PostgreSQL: na primeira subida com o
 * Postgres vazio, copia análises e jobs (inclusive os que estavam na fila, que o AnalysisService retoma).
 * O arquivo H2 é aberto só para leitura e não é apagado. Roda antes dos listeners de ApplicationReady.
 */
@Component
public class LegacyH2Import implements InitializingBean {
    private static final Logger log = LoggerFactory.getLogger(LegacyH2Import.class);
    private static final List<String> TABLES = List.of("analysis", "job");

    private final JdbcTemplate jdbc;
    private final AraraProperties props;

    public LegacyH2Import(JdbcTemplate jdbc, AraraProperties props) {
        this.jdbc = jdbc;
        this.props = props;
    }

    @Override
    public void afterPropertiesSet() {
        Path base = Path.of(props.dataDir(), "db", "arara").toAbsolutePath().normalize();
        if (!Files.exists(Path.of(base + ".mv.db"))) return;
        if (isH2Target()) return;                                    // o banco atual já é H2 (testes): nada a migrar
        Integer n = jdbc.queryForObject("select count(*) from analysis", Integer.class);
        if (n != null && n > 0) return;                              // já migrado
        String url = "jdbc:h2:file:" + base + ";ACCESS_MODE_DATA=r;IFEXISTS=TRUE";
        try (Connection h2 = DriverManager.getConnection(url, "sa", "")) {
            int total = 0;
            for (String t : TABLES) total += copy(h2, t);
            log.info("banco antigo (H2 em {}) importado no PostgreSQL: {} linhas; o arquivo antigo foi mantido", base, total);
        } catch (SQLException e) {
            log.warn("não foi possível importar o banco antigo H2 ({}): {}", base, e.getMessage());
        }
    }

    private boolean isH2Target() {
        try (Connection c = jdbc.getDataSource().getConnection()) {
            return c.getMetaData().getURL().startsWith("jdbc:h2:");
        } catch (SQLException e) {
            return false;
        }
    }

    private int copy(Connection h2, String table) throws SQLException {
        List<String> targetCols = jdbc.queryForList(
                "select column_name from information_schema.columns where table_name = ?", String.class, table);
        int rows = 0;
        try (var st = h2.createStatement(); ResultSet r = st.executeQuery("select * from " + table)) {
            ResultSetMetaData md = r.getMetaData();
            List<String> cols = new ArrayList<>();
            for (int i = 1; i <= md.getColumnCount(); i++) {
                String c = md.getColumnLabel(i).toLowerCase();
                if (targetCols.contains(c)) cols.add(c);
            }
            String sql = "insert into " + table + " (" + String.join(",", cols) + ") values ("
                    + String.join(",", cols.stream().map(c -> "?").toList()) + ")";
            while (r.next()) {
                Object[] vals = new Object[cols.size()];
                for (int i = 0; i < cols.size(); i++) {
                    Object v = r.getObject(cols.get(i));
                    if (v instanceof java.sql.Clob clob) v = clob.getSubString(1, (int) clob.length());
                    vals[i] = v;
                }
                jdbc.update(sql, vals);
                rows++;
            }
        }
        return rows;
    }
}
