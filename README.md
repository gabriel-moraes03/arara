<p align="center"><img src="frontend/globe/img/arara-marca.png" alt="Arara" width="96"></p>

# Arara

Onde a água saiu do leito no Sul do Brasil, vista pelo radar NISAR (banda L), que enxerga através de
nuvem e chuva. Para cada região monitorada (Guaíba, Taquari, Sinos, Caí, Jacuí, Pelotas, Uruguaiana,
Itajaí, Iguaçu), o Arara lê só a janela daquela região em cada passagem do satélite, separa água de terra,
mede a **água além da passagem mais seca** (cheia) e a possível vegetação alagada, soma a **chuva** do GPM
antes de cada passagem, cruza com os **municípios** do IBGE, confere com o Sentinel-2 e dá uma
**confiança** a cada número. Um monitor no servidor analisa as regiões quando o NISAR passa de novo; o
cache faz cada atualização ler na NASA só a passagem nova.

O globo é para explorar as regiões e os estudos concluídos: a seleção de áreas personalizadas e a criação
de análises pela API pública foram removidas. A pipeline e os resultados existentes continuam disponíveis.

Tudo o que aparece é medido; quando o dado real não pode ser obtido, a resposta é `unavailable` com o
motivo. Medida separada de causa: o radar diz onde há água a mais, não por quê.

## Como funciona

```
globo (frontend/globe)  ──►  API Spring Boot (backend)  ──►  pipeline Python (pipeline/arara_pipeline)
   área + período             catálogo ASF, fila de jobs       janela GCOV por streaming → água → mudança
   painel e histórico         H2 + derivados em data/          → Sentinel-2 → COG, PNG, tiles, métricas
```

| Pasta | O que tem |
|---|---|
| `backend/` | Spring Boot 3.5, Java 21. API `/api/arara`, fila de um job pesado, H2 + Flyway |
| `pipeline/arara_pipeline/` | catálogo, leitura de janelas, classificação, qualidade, comparação, óptico, padrões, projeção, publicação |
| `pipeline/scripts/` | ferramentas de linha de comando: estudo de Furnas, estudos em lote, bacias de MG, medição de terreno |
| `pipeline/tests/` | testes da pipeline (a regressão de Furnas com cenas reais roda com `FURNAS_H5_DIR`) |
| `frontend/globe/` | globo, servido em `/` (logo e favicon em `img/` e `favicon.ico`) |
| `frontend/estudo/` | estudo automático de qualquer análise concluída, em `/estudo/index.html?id=<id>` |
| `frontend/furnas/` | estudo validado de Furnas, servido em `/furnas/` |
| `scripts/exportar_vitrine.py` | vitrine estática (o mesmo frontend, sem servidor) para GitHub Pages |
| `data/ana/`, `regression/furnas/` | cota × área da ANA e números de referência de Furnas |

## Documentação

- [docs/COMO_RODAR.md](docs/COMO_RODAR.md): instalação, servidor, API, qualidade das análises, testes, vitrine.
- [docs/LIMITACOES.md](docs/LIMITACOES.md): o que foi verificado, onde o método erra e o que não faz.
- [docs/HISTORICO.md](docs/HISTORICO.md): o que mudou em cada versão do algoritmo.
- [regression/furnas/RESUMO.md](regression/furnas/RESUMO.md): o estudo de Furnas contra a ANA.

## Rodar

Em resumo (detalhes e Windows em [docs/COMO_RODAR.md](docs/COMO_RODAR.md)):

```
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements-dev.txt
cp .env.example .env            # preencha EARTHDATA_USERNAME e EARTHDATA_PASSWORD
./backend/mvnw -f backend spring-boot:run      # http://localhost:8080/
```

## Método

Canal HH em potência linear → dB uma única vez → média 5×5 em dB → limiar no vale água/terra dos blocos
de margem (um limiar por série) → água recorrente dilatada 1 km ∩ área pedida → manchas < 0,1 km² fora.
Uma análise usa uma única coleção e uma única geometria (trilha, direção, frame). Datas com suspeita de
vento ficam marcadas, sem correção. Cada análise sai `reliable`, `experimental` ou `no_reliable_water`,
com os motivos. Validado em Furnas contra a cota × área da ANA: erro médio de 1,0% nas 7 datas calmas.

## Licença

MIT, ver [LICENSE](LICENSE).
