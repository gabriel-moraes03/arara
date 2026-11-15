package br.arara.adapters.pipeline;

import br.arara.config.AraraProperties;
import br.arara.config.MonitorProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Roda `python -m arara_pipeline.run` num processo filho e lê o progresso (JSON Lines) do stdout. */
public class ProcessPipelineRunner implements PipelineRunner {
    private static final Logger log = LoggerFactory.getLogger(ProcessPipelineRunner.class);
    private final List<String> baseCommand;
    private final Path workDir;
    private final AraraProperties props;
    private final MonitorProperties perf;
    private final ObjectMapper json = new ObjectMapper();

    public ProcessPipelineRunner(List<String> baseCommand, Path workDir, AraraProperties props) {
        this(baseCommand, workDir, props, MonitorProperties.defaults());
    }

    public ProcessPipelineRunner(List<String> baseCommand, Path workDir, AraraProperties props, MonitorProperties perf) {
        this.baseCommand = baseCommand;
        this.workDir = workDir;
        this.props = props;
        this.perf = perf;
    }

    @Override
    public JsonNode run(Path specFile, Path outDir, Progress progress) throws Exception {
        List<String> cmd = new ArrayList<>(baseCommand);
        cmd.addAll(List.of("--spec", specFile.toString(), "--out", outDir.toString()));
        ProcessBuilder pb = new ProcessBuilder(cmd).directory(workDir.toFile());
        pb.redirectError(outDir.resolve("pipeline.log").toFile());
        Map<String, String> env = pb.environment();
        env.put("PYTHONUNBUFFERED", "1");
        env.put("PYTHONIOENCODING", "utf-8");     // progresso com acento chega inteiro (o pipe no Windows seria cp1252)
        env.put("PYTHONUTF8", "1");
        env.put("ARARA_AOI_MAX_KM2", String.valueOf(props.aoiMaxKm2()));
        env.put("ARARA_MAX_SCENES", String.valueOf(props.maxScenes()));
        // cache por passagem (data/cache) e leitura em paralelo: reanalisar a mesma área relê só o que é novo
        env.put("ARARA_CACHE_DIR", Path.of(props.dataDir(), "cache").toAbsolutePath().normalize().toString());
        env.put("ARARA_CACHE_MAX_MB", String.valueOf(perf.cacheMaxMb()));
        env.put("ARARA_READ_WORKERS", String.valueOf(perf.readWorkers()));
        // credenciais Earthdata: só no ambiente do processo filho; nunca em argumento, log ou arquivo
        if (props.earthdataConfigured()) {
            env.put("EARTHDATA_USERNAME", props.earthdataUsername());
            env.put("EARTHDATA_PASSWORD", props.earthdataPassword());
        } else {
            env.remove("EARTHDATA_USERNAME");
            env.remove("EARTHDATA_PASSWORD");
        }
        Process p = pb.start();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) {
                if (!line.startsWith("{")) continue;
                try {
                    JsonNode n = json.readTree(line);
                    progress.update(n.path("stage").asText(""), n.path("progress").asDouble(0), n.path("message").asText(""));
                } catch (Exception e) {
                    log.debug("linha de progresso ignorada");
                }
            }
        }
        if (!p.waitFor(props.pipelineTimeoutMinutes(), TimeUnit.MINUTES)) {
            p.destroyForcibly();
            throw new IllegalStateException("a pipeline passou do tempo limite de " + props.pipelineTimeoutMinutes() + " min");
        }
        Path result = outDir.resolve("result.json");
        if (!Files.exists(result)) {
            throw new IllegalStateException("a pipeline terminou (código " + p.exitValue() + ") sem gravar result.json; veja pipeline.log");
        }
        return json.readTree(result.toFile());
    }
}
