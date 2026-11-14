package br.arara.config;

import br.arara.adapters.pipeline.PipelineRunner;
import br.arara.adapters.pipeline.ProcessPipelineRunner;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AppConfig implements WebMvcConfigurer {
    private final AraraProperties props;

    public AppConfig(AraraProperties props) {
        this.props = props;
    }

    @Bean
    RestClient asfRestClient() {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(10));
        factory.setReadTimeout(Duration.ofSeconds(60));
        return RestClient.builder().requestFactory(factory).build();
    }

    @Bean
    PipelineRunner pipelineRunner() {
        return new ProcessPipelineRunner(
                List.of(Path.of(props.python()).toAbsolutePath().normalize().toString(), "-m", "arara_pipeline.run"),
                Path.of(props.pipelineDir()).toAbsolutePath().normalize(), props);
    }

    /** O globo é servido em "/" e o site de Furnas em "/furnas/", direto das pastas do frontend. */
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String base = Path.of(props.frontendDir()).toAbsolutePath().normalize().toUri().toString();
        registry.addResourceHandler("/furnas/**").addResourceLocations(base + "furnas/").setCacheControl(CacheControl.noCache());
        registry.addResourceHandler("/**").addResourceLocations(base + "globe/").setCacheControl(CacheControl.noCache());
    }

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addViewController("/").setViewName("forward:/index.html");
        registry.addRedirectViewController("/furnas", "/furnas/index.html");
        registry.addRedirectViewController("/furnas/", "/furnas/index.html");
    }
}
