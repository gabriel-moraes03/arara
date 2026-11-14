# TerraPulse — contexto para continuar o código

> Documento de passagem de bastão para o Claude Code. Atualizado em 14/11/2026, tarde (horário de Brasília).
> Hackathon NASA Space Apps 2026, desafio **"Dancing with the SARs"**. Entrega: **domingo 15/11/2026, 23:59 (horário local)**.

## 0. Decisões congeladas (14/11, tarde)

Não reabrir sem motivo forte.

- **Método oficial:** HH filtrado (média 5×5 em dB) **< −15,6 dB**, contado **só dentro do polígono oficial da ANA, sem buffer**, removendo **manchas < 0,1 km²**. O limiar é único para as 9 datas.
  ```powershell
  python scripts/area_agua.py --poligono data/ana/furnas/Furnas.gdb --buffer 0 --limiar -15.65 --saida outputs/furnas_poligono_b0
  ```
  Atenção: o padrão do script ainda é `--buffer 500`. Passe sempre `--buffer 0`.
- **07/09 e 01/10** ficam marcadas como **"suspeita: possível vento"**. A água aparece 2–2,5 dB mais clara e uniforme, e a área cai sem que a cota explique. As datas continuam no gráfico, marcadas, mas ficam fora das métricas principais.
- **Funil fora do pipeline.** Só 21% do lago tem dado válido na trilha 024 D (a borda leste da passagem corta o lago). Não há grupo de controle nesta entrega.
- **Resultado principal:**
  - Nas 7 datas sem suspeita, o erro absoluto médio contra a curva cota × área da ANA é **1,0% (10 km²)**, com ruído (desvio padrão das diferenças) de ~12 km².
  - A inclinação área × cota medida é **47 km²/m**; a da curva ANA é **45 km²/m**.
  - A cota caiu **0,87 m** (763,72 → 762,85 m), o que corresponde a ~40 km² de área esperada.
  - **História do app:** "Furnas ficou estável em 2026 e o NISAR mediu isso com 1% de erro."
- **Entrega:** app web **estático** em `web/` (story map + modo explorar), com os dados em `web/data/`. A pasta `web/` ainda não existe.

## 1. O que estamos construindo

Um app web interativo e open-source (MIT) que mostra a **área de água do lago da hidrelétrica de Furnas (MG)** ao longo da seca de 2026 e do começo das chuvas (27/06 a 13/10). A área é medida com o radar do satélite **NISAR** (NASA–ISRO) e **validada** contra a **cota oficial** (boletins ANA/ONS) convertida em área pela **curva cota × área da ANA/SNIRH**.

### O que o desafio pede (enunciado oficial, aba Details)
- App interativo que use dados do NISAR para rastrear e visualizar um tipo de mudança da superfície.
- Escolher uma área de estudo.
- Dados de apoio para contextualizar; levantar hipóteses sobre as causas do que se vê (ou não se vê).
- Considerações sugeridas:
  - comparar **polarizações** (HH × HV) e **outras frequências/sensores**;
  - mostrar **impacto humano** (a operação da usina decide o nível do lago);
  - storytelling e interatividade (sliders, mapas).
- Solução **open-source** (repo público, licença MIT).

## 2. Conceitos mínimos (radar)

- **O que é uma imagem:** uma matriz 2D de floats. Cada pixel diz quanto sinal de radar voltou (retroespalhamento, γ⁰, em potência linear).
- **Água parada é escura** (devolve quase nada); terra e vegetação são mais claras. Achar água ≈ `db < limiar`.
- **Conversão:** `dB = 10*log10(valor)`. No dado real:
  - água calma: −20 a −21 dB;
  - terra: ~−9 dB;
  - o vale entre as duas fica em ~−15,6 dB.
- **Vento** deixa a água rugosa e mais clara (−17 dB), e a água "some" com limiares baixos. Por isso **−18 dB foi descartado**.
- **Speckle** é o granulado da imagem. Filtre (média 5×5) **em dB** antes de limiarizar.
- **Canais:** HH (melhor para água) e HV (vegetação). No arquivo se chamam `HHHH` e `HVHV`.
- **Comparações:** só entre imagens da mesma trilha, frame, direção de órbita e coleção.
- **Solo exposto liso** (margem que aparece na seca) também fica escuro. Por isso só se conta água dentro do polígono, sem buffer.

