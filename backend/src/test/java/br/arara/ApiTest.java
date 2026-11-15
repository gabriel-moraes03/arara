package br.arara;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.equalTo;
import static com.github.tomakehurst.wiremock.client.WireMock.getRequestedFor;
import static com.github.tomakehurst.wiremock.client.WireMock.containing;
import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import br.arara.adapters.persistence.AnalysisRepository;
import br.arara.adapters.pipeline.PipelineRunner;
import br.arara.adapters.storage.AnalysisStorage;
import br.arara.application.AnalysisService;
import br.arara.domain.JobStatus;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiTest {
    static final WireMockServer ASF = new WireMockServer(WireMockConfiguration.options().dynamicPort());
    static final String PANTANAL = "-57.6,-18.6,-57.2,-18.2";
    static final String SECRET_USER = "usuario-secreto-de-teste", SECRET_PASS = "senha-secreta-de-teste";
    static Path dataDir;

    @TestConfiguration
    static class Fakes {
        @Bean
        @org.springframework.context.annotation.Primary
        PipelineRunner fakePipeline() {
            return new FakePipeline();
        }
    }

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry r) throws Exception {
        ASF.start();
        dataDir = Files.createTempDirectory("arara-test");
        r.add("arara.asf-url", () -> ASF.baseUrl() + "/services/search/param");
        r.add("arara.data-dir", () -> dataDir.toString());
        r.add("arara.frontend-dir", () -> "../frontend");
        r.add("arara.earthdata-username", () -> SECRET_USER);
        r.add("arara.earthdata-password", () -> SECRET_PASS);
        r.add("resilience4j.retry.instances.asf.wait-duration", () -> "10ms");
        // o teste de catálogo fora do ar não deve abrir o disjuntor para os outros testes
        r.add("resilience4j.circuitbreaker.instances.asf.minimum-number-of-calls", () -> "1000");
        r.add("resilience4j.circuitbreaker.instances.asf.sliding-window-size", () -> "1000");
    }

    @AfterAll
    static void stop() {
        ASF.stop();
    }

    @Autowired MockMvc mvc;
    @Autowired AnalysisRepository repo;
    @Autowired AnalysisStorage storage;
    @Autowired AnalysisService service;
    final ObjectMapper json = new ObjectMapper();

    @BeforeEach
    void stubs() throws Exception {
        ASF.resetAll();
        String fixture = new String(getClass().getResourceAsStream("/asf_gcov_pantanal.json").readAllBytes());
        ASF.stubFor(com.github.tomakehurst.wiremock.client.WireMock.get(urlPathEqualTo("/services/search/param"))
                .willReturn(aResponse().withHeader("Content-Type", "application/json").withBody(fixture)));
    }

    JsonNode body(org.springframework.test.web.servlet.ResultActions r) throws Exception {
        return json.readTree(r.andReturn().getResponse().getContentAsString());
    }

    JsonNode waitJob(String jobId) throws Exception {
        for (int i = 0; i < 100; i++) {
            JsonNode j = body(mvc.perform(get("/api/arara/jobs/" + jobId)).andExpect(status().isOk()));
            if (!JobStatus.of(j.get("status").asText()).active()) return j;
            Thread.sleep(50);
        }
        throw new AssertionError("job não terminou");
    }

    String analysisBody(String start) {
        return "{\"name\":\"Pantanal teste\",\"bbox\":\"" + PANTANAL + "\",\"start\":\"" + start + "\",\"end\":\"2026-11-14\"}";
    }

    @Test
    void scenesFromRealCatalogResponseAreGroupedWithoutMixing() throws Exception {
        JsonNode r = body(mvc.perform(get("/api/arara/scenes").param("bbox", PANTANAL)
                .param("start", "2026-06-01").param("end", "2026-11-14")).andExpect(status().isOk()));
        assertThat(r.get("count").asInt()).isEqualTo(38);
        assertThat(r.get("scenes").get(0).get("crid").asText()).startsWith("P05");
        assertThat(r.get("scenes").get(0).has("footprint")).isTrue();
        JsonNode groups = r.get("groups");
        assertThat(groups.size()).isEqualTo(6);
        assertThat(groups.get(0).get("eligible").asBoolean()).isTrue();
        assertThat(groups.get(0).get("id").asText()).isEqualTo("NISAR_L2_GCOV_PROVISIONAL_V1|132|A|168");
        for (JsonNode g : groups) {      // um grupo = uma coleção, uma trilha, uma direção, um frame
            assertThat(g.get("id").asText()).isEqualTo(g.get("collection").asText() + "|" + g.get("track").asInt()
                    + "|" + g.get("direction").asText() + "|" + g.get("frame").asInt());
            assertThat(g.get("crids").size()).isEqualTo(1);
        }
        ASF.verify(getRequestedFor(urlPathEqualTo("/services/search/param"))
                .withQueryParam("dataset", equalTo("NISAR")).withQueryParam("processingLevel", equalTo("GCOV"))
                .withQueryParam("intersectsWith", containing("POLYGON")).withQueryParam("start", equalTo("2026-06-01T00:00:00Z")));
        // segunda consulta igual: vem do cache de 1 h, sem nova chamada à ASF
        mvc.perform(get("/api/arara/scenes").param("bbox", PANTANAL).param("start", "2026-06-01").param("end", "2026-11-14"))
                .andExpect(status().isOk());
        ASF.verify(1, getRequestedFor(urlPathEqualTo("/services/search/param")));
        // filtro de maturidade
        JsonNode v = body(mvc.perform(get("/api/arara/scenes").param("bbox", PANTANAL).param("start", "2026-06-01")
                .param("end", "2026-11-14").param("maturity", "validated")));
        assertThat(v.get("count").asInt()).isEqualTo(3);
    }

    @Test
    void coverageSaysUnavailableWithReasonInsteadOfGuessing() throws Exception {
        mvc.perform(get("/api/arara/coverage").param("bbox", "-57.6,-18.6,-57.2,-18.2").param("start", "2026-06-02"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("available"))
                .andExpect(jsonPath("$.best_group.n_dates").value(9)).andExpect(jsonPath("$.best_group.aoi_coverage").value(1.0));
        mvc.perform(get("/api/arara/coverage").param("bbox", "10,45,10.2,45.2"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("unavailable"))
                .andExpect(jsonPath("$.reason").isNotEmpty()).andExpect(jsonPath("$.best_group").doesNotExist());
    }

    @Test
    void catalogDownIsUnavailableNotFake() throws Exception {
        ASF.resetAll();
        ASF.stubFor(com.github.tomakehurst.wiremock.client.WireMock.get(urlPathEqualTo("/services/search/param")).willReturn(aResponse().withStatus(500)));
        mvc.perform(get("/api/arara/scenes").param("bbox", "-50,-10,-49.8,-9.8"))
                .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.status").value("unavailable"))
                .andExpect(jsonPath("$.reason").isNotEmpty()).andExpect(jsonPath("$.scenes").doesNotExist());
        ASF.verify(3, getRequestedFor(urlPathEqualTo("/services/search/param")));     // 3 tentativas
    }

    @Test
    void analysisLifecycle() throws Exception {
        JsonNode created = body(mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON)
                .content(analysisBody("2026-06-01"))).andExpect(status().isAccepted()));
        String id = created.get("analysis_id").asText();
        assertThat(id).matches("[0-9a-f]{24}");
        JsonNode job = waitJob(created.get("job_id").asText());
        assertThat(job.get("status").asText()).isEqualTo("completed");
        assertThat(job.get("progress").asDouble()).isEqualTo(1.0);

        mvc.perform(get("/api/arara/analyses").param("status", "completed").param("include_superseded", "true")).andExpect(status().isOk())
                .andExpect(jsonPath("$.analyses[?(@.analysis_id=='" + id + "')].summary.net_change_ha").value(-2225.0))
                .andExpect(jsonPath("$.analyses[?(@.analysis_id=='" + id + "')].summary.wind_dates[0]").value("2026-10-09"));
        String detail = mvc.perform(get("/api/arara/analyses/" + id)).andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("completed")).andExpect(jsonPath("$.name").value("Pantanal teste"))
                .andExpect(jsonPath("$.dates[1].suspeita_vento").value(true))
                .andExpect(jsonPath("$.optical_validation.status").value("validated"))
                .andReturn().getResponse().getContentAsString();
        assertThat(detail).doesNotContain(SECRET_USER).doesNotContain(SECRET_PASS);
        mvc.perform(get("/api/arara/analyses/" + id + "/metrics").param("format", "csv")).andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("text/csv"))
                .andExpect(content().string(org.hamcrest.Matchers.startsWith("date,water_km2")));
        mvc.perform(get("/api/arara/analyses/" + id + "/metrics")).andExpect(jsonPath("$.dates[0].water_km2").value(120.5));
        mvc.perform(get("/api/arara/analyses/" + id + "/sources")).andExpect(jsonPath("$.scenes[0].crid").value("P05023"));
        mvc.perform(get("/api/arara/analyses/" + id + "/layers")).andExpect(status().isOk())
                .andExpect(jsonPath("$.layers[0].layer_id").value(id + "-change"))
                .andExpect(jsonPath("$.layers[0].tiles").value("/api/arara/tiles/" + id + "-change/{z}/{x}/{y}.png"));
        mvc.perform(get("/api/arara/tiles/" + id + "-change/6/21/35.png")).andExpect(status().isOk())
                .andExpect(content().contentType(MediaType.IMAGE_PNG));
        mvc.perform(get("/api/arara/tiles/" + id + "-change/6/0/0.png")).andExpect(status().isNotFound());
        mvc.perform(get("/api/arara/tiles/" + id + "-..%2F..%2Fspec/6/0/0.png")).andExpect(status().is4xxClientError());
        mvc.perform(get("/api/arara/analyses/" + id + "/png/change.png")).andExpect(status().isOk());

        // o mesmo pedido de novo: mesma identidade, resultado reaproveitado, sem novo job
        mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON).content(analysisBody("2026-06-01")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.analysis_id").value(id))
                .andExpect(jsonPath("$.reused").value(true)).andExpect(jsonPath("$.status").value("completed"));
    }

    @Test
    void areaWithoutReliableWaterPublishesNoWaterNumbers() throws Exception {
        for (String start : java.util.List.of("2026-06-02", "2026-06-03")) {    // pipeline nova e resultado antigo sem 'quality'
            JsonNode created = body(mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON)
                    .content(analysisBody(start))).andExpect(status().isAccepted()));
            String id = created.get("analysis_id").asText();
            assertThat(waitJob(created.get("job_id").asText()).get("status").asText()).isEqualTo("completed");
            String card = "$.analyses[?(@.analysis_id=='" + id + "')]";
            mvc.perform(get("/api/arara/analyses").param("status", "completed").param("include_superseded", "true"))
                    .andExpect(jsonPath(card + ".quality").value("no_reliable_water"))
                    .andExpect(jsonPath(card + ".summary.quality").value("no_reliable_water"))
                    .andExpect(jsonPath(card + ".summary.water_km2_last").isEmpty())
                    .andExpect(jsonPath(card + ".summary.net_change_ha").isEmpty());
            String detail = mvc.perform(get("/api/arara/analyses/" + id)).andExpect(status().isOk())
                    .andExpect(jsonPath("$.quality").value("no_reliable_water"))
                    .andExpect(jsonPath("$.quality_reasons[0]").value(org.hamcrest.Matchers.containsString("margem")))
                    .andExpect(jsonPath("$.what_to_try").isNotEmpty())
                    .andExpect(jsonPath("$.dates[0].water_km2").isEmpty())
                    .andExpect(jsonPath("$.dates[0].suspeita_vento").isEmpty())
                    .andExpect(jsonPath("$.comparison").isEmpty()).andExpect(jsonPath("$.patterns").isEmpty())
                    .andExpect(jsonPath("$.forecast").isEmpty())
                    .andExpect(jsonPath("$.layers[*].type", org.hamcrest.Matchers.everyItem(org.hamcrest.Matchers.is("backscatter"))))
                    .andReturn().getResponse().getContentAsString();
            assertThat(detail).doesNotContain("TypeError").doesNotContain("suspeita de vento (água").doesNotContain("43.29");
            mvc.perform(get("/api/arara/analyses/" + id + "/metrics").param("format", "csv"))
                    .andExpect(content().string(org.hamcrest.Matchers.startsWith("date,quality,margin_blocks")))
                    .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("120.5"))));
        }
    }

    @Test
    void redoneAnalysisSupersedesTheOldOneWithoutDeletingIt() throws Exception {
        String old = null, current = null;
        for (String start : java.util.List.of("2026-06-05", "2026-06-06")) {      // mesma área, refeita depois
            JsonNode created = body(mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON)
                    .content(analysisBody(start))).andExpect(status().isAccepted()));
            assertThat(waitJob(created.get("job_id").asText()).get("status").asText()).isEqualTo("completed");
            old = current;
            current = created.get("analysis_id").asText();
        }
        mvc.perform(get("/api/arara/analyses").param("status", "completed"))
                .andExpect(jsonPath("$.analyses[?(@.analysis_id=='" + old + "')]").isEmpty())
                .andExpect(jsonPath("$.analyses[?(@.analysis_id=='" + current + "')].superseded_by").isEmpty())
                .andExpect(jsonPath("$.analyses[?(@.bbox[0]==-57.6)]", org.hamcrest.Matchers.hasSize(1)));
        mvc.perform(get("/api/arara/analyses/" + old)).andExpect(status().isOk())          // continua acessível pelo id
                .andExpect(jsonPath("$.superseded_by").value(current))
                .andExpect(jsonPath("$.dates[0].water_km2").value(120.5));
        mvc.perform(get("/api/arara/analyses").param("include_superseded", "true"))
                .andExpect(jsonPath("$.analyses[?(@.analysis_id=='" + old + "')].superseded_by").value(current));
    }

    @Test
    void reliableAnalysisKeepsItsNumbersAndQuality() throws Exception {
        JsonNode created = body(mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON)
                .content(analysisBody("2026-06-04"))).andExpect(status().isAccepted()));
        String id = created.get("analysis_id").asText();
        waitJob(created.get("job_id").asText());
        mvc.perform(get("/api/arara/analyses/" + id)).andExpect(jsonPath("$.quality").value("reliable"))
                .andExpect(jsonPath("$.dates[0].water_km2").value(120.5)).andExpect(jsonPath("$.comparison.net_change_ha").value(-2225.0));
    }

    @Test
    void unavailableAndFailedJobsCarryTheReasonAndLeaveNothingOnDisk() throws Exception {
        JsonNode created = body(mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON)
                .content(analysisBody("1999-01-01"))).andExpect(status().isAccepted()));
        JsonNode job = waitJob(created.get("job_id").asText());
        assertThat(job.get("status").asText()).isEqualTo("unavailable");
        assertThat(job.get("reason").asText()).contains("nenhuma cena");
        String id = created.get("analysis_id").asText();
        assertThat(Files.exists(storage.dir(id))).isFalse();
        mvc.perform(get("/api/arara/analyses/" + id)).andExpect(jsonPath("$.status").value("unavailable"))
                .andExpect(jsonPath("$.reason").isNotEmpty()).andExpect(jsonPath("$.dates").doesNotExist());
        mvc.perform(get("/api/arara/analyses/" + id + "/metrics")).andExpect(status().isNotFound());

        JsonNode failed = body(mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON)
                .content(analysisBody("1998-01-01"))).andExpect(status().isAccepted()));
        assertThat(waitJob(failed.get("job_id").asText()).get("status").asText()).isEqualTo("failed");
    }

    @Test
    void invalidRequestsAreRejectedWithReason() throws Exception {
        mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"bbox\":\"-58,-19,-56,-17\"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.reason").value(org.hamcrest.Matchers.containsString("limite")));
        mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isBadRequest());
        mvc.perform(post("/api/arara/analysis").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"bbox\":\"" + PANTANAL + "\",\"start\":\"ontem\"}")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/arara/scenes")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/arara/jobs/nao-existe")).andExpect(status().isNotFound());
        mvc.perform(get("/api/arara/analyses/zzzz")).andExpect(status().isNotFound());
    }

    @Test
    void orphanJobsAreRequeuedOnRestart() throws Exception {
        Instant now = Instant.now();
        String id = "0123456789abcdef01234567";
        repo.upsert(new AnalysisRepository.Analysis(id, id, "órfã", JobStatus.PROCESSING,
                "{\"type\":\"Polygon\",\"coordinates\":[[[-57.6,-18.6],[-57.2,-18.6],[-57.2,-18.2],[-57.6,-18.2],[-57.6,-18.6]]]}",
                -57.6, -18.6, -57.2, -18.2, 1900, "2026-06-01", "2026-11-14", null, null, "arara-water-0.1.0",
                null, null, null, now, now, null, null));
        repo.insert(new AnalysisRepository.Job("job-orfao", id, JobStatus.PROCESSING, "classify", 0.6, "no meio", null, now, now));
        service.recoverOrphans();
        assertThat(waitJob("job-orfao").get("status").asText()).isEqualTo("completed");
        assertThat(repo.find(id).orElseThrow().status()).isEqualTo(JobStatus.COMPLETED);
    }

    @Test
    void configNeverLeaksCredentialsAndGlobeIsServed() throws Exception {
        String cfg = mvc.perform(get("/api/arara/config")).andExpect(status().isOk())
                .andExpect(jsonPath("$.on_demand_available").value(true)).andReturn().getResponse().getContentAsString();
        assertThat(cfg).doesNotContain(SECRET_USER).doesNotContain(SECRET_PASS);
        mvc.perform(get("/index.html")).andExpect(status().isOk());
        mvc.perform(get("/furnas/index.html")).andExpect(status().isOk());
    }

    @Test
    void globeLibrariesAreLocalAndCachedWhileHtmlRevalidates() throws Exception {
        String html = mvc.perform(get("/index.html")).andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", org.hamcrest.Matchers.containsString("no-cache")))
                .andReturn().getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8);
        assertThat(html).contains("vendor/globe.gl/globe.gl.min.js").doesNotContain("cdn.jsdelivr.net/npm/globe.gl")
                .contains("function loadBasins()");   // bacias de Minas só sob demanda
        mvc.perform(get("/vendor/globe.gl/globe.gl.min.js")).andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", org.hamcrest.Matchers.containsString("max-age=604800")));
        mvc.perform(get("/vendor/three/three.core.min.js")).andExpect(status().isOk());
        mvc.perform(get("/geo.json")).andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", org.hamcrest.Matchers.containsString("max-age=86400")));
        mvc.perform(get("/favicon.ico")).andExpect(status().isOk())          // sem 404 de favicon no app
                .andExpect(header().string("Cache-Control", org.hamcrest.Matchers.containsString("max-age=86400")));
    }
}
