# Arara

Onde a água avançou ou recuou, vista pelo radar NISAR (banda L). O usuário escolhe uma área no globo, o
Arara consulta o catálogo da NASA ao vivo, lê só a janela daquela área em cada cena, classifica a água,
compara as datas, confere com o Sentinel-2 e publica o resultado no globo.

Escopo: **só água**. Tudo o que aparece é medido; quando o dado real não pode ser obtido, a resposta é
`unavailable` com o motivo.

## Como funciona

```
globo (frontend/globe)  ──►  API Spring Boot (backend)  ──►  pipeline Python (pipeline/arara_pipeline)
   área + período             catálogo ASF, fila de jobs       janela GCOV por streaming → água → mudança
   painel e histórico         H2 + derivados em data/          → Sentinel-2 → COG, PNG, tiles, métricas
```

| Pasta | O que tem |
|---|---|
| `backend/` | Spring Boot 3.5, Java 21. API `/api/arara`, fila de um job pesado, H2 + Flyway |
| `pipeline/arara_pipeline/` | catálogo, leitura de janelas, classificação, comparação, óptico, projeção, publicação |
| `pipeline/scripts/` | scripts do estudo de Furnas |
| `frontend/globe/` | globo, servido em `/` |
| `frontend/furnas/` | estudo validado de Furnas, servido em `/furnas/` |
| `data/ana/`, `regression/furnas/` | cota × área da ANA e números de referência de Furnas |
| `terrapulse/` | projeto de origem, somente leitura |

## Rodar

Ver [docs/COMO_RODAR.md](docs/COMO_RODAR.md). Em resumo:

```
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements-dev.txt
cp .env.example .env            # preencha EARTHDATA_USERNAME e EARTHDATA_PASSWORD
./backend/mvnw -f backend spring-boot:run      # http://localhost:8080/
```

## Método

Canal HH em potência linear → dB uma única vez → média 5×5 em dB → limiar no vale água/terra dos blocos
de margem (um limiar por série) → água recorrente dilatada 1 km ∩ área pedida → manchas < 0,1 km² fora.
Uma análise usa uma única coleção e uma única geometria (trilha, direção, frame). Datas com suspeita de
vento ficam marcadas, sem correção. Validado em Furnas contra a cota × área da ANA: erro médio de 1,0%
nas 7 datas calmas.

Limitações conhecidas: [docs/LIMITACOES.md](docs/LIMITACOES.md).
