package br.arara.domain;

/** O dado real não pode ser obtido agora; a API responde "unavailable" com o motivo, nunca um substituto. */
public class Unavailable extends RuntimeException {
    public Unavailable(String reason) {
        super(reason);
    }

    public Unavailable(String reason, Throwable cause) {
        super(reason, cause);
    }
}
