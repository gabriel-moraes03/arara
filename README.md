<p align="center"><img src="frontend/globe/img/arara-marca.png" alt="Arara" width="96"></p>

# Arara

**Arara is a flood monitor for southern Brazil built on NISAR, the NASA–ISRO L-band radar satellite.**
Radar measures day or night, with or without clouds, which is exactly when floods happen. For each
monitored region (Guaíba, Taquari, Sinos, Caí, Jacuí, Pelotas, Uruguaiana, Itajaí, Iguaçu), Arara reads
only that region's window from each satellite pass, separates water from land, measures the **water
beyond the driest pass** (flooding) and possible flooded vegetation, adds the **rainfall** (GPM IMERG)
before each pass, crosses the result with **municipalities** (IBGE), checks it against Sentinel-2 and
gives every number a **confidence** level. A server-side monitor re-analyses a region when NISAR passes
again; the cache makes each update read from NASA only the new pass.

The globe is for exploring the regions and the finished studies: custom area selection and creating
analyses through the public API were removed. The pipeline and the existing results remain available.

Everything shown is measured. When real data cannot be obtained, the answer is `unavailable`, with the
reason. Measurement is kept separate from cause: the radar says where there is extra water, not why.

- Live showcase (static, GitHub Pages): `<VITRINE_URL>`
- Video: `<VIDEO_URL>`

## Validation

**Main validation: Furnas reservoir (MG).** Nine NISAR GCOV passes (track 24 D, frame 99, June–October
2026), checked against the official ANA level–area curve (CAV) at the ANA water level of each date.
- Mean absolute error: **1.0%** (10.4 km²) on the 7 calm dates.
- Sensitivity to water level: 47 km²/m measured by NISAR against 45 km²/m in the ANA curve.
- Two windy dates are flagged, not hidden.

Details: [regression/furnas/RESUMO.md](regression/furnas/RESUMO.md) and the story page `frontend/furnas/`.

**Second study (experimental): Barra Grande and Machadinho (Pelotas/Uruguay rivers, RS/SC).** Between
29 June and 11 July 2026, winter rains raised Barra Grande by 14.3 m and Machadinho by 9.3 m. Seven NISAR
passes (track 53 D, frame 102) were measured with the Furnas-validated method (`arara-water-0.2.1`) and
checked against ANA's water level (SAR) and CAV.
- **What the radar gets right:** the timing and direction of the refill. The correlation between water
  level and area is r = 0.98 (Barra Grande) and 0.85 (Machadinho). The noise (standard deviation of the
  differences) is 5.2 and 2.9 km².
- **What it gets wrong:** it underestimates the area of these narrow canyon reservoirs. The mean
  absolute error is 20.0% and 25.7% at 40 m. A resolution sensitivity run at 20 m brings it to 9.5% and
  15.9% (5×5 filter), or 7.0% and 12.1% (3×3); the 40 m result stays the official one.
- The study is therefore labelled **experimental**.

Details: [regression/barra_machadinho/RESUMO.md](regression/barra_machadinho/RESUMO.md) and the page
`frontend/uruguai/`.

## Flood monitor: what it measures and its limits

- **Flood water** = open water beyond the driest calm pass of the period. A flood that lasted the whole
  period is invisible, because it is in the reference.
- **Low terrain only:** flood water is counted only where HAND ≤ 15 m (GLO-30 HAND).
- **Flooded vegetation is "possible", never certain:** HH at least 3 dB above the series median, with
  HAND ≤ 10 m. Wet soil, irrigation and crop changes also brighten HH; irrigated rice can look like open
  water or like flooded vegetation, depending on the crop stage.
- **Delta do Jacuí (track 53 D):** water and smooth land (marsh, rice, fields) overlap in brightness.
  The best cut against Sentinel-2 reaches IoU 0.66–0.72, so separating water from land there is hard.
- **Rainfall** is GPM IMERG Late, a satellite estimate with ~11 km cells, summed over the 3 and 7 days
  before each pass. It is context, not a cause.
- **Municipal population** is the population of the whole municipality (IBGE), not the number of people
  affected.
- NISAR products are still provisional. Every analysis is labelled `reliable`, `experimental` or
  `no_reliable_water`, with the reasons.

Full list (in Portuguese): [docs/LIMITACOES.md](docs/LIMITACOES.md).

## Data

