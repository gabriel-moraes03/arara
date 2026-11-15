# Histórico

O que mudou em cada versão do algoritmo (`ALGORITHM_VERSION` na pipeline, `arara.algorithm-version` no
backend). A versão entra no id da análise: mudar de versão gera análises novas, e as antigas ficam
superadas, sem ser apagadas.

## `arara-water-0.3.0` (15/11/2026)

Foco em cheias no Sul do Brasil, contexto para interpretar a água e desempenho.

- **Modo cheia** (`cheia.py`): a zona de água dos reservatórios (núcleo recorrente dilatado 1 km) apaga
  inundação, que é água não recorrente. Agora toda análise também mede, por passagem, a **água além da
  passagem mais seca sem vento** (referência dilatada 2 px), só em terreno baixo (HAND ≤ 15 m, GLO-30 HAND),
  sem manchas < 0,1 km², e a **possível vegetação alagada** (HH ≥ 3 dB acima da mediana da série, HAND ≤ 10 m,
  ≥ 4 passagens). Camadas `flood_AAAAMMDD`. A área de água dos reservatórios continua igual.
- **Semente adaptativa da margem água/terra**: tenta −20, −18 e −16 dB e fica com a mais escura que acha
  ≥ 5 blocos de margem; nas sementes de reserva o bloco precisa ter ≥ 20% de pixels 6 dB acima da semente
  (terra nítida). No delta do Jacuí (trilha 53 D, pixel de 10 m) a água tem mediana de −16 dB e 10% da
  terra fica abaixo de −12 dB: com −20 dB fixo não havia margem e o limiar caía no Otsu (−9,4 dB,
  `no_reliable_water`); agora sai entre −12,3 e −13,9 dB, onde o corte bate melhor com o Sentinel-2
  (IoU 0,66–0,72 medido em 16/08 e 15/10). Furnas e Três Marias acham margem em −20 dB e não mudam.
- **Chuva** (`chuva.py`): GPM IMERG Late diário (0,1°) por OPeNDAP, soma de 3 e 7 dias antes de cada
  passagem. Sem autorização do GES DISC na conta Earthdata, sai `unavailable` com o motivo.
- **Municípios** (`municipios.py`): km² de cheia por município no pico, com a população do Censo 2022
  (IBGE). É a população do município inteiro, não de pessoas atingidas.
- **Confiança por passagem** (alta, média, baixa, com os motivos) e **resumo em linguagem simples**
  (`leitura.py`), montados por regras a partir dos números, sem IA.
- **Desempenho**: cache local por passagem (radar em dB da janela, chave cena + CRID + área + passo +
  filtro), leitura das passagens que faltam em 3 processos paralelos, Sentinel-2 com 4 datas por vez e
  cache por data, HAND e chuva em cache. O filtro 5×5 passa a ser aplicado na janela inteira antes do
  recorte para a grade comum (muda só pixels a até 2 px da borda da janela, 1 km fora da área).
  `timings_s` e `cache` no resultado. Backend: monitor das regiões (`regioes.json`) que reanalisa quando
  o catálogo tem passagem nova; relatório em `GET /api/arara/monitor`. A seleção de área no globo e o
  `POST /api/arara/analysis` saíram (decisão do time): as análises das regiões vêm só do monitor.
- **Banco PostgreSQL** (`docker-compose.yml`) no lugar do H2 em arquivo, com a tabela `observation`: uma
  linha por passagem de cada análise concluída, que sobrevive à limpeza dos arquivos e às análises
  superadas. `GET /api/arara/regions/{id}/history` (JSON ou CSV). O banco H2 antigo é importado na
  primeira subida; os testes seguem em H2 no modo PostgreSQL.
- **Globo** refeito para as cheias do Sul: lista de regiões ordenada pela cheia, mapa de satélite com a
  camada de cheia, linha do tempo das passagens (cheia, chuva, confiança, vento), comparação deslizante
  com a passagem mais seca.

## `arara-water-0.2.1` (15/11/2026)

- **Permanência sem datas de vento**, como a tendência. Antes, um único dia de vento em 9 deixava cada
  pixel com água em 8/9 = 89% das datas, abaixo dos 90% de "permanente": Furnas saía com 0 km² permanente.
  Agora 114,9 km² permanente / 68,8 sazonal, em 8 datas (1 com vento fora).
- **Alerta da última passagem preso ao ruído da série**: só sobe para atenção/alerta se o desvio sai da
  faixa p10–p90 dos resíduos das datas anteriores **e** passa o ruído entre passagens (mediana das
  variações entre passagens calmas, o mesmo número da leitura). Senão: "dentro da variação normal". Furnas
  dizia "atenção" (z −2,3) enquanto a leitura dizia "dentro do ruído"; o desvio era 12,9 km² contra um
  ruído de 15,1 km². Se primeira × última está dentro do ruído mas a última saiu da faixa, a leitura diz
  as duas coisas.
- **Tabela radar × Sentinel-2**: "concordam" só com diferença de fração < 5 pontos percentuais e sem
  divergência; "óptico sem água" quando o Sentinel-2 vê ~0 e o radar ≥ 5%, inclusive em data de vento
  (Nanuque 21/07, 24,7% × 0%, aparecia "concordam"). O backend preenche o rótulo em resultados antigos.
- **Análises superadas**: refazer a mesma área (mesmo retângulo) marca a anterior com `superseded_by`,
  sem apagar; ela sai dos cards e do globo e continua aberta pelo id, com aviso e link para a atual.
- **Vitrine**: o painel não fala em catálogo "ao vivo" no modo sem servidor; `favicon.ico` no app e na
  vitrine.

## `arara-water-0.2.0` (15/11/2026)

- **Estado de qualidade** em toda análise: `reliable`, `experimental` ou `no_reliable_water`, com os
  motivos (regras em [COMO_RODAR.md](COMO_RODAR.md#qualidade-de-cada-análise)). O backend reavalia
  resultados antigos (sem o campo) a partir dos números gravados e nunca promove uma análise.
- **Validação óptica**: a média por métrica ignora datas sem valor (0/0 quando nenhum sensor vê água) e diz
  quantas datas entraram em cada uma. "Óptico sem água, radar com água" é divergência forte e alimenta o
  `no_reliable_water`. Falha de etapa vai para o log do servidor; o usuário vê só "validação óptica
  indisponível nesta análise".
- **Progresso em UTF-8** entre a pipeline e o backend (`PYTHONIOENCODING`, `PYTHONUTF8` e `reconfigure`).
- **Primeira carga do globo**: `globe.gl`, `three` e `topojson` servidos localmente, fontes sem bloquear a
  página, bacias de Minas carregadas só ao abrir o seletor, buscar ou aproximar de Minas, gzip e cache HTTP
  nos arquivos estáticos. Chrome headless, cache vazio, localhost: 3,9 s antes, ~1,5 s depois.
- **Vitrine estática** (`scripts/exportar_vitrine.py`): o mesmo frontend lendo análises exportadas, sem servidor.
- **Máscara de terreno** para os falsos positivos do Lake Mead: medida e **não ligada** (ver
  [LIMITACOES.md](LIMITACOES.md#máscara-de-terreno-medida-não-ligada)).

## `arara-water-0.1.0`

Primeira versão do fluxo global: catálogo da ASF, leitura de janelas GCOV por streaming, limiar bimodal
nos blocos de margem, comparação entre datas, validação com o Sentinel-2, padrões, projeção e publicação.
