# Como rodar

## Requisitos

- Python 3.11+ e JDK 21 ou mais novo (testado com Python 3.14 e JDK 25; o Maven vem pelo `mvnw`).
- Conta Earthdata (https://urs.earthdata.nasa.gov) para ler as cenas NISAR. O catálogo funciona sem ela.

## Instalação

```
python3 -m venv .venv
.venv/bin/pip install -r pipeline/requirements-dev.txt
cp .env.example .env
```

Preencha `EARTHDATA_USERNAME` e `EARTHDATA_PASSWORD` no `.env`. O arquivo não é versionado e as
credenciais só existem no backend, que as repassa à pipeline pelo ambiente do processo.

## Subir a aplicação

```
./backend/mvnw -f backend spring-boot:run
```

- Globo: http://localhost:8080/
- Furnas: http://localhost:8080/furnas/
- Estado do servidor: http://localhost:8080/api/arara/config (`on_demand_available` diz se há credenciais)

No globo: busque um lugar ou use **Minha área** para desenhar um polígono de até 2.500 km². O painel
mostra as cenas disponíveis; **Analisar água nesta área** cria o job. Ao terminar, a área vira um card.

## API

| Método | Caminho | Para quê |
|---|---|---|
| GET | `/api/arara/scenes?bbox=o,s,l,n&start=&end=&maturity=` | cenas e grupos de geometria |
| GET | `/api/arara/coverage?bbox=...` | há geometria que cobre 95% da área? |
| POST | `/api/arara/analysis` | `{name, aoi \| bbox, start, end, group_id?, maturity?}` |
| GET | `/api/arara/jobs/{id}` | queued, downloading, processing, completed, failed, unavailable |
| GET | `/api/arara/analyses?status=completed` | cards |
| GET | `/api/arara/analyses/{id}` | resultado completo |
| GET | `/api/arara/analyses/{id}/metrics?format=csv` | métricas |
| GET | `/api/arara/analyses/{id}/layers`, `/sources` | camadas e proveniência |
| GET | `/api/arara/tiles/{id}-{camada}/{z}/{x}/{y}.png` | tiles XYZ |

## Pipeline sem o backend

```
PYTHONPATH=pipeline .venv/bin/python -m arara_pipeline.run --spec spec.json --out saida/
```

`spec.json`: `{"analysis_id", "aoi": <GeoJSON>, "start", "end"}`. Com `"local_scenes": [arquivos .h5]`
usa cenas do disco em vez do catálogo. O progresso sai em JSON Lines e o resultado em `saida/result.json`.

## Testes

```
.venv/bin/python -m pytest pipeline/tests -q
./backend/mvnw -f backend test
```

A regressão de Furnas com as cenas reais só roda com `FURNAS_H5_DIR` (pasta dos 9 `.h5`) e
`FURNAS_POLIGONO` (o `Furnas.gdb` ou o GeoJSON gerado por `pipeline/scripts/exportar_poligono.py`).

## Dados em disco

Derivados ficam em `data/analyses/{id}/` e são apagados após 7 dias (`ARARA_RETENTION_DAYS`). As
janelas brutas só existem em memória durante o job. Limites em `.env.example`.