| Data | Use | Source |
|---|---|---|
| NISAR L2 GCOV (provisional collection `NISAR_L2_GCOV_PROVISIONAL_V1`) | radar backscatter (HH, HV) | [ASF DAAC](https://nisar-docs.asf.alaska.edu/), [ASF search API](https://api.daac.asf.alaska.edu/services/search/param) |
| ANA SAR (MedicaoSin) | official daily reservoir water level and storage | [ANA SAR](https://www.ana.gov.br/sar/) |
| ANA CAV (SNIRH) | official level–area–volume curves and reservoir outlines | [ANA/SNIRH metadata](https://metadados.snirh.gov.br/geonetwork/srv/api/records/b8f0487a-df73-4f8d-8b22-bb49cf9f3683) |
| ANA/ONS reservoir bulletins | Furnas water level | [ANA situation room](https://www.gov.br/ana/pt-br/sala-de-situacao/sistemas-hidricos-dos-rios-grande-e-paranaiba), [ONS](https://www.ons.org.br/) |
| GPM IMERG Late (daily) | rainfall before each pass | [NASA GES DISC](https://gpm1.gesdisc.eosdis.nasa.gov/opendap/) |
| IBGE | municipalities and population | [IBGE data API](https://servicodados.ibge.gov.br/api) |
| Sentinel-2 L2A | independent optical check (MNDWI) | [Earth Search STAC](https://earth-search.aws.element84.com/v1/search) |
| Copernicus GLO-30 DEM and HAND | low-terrain mask for flood water | [GLO-30 HAND](https://glo-30-hand.s3.amazonaws.com/), [Copernicus DEM](https://copernicus-dem-30m.s3.amazonaws.com/) |

## How it works

```
globe (frontend/globe)  ──►  Spring Boot API (backend)  ──►  Python pipeline (pipeline/arara_pipeline)
   regions + studies           ASF catalog, region monitor,     streamed GCOV window → water → flood
   timeline and history        PostgreSQL + derivatives in       → rain, municipalities, Sentinel-2
                               data/                             → COG, PNG, tiles, metrics
```

| Folder | Contents |
|---|---|
| `backend/` | Spring Boot 3.5, Java 21. API `/api/arara`, region monitor, PostgreSQL (Docker Compose) + Flyway |
| `pipeline/arara_pipeline/` | catalog, window reads, classification, flood mode, rain, municipalities, quality, Sentinel-2, publishing (`arara-water-0.3.0`) |
| `pipeline/scripts/` | command-line tools: Furnas study, Barra Grande/Machadinho study and resolution sensitivity, batch studies, terrain measurement |
| `pipeline/tests/` | pipeline tests (the Furnas regression with real scenes runs with `FURNAS_H5_DIR`) |
| `frontend/globe/` | globe, served at `/`; the regions are listed in `regioes.json` |
| `frontend/estudo/` | automatic study of any finished analysis, at `/estudo/index.html?id=<id>` |
| `frontend/furnas/` | validated Furnas study, at `/furnas/` |
| `frontend/uruguai/` | experimental Barra Grande and Machadinho study (EN/PT), at `/uruguai/` |
| `scripts/exportar_vitrine.py` | static showcase (the same frontend, no server) for GitHub Pages |
| `data/ana/`, `regression/` | ANA level–area curves, outlines and water levels; reference numbers for Furnas and Barra Grande/Machadinho |
| `docker-compose.yml` | the PostgreSQL database for development, bound to 127.0.0.1 only |
| `deploy/` | production package for a VPS: backend image, Postgres, Caddy (HTTPS), seeds loader, [DEPLOY.md](deploy/DEPLOY.md) |

## Running

Requirements: Python 3.11+, JDK 21 (newer works; the Maven wrapper is included), Docker with Compose,
and an [Earthdata](https://urs.earthdata.nasa.gov) account to read NISAR scenes.

```
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements-dev.txt
cp .env.example .env     # fill EARTHDATA_USERNAME, EARTHDATA_PASSWORD and ARARA_DB_PASSWORD
docker compose up -d     # PostgreSQL on 127.0.0.1:5432
./backend/mvnw -f backend spring-boot:run      # http://localhost:8080/
```

- The backend needs **JDK 21**. If your default Java is older, point `JAVA_HOME` to a JDK 21 for the
  `mvnw` commands.
- On Windows the venv Python is `.venv\Scripts\python.exe`: set `ARARA_PYTHON=../.venv/Scripts/python.exe`
  in `.env`. Change the port with `ARARA_PORT`.
- Credentials live only in `.env` (never committed) and in the backend process environment.

Tests and static showcase:

```
.venv/bin/python -m pytest pipeline/tests -q
./backend/mvnw -f backend test
python scripts/exportar_vitrine.py --servidor http://localhost:8080 --ids <analysis ids>
python -m http.server 8090 -d dist/vitrine
```

Everything above was run on the team's machine (Windows, JDK 21, Docker Desktop).

**Hosting (VPS).** `deploy/` runs Arara in *event mode* (`SPRING_PROFILES_ACTIVE=event`): Postgres,
the backend (which also serves the frontend) and Caddy with automatic HTTPS, preloaded with the finished
analyses. The region monitor is off, so nothing is processed on the server and no Earthdata credentials
are needed. Step by step (in Portuguese): [deploy/DEPLOY.md](deploy/DEPLOY.md).

## Documentation

The documents in `docs/` are in **Portuguese**:

- [docs/COMO_RODAR.md](docs/COMO_RODAR.md): installation, server, API, analysis quality, tests, showcase.
- [docs/LIMITACOES.md](docs/LIMITACOES.md): what was verified, where the method fails and what it does not do.
- [docs/HISTORICO.md](docs/HISTORICO.md): what changed in each algorithm version.
- [regression/furnas/RESUMO.md](regression/furnas/RESUMO.md): the Furnas study against ANA.
- [regression/barra_machadinho/RESUMO.md](regression/barra_machadinho/RESUMO.md): the Barra Grande and Machadinho study against ANA.

## Method

HH channel in linear power → dB once → 5×5 mean in dB → one water/land threshold per series, at the
valley of the shoreline blocks → water inside the area. Flood mode then compares each pass with the
driest calm pass, on low terrain only. One analysis uses a single collection and a single geometry
(track, direction, frame). Dates with suspected wind are flagged, never corrected or hidden.

## Use of AI

We used AI tools (Anthropic's Claude) as assistants in two ways: to help us understand the NISAR data
(product structure, HDF5 layout, radar concepts such as backscatter and decibel conversion) and to help
build the application (code, tests, documentation and review). The interpretation of the problem and the
idea behind Arara are our own: the choice of tracking water with radar, the focus on floods and
reservoirs in southern Brazil, and the decision to validate against official ANA data. AI-assisted
outputs were reviewed and tested by the team, and all reported results come from real NISAR data
processed by our pipeline.

## Team

`<TEAM>`

## License

MIT, see [LICENSE](LICENSE).
