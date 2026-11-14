package br.arara.adapters.pipeline;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.file.Path;

/** Porta para a pipeline científica (Python). O resultado é o result.json que ela grava em outDir. */
public interface PipelineRunner {
    interface Progress {
        void update(String stage, double progress, String message);
    }

    /** Roda a análise descrita em specFile; bloqueia até terminar. Devolve o conteúdo de result.json. */
    JsonNode run(Path specFile, Path outDir, Progress progress) throws Exception;
}
