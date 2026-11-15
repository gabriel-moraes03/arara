# Histórico

O que mudou em cada versão do algoritmo (`ALGORITHM_VERSION` na pipeline, `arara.algorithm-version` no
backend). A versão entra no id da análise: mudar de versão gera análises novas, e as antigas ficam
superadas, sem ser apagadas.

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