## 3. Dados

### NISAR GCOV (`data/raw/nisar/`, não versionado)
- **Coleção:** `NISAR_L2_GCOV_PROVISIONAL_V1` (ASF DAAC, login NASA Earthdata).
- **Trilha 024 D, frame 099, modo 2005:** pixel de 20 m (processado a 40 m, `PASSO = 2`), HH+HV. Cada arquivo tem ~1,9–2,0 GB.
- **9 datas:** 2026-06-27, 07-09, 07-21, 08-14, 08-26, 09-07, 09-19, 10-01 e 10-13. Todas estão baixadas.
- **Nome dos arquivos:** padrão `*_024_D_099_2005_*`. A data está no campo `[11]` do split por `_`.
- **Grade:** EPSG:32723, 16020 × 16488 pixels.
- **Camada `mask`** (códigos confirmados): **255** = fora da passagem; **0** = amostra inválida ou parcialmente focada (inclui a faixa escura da borda esquerda); **1..254** = número da subfaixa (válido).
- **Recorte:** no método oficial é a caixa do polígono + 2 km. 100% do polígono de Furnas tem dado válido nas 9 datas.

### ANA (`data/ana/`)
| arquivo | conteúdo |
|---|---|
| `cota_furnas_ana.csv` | data, cota_furnas_m, volume_util_pct, boletim_ana: as 9 datas NISAR (boletins ANA/ONS) |
| `Furnas.zip` → `furnas/` | `Furnas.gdb`, `UHE Furnas CAV SNIRH.xlsx`, relatório PDF |
| `Funil_Alianca.zip` → `funil/` | `Funil - Aliança.gdb`, `UHE Funil - CAV SNIRH.xlsx`, PDF (não usado no pipeline) |
| `furnas_cota_area.csv` | cota_m, area_km2: curva atualizada da ANA, a cada 0,01 m (`scripts/converter_cav.py`) |
| `funil_cota_area.csv` | idem, para o Funil |

- **Polígono:** a camada `Reservatório` do GDB **não é um polígono**. São 2.068 **linhas** na cota 768,2 m SGB (= **768,0 m de operação**, o nível máximo normal), em SIRGAS 2000 / UTM 23S (EPSG:31983). O `area_agua.py` costura essas linhas em anéis (folga máxima de 340 m) e trata ilhas como buracos (regra par-ímpar). O polígono resultante tem **1.332,0 km²**; a ficha técnica da ANA dá 1.332,14 km².
- **Duas referências de cota na planilha:** "Cota de Operação" (coluna A) e "Cota SGB" (= operação + 0,2 m). Os boletins usam a **de operação**, e é essa que vai para `furnas_cota_area.csv`. A área de 1.442 km² que circulava antes é a original; a atualizada é 1.332 km².
- **Para ler o .gdb:** `pyogrio` (GDAL embutido). Para ler o .xlsx: só a biblioteca padrão.

## 4. Estrutura do repositório

```
CLAUDE.md, README.md, LICENSE (MIT), .gitignore, requirements.txt, requirements-dev.txt (pytest)
scripts/
  abrir_nisar.py     inspeciona um .h5 (arrays, EPSG, pixel, np.unique da mask) e salva prévias HH/HV/cor
  area_agua.py       série de área; opções --poligono (.shp ou .gdb), --buffer, --limiar, --saida
  converter_cav.py   planilha CAV da ANA (.xlsx) -> cota_m,area_km2
  analise.py         junta NISAR + cota + curva ANA -> pasta analise/ (CSV, gráficos, métricas)
tests/               pytest com dados sintéticos (19 testes): limiar, mask, polígono/costura/WKB, braço fino, recorte
data/raw/nisar/      9 .h5 (não versionados)
data/ana/            dados da ANA (ver seção 3)
outputs/
  furnas_poligono_b0/  ** MÉTODO OFICIAL ** (polígono sem buffer, −15,65 dB)
  furnas_poligono/     polígono + 500 m (comparação)
  funil_poligono*/     Funil (cobertura 21%, só registro)
  iter0..2/, raiz      histórico das iterações sem polígono (zona derivada das datas)
  investigacao_20260907*.png   evidência de vento em 07/09
analise/             pacote de resultados (serie.csv, gráficos, RESUMO.md, metricas.txt); analise.zip na raiz
web/                 (a criar) app estático; web/data/ com os dados exportados
```

