package br.arara.domain;

import java.util.Locale;

public enum JobStatus {
    QUEUED, DOWNLOADING, PROCESSING, COMPLETED, FAILED, UNAVAILABLE;

    public String api() {
        return name().toLowerCase(Locale.ROOT);
    }

    public boolean active() {
        return this == QUEUED || this == DOWNLOADING || this == PROCESSING;
    }

    public static JobStatus of(String s) {
        return valueOf(s.toUpperCase(Locale.ROOT));
    }

    /** Etapa da pipeline -> estado visível do job. */
    public static JobStatus ofStage(String stage) {
        return switch (stage) {
            case "discover", "select", "acquire" -> DOWNLOADING;
            default -> PROCESSING;
        };
    }
}
