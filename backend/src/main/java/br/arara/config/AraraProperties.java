package br.arara.config;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** Configuração do Arara (application.yml + variáveis de ambiente / .env). */
@ConfigurationProperties("arara")
public record AraraProperties(
        String dataDir, String pipelineDir, String frontendDir, String python, String algorithmVersion,
        String asfUrl, double aoiMaxKm2, int maxScenes, int retentionDays, long diskLimitMb,
        int pipelineTimeoutMinutes, String earthdataUsername, String earthdataPassword) {

    public Path analysesDir() {
        return Path.of(dataDir, "analyses").toAbsolutePath().normalize();
    }

    public boolean earthdataConfigured() {
        return earthdataUsername != null && !earthdataUsername.isBlank()
                && earthdataPassword != null && !earthdataPassword.isBlank();
    }

    /** Nunca expõe as credenciais, nem por acidente num log. */
    @Override
    public String toString() {
        return "AraraProperties[dataDir=" + dataDir + ", earthdataConfigured=" + earthdataConfigured() + "]";
    }
}
