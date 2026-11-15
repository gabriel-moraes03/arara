package br.arara.adapters.storage;

import br.arara.config.AraraProperties;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Optional;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.springframework.stereotype.Component;

/** Arquivos derivados de cada análise em data/analyses/{id}/ (COG, PNG, tiles, métricas, fontes). */
@Component
public class AnalysisStorage {
    private static final Pattern ID = Pattern.compile("[0-9a-f]{8,64}");
    private static final Pattern NAME = Pattern.compile("[A-Za-z0-9_]{1,80}");
    private final Path root;

    public AnalysisStorage(AraraProperties props) {
        this.root = props.analysesDir();
    }

    public static boolean validId(String id) {
        return id != null && ID.matcher(id).matches();
    }

    public static boolean validName(String name) {
        return name != null && NAME.matcher(name).matches();
    }

    public Path dir(String id) {
        if (!validId(id)) throw new IllegalArgumentException("id de análise inválido");
        return root.resolve(id);
    }

    public Path prepare(String id) {
        try {
            delete(id);
            return Files.createDirectories(dir(id));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** Arquivo dentro da pasta da análise, ou vazio se não existir (nunca sai da pasta). */
    public Optional<Path> file(String id, String... parts) {
        Path base = dir(id);
        Path p = base;
        for (String part : parts) p = p.resolve(part);
        p = p.normalize();
        return p.startsWith(base) && Files.isRegularFile(p) ? Optional.of(p) : Optional.empty();
    }

    public void delete(String id) {
        Path d = dir(id);
        if (!Files.exists(d)) return;
        try (Stream<Path> s = Files.walk(d)) {
            s.sorted(Comparator.reverseOrder()).forEach(p -> p.toFile().delete());
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public long usedBytes() {
        if (!Files.exists(root)) return 0;
        try (Stream<Path> s = Files.walk(root)) {
            return s.filter(Files::isRegularFile).mapToLong(p -> p.toFile().length()).sum();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
