# TerraPulse

Projeto para o NASA Space Apps 2026, desafio *Dancing with the SARs*. Mede com o radar do satélite
**NISAR** (L2 GCOV, banda L, HH) a **área de água da represa de Furnas (MG)** em 9 passagens de 2026
(27/06 a 13/10) e confere cada medida com a **cota oficial da ANA/ONS**, convertida em área pela curva
cota × área da ANA/SNIRH.

Resultado: nas 7 datas sem suspeita de vento, erro absoluto médio de **1,0% (10 km²)**; inclinação
área × cota de **47 km²/m** contra **45 km²/m** da curva ANA. Detalhes em `analise/RESUMO.md`.

> Mudança no radar ≠ causa comprovada. 07/09 e 01/10 estão marcadas como "possível vento".

## Estrutura

```
web/                     app estático (story map + modo Explorar); abre com python -m http.server
  config.js              nomes do time e link do repositório (único lugar a editar)
  data/                  camadas e dados gerados por scripts/exportar_web.py
  i18n/                  textos EN e PT
scripts/
  abrir_nisar.py         inspeciona um .h5 (arrays, EPSG, pixel, códigos da mask) e salva prévias
  area_agua.py           série de área de água por data (método oficial: --buffer 0 --limiar -15.65)
  converter_cav.py       planilha cota × área × volume da ANA (.xlsx) -> CSV
  analise.py             junta NISAR + cota + curva ANA -> analise/
  exportar_web.py        refaz o método oficial e exporta web/data/
tests/                   pytest com dados sintéticos
data/ana/                cotas (boletins ANA/ONS) e curvas cota × área (CSV)
data/raw/nisar/          .h5 NISAR GCOV, trilha 024 D, frame 099, modo 2005 (não versionados, ~2 GB cada)
outputs/furnas_poligono_b0/  saída do método oficial (polígono ANA sem buffer, −15,65 dB)
analise/                 pacote de resultados (série, gráficos, RESUMO.md, metricas.txt)
CLAUDE.md                contexto completo e decisões do projeto
```

Não versionados (ver `.gitignore`): os .h5 do NISAR, o File Geodatabase e as planilhas da ANA
(`data/ana/furnas/`, `data/ana/funil/`, zips, ~2,8 GB), as iterações antigas em `outputs/`, os
screenshots do site e os zips de entrega.

## Como rodar (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # se bloquear: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -r requirements.txt

# 1. área de água em cada data (precisa dos .h5 em data/raw/nisar e do Furnas.gdb da ANA)
python scripts/area_agua.py data/raw/nisar --poligono data/ana/furnas/Furnas.gdb --buffer 0 --limiar -15.65 --saida outputs/furnas_poligono_b0

# 2. camadas e dados do site
python scripts/exportar_web.py

# 3. site
cd web; python -m http.server 8000      # abrir http://localhost:8000

# testes
pip install -r requirements-dev.txt
python -m pytest tests
```

## Dados

- NISAR GCOV `NISAR_L2_GCOV_PROVISIONAL_V1` (ASF DAAC, login NASA Earthdata). Datas: 27/06, 09/07,
  21/07, 14/08, 26/08, 07/09, 19/09, 01/10 e 13/10 de 2026.
- Cota de Furnas: boletins diários ANA/ONS, Sistemas Hídricos dos Rios Grande e Paranaíba.
- Limite do reservatório e curva cota × área: ANA/SNIRH (UHE Furnas).

## Licença

MIT. Veja `LICENSE`. Fontes do site: Fraunces e IBM Plex (SIL OFL, em `web/fonts/`); Leaflet (BSD-2, em `web/vendor/`).