- **Rodar** (o `.venv` na raiz já tem tudo):
  ```powershell
  .\.venv\Scripts\Activate.ps1   # se bloquear: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  pip install -r requirements.txt          # h5py numpy matplotlib scipy pyproj pyogrio
  python -m pytest tests
  ```
- **`analise/` ainda está desalinhada com a decisão congelada:** as colunas `area_nisar_poligono_*` e os mapas usam o polígono + 500 m. A variante oficial, sem buffer, está em `area_nisar_poligono_sem_buffer_m15_km2`. Refazer apontando `--furnas outputs/furnas_poligono_b0` antes de exportar para o site.
- **Atenção ao `.gitignore`:** ele ainda não cobre `data/ana/`, que tem ~2,8 GB de zips e .gdb.

## 5. Próximas tarefas (em ordem)

1. **Exportar dados para `web/data/`:**
   - `serie.csv` / `serie.json` com data, cota, área esperada, área NISAR oficial, deltas e flag `suspeita_vento`;
   - máscaras por data como PNG georreferenciado (bounds em lat/lon);
   - contorno do polígono em GeoJSON (lat/lon);
   - `meta.json` com ids das cenas, CRID, limiar e método.
2. **App estático em `web/`:**
   - **story map:** o que medimos → validação ANA → por que 07/09 e 01/10 são suspeitos → limitações;
   - **modo explorar:** mapa (ex.: Leaflet), slider de datas, antes/depois, gráfico área × cota;
   - seção sobre a operação da usina (impacto humano).
3. **Polarizações** (opcional): PNG por data em HH, HV e composição, para o botão do site.
4. **Validação DSWx-S1** (opcional, se der tempo): concordância água/não-água por data (±3 dias), ignorando as classes 250/251.

## 6. Testes e sanidade

- **`tests/` cobre:** `otsu`, `vale`, `data_do_nome`, `valido_da_mask`, recorte por coordenadas, lago circular com speckle (±2%), faixa com `mask = 0` ignorada, braço de 3–5 px, `tirar_manchas`, zona/ligação ao lago, leitura de shapefile, costura de linhas, WKB com Z, `processar` com polígono.
- **Sanidade no real (método oficial):**
  - área entre 1.020 e 1.071 km² nas datas sem suspeita;
  - esperada pela ANA entre 1.006 e 1.045 km²;
  - Δ esperado no período de ~−36 km².

## 7. Regras de comunicação no app

- Mudança no radar ≠ causa comprovada. Separe "o que medimos" de "causa provável", sempre com a fonte.
- O ruído do método (~12 km²) é ~1/3 da variação real do período (~40 km²). Não afirme mudanças de poucos km² entre datas próximas.
- Datas suspeitas aparecem marcadas como "suspeita: possível vento", nunca escondidas nem corrigidas.
- Identifique o sensor de cada camada (NISAR, Sentinel-1, HLS). Nunca apresente dado de outro satélite como NISAR.

## 8. Referências

- Guia NISAR: https://nisar-docs.asf.alaska.edu/ (products-overview, gcov, earthaccess, availability-overview)
- NISAR Cookbook (busca/streaming): https://asfopensarlab.github.io/NISAR_Cookbook/
- openSEPPO (conversor GCOV → COG/dB): https://openseppo.readthedocs.io/
- Vertex: https://search.asf.alaska.edu/ · Earthdata Search: https://search.earthdata.nasa.gov/
- ANA, boletins Rios Grande e Paranaíba: https://www.gov.br/ana/pt-br/sala-de-situacao/sistemas-hidricos-dos-rios-grande-e-paranaiba
- ANA/SNIRH, cota × área × volume de Furnas: https://metadados.snirh.gov.br/geonetwork/srv/api/records/b8f0487a-df73-4f8d-8b22-bb49cf9f3683
- OPERA DSWx-S1 (`OPERA_L3_DSWX-S1_V1`, PO.DAAC): 30 m; classes 0 não-água, 1 água, 3 vegetação alagada, 250 HAND, 251 layover/sombra
- Desafio: https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/
- Plano do time (doc): https://claude.ai/artifact/JKFbW6JR1DFek52mWUZbtf
