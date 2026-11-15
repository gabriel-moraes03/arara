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

No Windows o Python da venv fica em `.venv\Scripts\python.exe`: ponha `ARARA_PYTHON=../.venv/Scripts/python.exe`
no `.env`. A porta muda com `ARARA_PORT` (ex.: `ARARA_PORT=8081`).

## Subir a aplicação

```
./backend/mvnw -f backend spring-boot:run
```

- Globo: http://localhost:8080/
- Furnas: http://localhost:8080/furnas/
- Estado do servidor: http://localhost:8080/api/arara/config (`on_demand_available` permanece `false`, pois a criação pública de análises foi removida)

No globo, explore as regiões e abra os estudos concluídos. A seleção de áreas personalizadas
(desenho, retângulo, importação e criação por coordenadas) e a criação de análises pela API pública
foram removidas. A busca por coordenadas continua disponível apenas para navegar no mapa.

## API

| Método | Caminho | Para quê |
|---|---|---|
| GET | `/api/arara/scenes?bbox=o,s,l,n&start=&end=&maturity=` | cenas e grupos de geometria |
| GET | `/api/arara/coverage?bbox=...` | há geometria que cobre 95% da área? |
| GET | `/api/arara/jobs/{id}` | queued, downloading, processing, completed, failed, unavailable |
| GET | `/api/arara/analyses?status=completed` | cards (só a análise mais recente de cada área; `&include_superseded=true` lista as superadas) |
| GET | `/api/arara/analyses/{id}` | resultado completo (uma análise superada continua aqui, com `superseded_by`) |
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

Quando a mesma área (mesmo retângulo) é analisada de novo, a análise anterior não é apagada: fica marcada
como superada (`superseded_by`), sai dos cards e do globo e continua aberta pelo id, com um aviso e um link
para a atual. O espaço total das análises é limitado por `ARARA_DISK_LIMIT_MB` (padrão 4096); acima
dele, novos pedidos respondem `unavailable`.

## Bacias de Minas

`pipeline/scripts/exportar_bacias.py` baixa as 43 Circunscrições Hidrográficas do GeoServer da IDE-Sisema/IGAM e
grava `frontend/globe/bacias_mg.json` (contorno simplificado para exibir, não para medir). No globo, dentro de
Minas, o botão **Bacias / Municípios** alterna a divisão.

## Estudo automático (o estudo de Furnas, para qualquer área)

Toda análise concluída tem uma página de estudo: `http://localhost:8080/estudo/index.html?id=<analysis_id>`
(botão "Abrir estudo completo" no painel). As seções são as do estudo de Furnas, montadas só com o que a
análise mediu: abertura com mapa e camadas, números principais, padrões (tendência em km²/semana, alerta
da última passagem, permanência da água, os 3 trechos que mais secaram), linha do tempo com reprodução,
antes × depois, série e validação com o Sentinel-2, medido × hipótese, limitações e fontes (cenas, CRID).

O script legado `pipeline/scripts/estudar_lote.py` depende do endpoint de criação removido e não
é compatível com esta versão. A pipeline pode ser executada diretamente conforme a seção acima.

## Vitrine estática (GitHub Pages)

A vitrine é o mesmo `frontend/` (globo, estudo automático e Furnas) lendo análises já concluídas de
arquivos, sem backend, pipeline ou credencial. Ela não consulta o catálogo da NASA: ao clicar numa área sem
estudo, o painel informa que a vitrine exibe apenas estudos concluídos.

1. Com o servidor no ar e as análises concluídas, gere a pasta (ids em `/api/arara/analyses`):

   ```
   .venv/bin/python scripts/exportar_vitrine.py --servidor http://localhost:8080 --ids <id1> <id2> ...
   ```

   Sai em `dist/vitrine/` (fora do Git): páginas copiadas com `window.ARARA_STATIC = true`, e para cada
   análise `data/analyses/<id>/` com `analysis.json`, `sources.json`, `metrics.json`, `metrics.csv` e os
   PNG das camadas.
2. Teste sem backend: `python -m http.server 8090 -d dist/vitrine` e abra `http://localhost:8090/`.
   Numa página do servidor, `?static=1` também liga o modo (útil para depurar).
3. Publique o conteúdo de `dist/vitrine/` no GitHub Pages, por exemplo:
   - branch `gh-pages` com o conteúdo da pasta na raiz (Settings → Pages → Deploy from a branch →
     `gh-pages` / `root`); ou
   - um workflow com `actions/upload-pages-artifact` apontando para `dist/vitrine` e `actions/deploy-pages`.

   A pasta já tem `.nojekyll`, e todos os links são relativos, então funciona em
   `https://<usuario>.github.io/<repositorio>/`. O link é público, sem senha nem cadastro.
