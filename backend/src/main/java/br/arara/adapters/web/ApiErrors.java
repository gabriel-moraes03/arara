package br.arara.adapters.web;

import br.arara.domain.Unavailable;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

/** Erros da API sempre com status e motivo legíveis; "unavailable" nunca vem com dado substituto. */
@RestControllerAdvice(assignableTypes = AraraController.class)
public class ApiErrors {
    @ExceptionHandler(Unavailable.class)
    ResponseEntity<Map<String, Object>> unavailable(Unavailable e) {
        return body(HttpStatus.SERVICE_UNAVAILABLE, "unavailable", e.getMessage());
    }

    @ExceptionHandler({IllegalArgumentException.class, HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class})
    ResponseEntity<Map<String, Object>> invalid(Exception e) {
        String reason = e instanceof IllegalArgumentException ? e.getMessage() : "pedido malformado";
        return body(HttpStatus.BAD_REQUEST, "invalid", reason);
    }

    @ExceptionHandler(NoSuchElementException.class)
    ResponseEntity<Map<String, Object>> notFound(NoSuchElementException e) {
        return body(HttpStatus.NOT_FOUND, "not_found", e.getMessage());
    }

    private static ResponseEntity<Map<String, Object>> body(HttpStatus http, String status, String reason) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("status", status);
        m.put("reason", reason);
        return ResponseEntity.status(http).body(m);
    }
}
