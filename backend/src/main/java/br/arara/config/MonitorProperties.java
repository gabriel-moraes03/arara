package br.arara.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Desempenho e monitor das regiões (application.yml, prefixo arara.monitor).
 *
 * @param enabled         liga o monitor que reanalisa as regiões quando o NISAR passa de novo
 * @param intervalMinutes de quanto em quanto tempo consultar o catálogo
 * @param regionsFile     JSON das regiões (o mesmo que o globo lê), relativo à pasta do frontend
 * @param cacheMaxMb      limite do cache de passagens, Sentinel-2, HAND e chuva (data/cache)
 * @param readWorkers     passagens lidas ao mesmo tempo, cada uma num processo
 */
@ConfigurationProperties("arara.monitor")
public record MonitorProperties(boolean enabled, long intervalMinutes, String regionsFile, long cacheMaxMb, int readWorkers) {
    public MonitorProperties {
        if (intervalMinutes <= 0) intervalMinutes = 360;
        if (regionsFile == null || regionsFile.isBlank()) regionsFile = "globe/regioes.json";
        if (cacheMaxMb <= 0) cacheMaxMb = 8192;
        if (readWorkers <= 0) readWorkers = 3;
    }

    public static MonitorProperties defaults() {
        return new MonitorProperties(false, 0, null, 0, 0);
    }
}
