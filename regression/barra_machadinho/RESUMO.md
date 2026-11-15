# Arara: Barra Grande e Machadinho 2026, NISAR × ANA (resumo)

**Rótulo: EXPERIMENTAL.** O NISAR acompanha a subida dos dois reservatórios, mas mede de 12% a 29% menos
área que a curva da ANA em todas as datas (erro absoluto médio de 20,0% e 25,7%, contra o critério de 5%).

**Dados:** NISAR GCOV HH (coleção NISAR_L2_GCOV_PROVISIONAL_V1, CRID P05023), trilha 053 D, frame 102,
modo 2005 (20 m), 7 datas (17/06 a 15/10/2026), pixel processado de 40 m. Limites dos reservatórios e
curvas cota × área: pacotes ANA/SNIRH "Cota x Área x Volume dos Reservatórios de UHEs". Cota e % de volume
útil: ANA SAR (MedicaoSin), reservatórios 19067 (Barra Grande) e 19069 (Machadinho).

## Método (o de Furnas, sem ajuste)
- **Contagem:** HH em potência linear → dB uma vez → média 5×5 em dB → água = HH < **−14,6 dB**, só dentro
  do polígono oficial, sem buffer, descartando manchas < 0,1 km². Mask 0 e 255 inválidos.
- **Limiar:** um só para a série inteira, no vale água/terra dos blocos de margem das 7 datas e dos dois
  reservatórios. Os lagos são estreitos e só **3 blocos** de 2 km passam no critério (o método pede 5).
  Como conferência, o Otsu dos pixels dentro dos polígonos dá −15,1 dB. O vale desses pixels não serve:
  o histograma não tem um segundo pico limpo e o vale caiu em +3,9 dB. O limiar fica em −14,6 dB.
- **Polígonos:**
  - *Machadinho:* camada `Reservatório` do GDB (linhas a 480,00 m, o nível máximo normal), 7 anéis com as
    ilhas como buracos: **79,7 km²**. A ficha da ANA dá 80,49 km² (−1%).
  - *Barra Grande:* a camada `Reservatório` é a curva de **651,14 m** (máximo maximorum), com 98,6 km²
    (a CAV dá 97,1 km² nessa cota). Por isso foi usada a **isóbata de 647,00 m** (o nível máximo normal)
    do mesmo GDB: 104 anéis com as ilhas, **90,2 km²**. A ficha dá 90,74 km² (−0,5%).
- **Área esperada:** interpolação da folha "Curvas Atualizadas" na **coluna A**: cota local em Barra
  Grande, cota de operação em Machadinho. É a referência do SAR da ANA: o % de volume útil recalculado com
  a coluna A bate com o publicado em todas as 14 linhas (diferença ≤ 0,1 ponto). A coluna B (SGB) fica
  +0,14 m e +0,21 m acima. A área é multiplicada pela fração do polígono que o radar mede, como em Furnas.

## Cobertura e encostas
| | polígono | válido em todas as datas | fora da passagem (255) | encosta: sombra | encosta: layover | fração usada |
|---|---|---|---|---|---|---|
| Barra Grande | 90,2 km² | 96,7% (96,8–98,6% por data) | 3,3% | 3,0% | 1,4% | **92,3%** |
| Machadinho | 79,7 km² | 100% | 0% | 2,3% | 1,4% | **96,3%** |

O GCOV veio **sem máscara de sombra** (`shadowMaskingApplied = False`). As encostas com geometria crítica
foram estimadas pelo fator RTC γ⁰→σ⁰ do próprio produto, que depende do ângulo de incidência local:
fator < 0,35 é encosta de costas para o radar (perto da sombra) e > 0,93 é encosta de frente (layover).
Essas encostas foram mascaradas. Sem a máscara, a área muda menos de 1 km² (`area_com_encostas_km2` em
`area_agua.csv`), então elas não explicam o déficit.

## Tabela (km²)
| data | BG cota (m) | BG esperada | BG NISAR | BG Δ | MA cota (m) | MA esperada | MA NISAR | MA Δ | vento |
|---|---|---|---|---|---|---|---|---|---|
| 17/06 | 628,96 | 58,9 | 51,7 | −7,2 | 468,21 | 63,3 | 49,4 | −13,9 | não |
| 29/06 | 629,64 | 59,3 | 50,5 | −8,8 | 469,33 | 64,5 | 48,3 | −16,2 | não |
| 11/07 | 643,90 | 77,4 | 61,1 | −16,3 | 478,63 | 74,8 | 53,1 | −21,8 | não |
| 23/07 | 646,17 | 82,1 | 63,1 | −19,0 | 479,04 | 75,4 | 55,1 | −20,3 | não |
| 16/08 | 645,93 | 81,6 | 60,5 | −21,1 | 477,49 | 73,4 | 52,1 | −21,3 | não* |
| 28/08 | 645,02 | 79,7 | 63,3 | −16,4 | 476,47 | 72,2 | 55,6 | −16,7 | não |
| 15/10 | 645,18 | 80,0 | 62,0 | −18,0 | 476,20 | 71,9 | 54,1 | −17,8 | não |

Esperada = CAV × fração usada. \* 16/08: a água fica 0,7 dB (BG) e 1,4 dB (MA) mais clara que a mediana
da série, abaixo do critério de vento fixado antes (≥ 1,5 dB). Não foi marcada, mas é a data mais clara
nos dois lagos, e a área de Barra Grande cai 2,6 km² sem que a cota explique.

## Concordância com a ANA (7 datas; nenhuma marcada como vento, então "sem vento" = "todas")
| | erro abs. médio | viés | desvio das dif. (ruído) | r(cota, área) | inclinação NISAR × CAV | r(Δ entre datas) | Δ NISAR / Δ CAV |
|---|---|---|---|---|---|---|---|
| **Barra Grande** | 15,3 km² (**20,0%**) | −15,3 km² | 5,2 km² | +0,98 | 0,68 × 1,33 km²/m | +0,89 | 0,57 |
| **Machadinho** | 18,3 km² (**25,7%**) | −18,3 km² | 2,9 km² | +0,85 | 0,54 × 1,10 km²/m | +0,64 | 0,44 |

**Subida de 29/06 a 11/07** (12 dias; Barra Grande +14,3 m, de 37% para 87% do volume útil; Machadinho
+9,3 m, de 26% para 90%):
- Barra Grande: o radar vê **+10,6 km²** de água nova (10,7 km² surgem, 0,1 km² somem). A CAV espera +18,0 km².
- Machadinho: o radar vê **+4,8 km²**. A CAV espera +10,3 km².

## O que ainda é suspeito
- **Medido:** o NISAR fica sempre abaixo da CAV, e o déficit cresce com a cota. Em Barra Grande vai de
  −7 km² com o lago baixo a −21 km² com ele cheio. O ruído é pequeno (3–5 km²), então o erro é sistemático,
  não aleatório.
- **Causa provável 1, resolução (verificada em parte):** os lagos são cânions com poucas centenas de metros
  de largura. Com pixel de 40 m e média 5×5 (janela de 200 m), margens e braços estreitos se perdem. A
  sensibilidade abaixo (`sensibilidade.json`, de `pipeline/scripts/sensibilidade_uruguai.py`) usa o mesmo
  limiar, polígono, máscara de encostas e área esperada, e **não** substitui o resultado:

  | erro absoluto médio | 40 m, 5×5 (oficial) | 20 m, 5×5 | 20 m, 3×3 |
  |---|---|---|---|
  | Barra Grande | 20,0% | 9,5% | 7,0% |
  | Machadinho | 25,7% | 15,9% | 12,1% |

  Nenhuma variante chega a 5%, e todas continuam abaixo da ANA com o lago cheio.
- **Causa provável 2, não verificada:** com o lago baixo por meses, a faixa entre ~629 m e 647 m pode ter
  ganho vegetação. Ao inundar, vegetação submersa ou emergente devolve sinal (dupla reflexão) e não aparece
  escura. Isso explicaria por que o déficit continua crescendo com a cota mesmo a 20 m.
- **Água mais clara que em Furnas:** a mediana do núcleo do lago fica em −18,4 dB (BG) e −19,4 dB (MA),
  contra −20 dB em Furnas. O limiar de −14,6 dB está a só 4–5 dB disso.

## O que a NISAR consegue e não consegue afirmar aqui
O radar mede de dia ou de noite, com ou sem nuvens. O NISAR mostra **quando** e **onde** os dois
reservatórios encheram: a subida de 29/06 a 11/07 aparece nas duas séries, com r(cota, área) de 0,98 em Barra Grande, e
o mapa mostra a água entrando nos braços. Com o método validado em Furnas e pixel de 40 m, porém, ele não
mede a **área absoluta** desses lagos encaixados: perde 20–26% da área e cerca de metade da variação. Para
números absolutos, ainda é preciso a cota da ANA ao lado. Os dados NISAR são provisórios.

## Verificações de 15/11 (antes de aceitar o rótulo)
- **Referencial dos polígonos:**
  - *Barra Grande:* as camadas `Reservatório` e `Isóbatas` estão em SIRGAS 2000 / UTM 22S (EPSG:31982),
    convertidas sem translação para WGS 84 / UTM 22S (EPSG:32722, a grade do GCOV).
  - *Machadinho:* está em SAD69 / UTM 22S, num WKT ESRI sem código EPSG. O pyproj usou o "ballpark
    geographic offset", ou seja, **sem** translação de datum (cerca de 10 m de efeito, só pelo elipsoide).
  - *Correlação cruzada* entre a máscara do polígono e a água do NISAR (HH < −14,6 dB) em 23/07, a 20 m,
    buscando ±150 m: Barra Grande tem pico em **(0, 0) m** (r = 0,658); Machadinho em **(0, −20) m**,
    com r = 0,6328 contra 0,6327 em (0, 0).
  - *Teste da translação do EPSG:* aplicar a translação SAD69→WGS 84 (−50, −44 m em Machadinho) **piora**
    o alinhamento: r cai para 0,616 e a IoU de 0,466 para 0,449. As coordenadas do GDB já estão, na
    prática, no referencial do radar.
  - *Conclusão:* não há deslocamento sistemático nem bug de conversão. Os polígonos não mudaram. O
    deslocamento visto no mapa da página fica dentro de 1 pixel; a causa provável (não verificada) é a
    reamostragem para Web Mercator e a linha simplificada a 30 m.
- **Água escura a leste de Machadinho, fora do contorno (12,5 km² em 23/07):**
  - O braço do Canoas no polígono da ANA termina em −51,345, −27,60. A mancha começa a 1,1 km dali, rio
    acima, depois de um trecho estreito de rio, e não encosta no contorno em ponto nenhum.
  - O polígono tem 79,7 km², 99% da área da ficha da ANA no NA máximo normal (80,49 km²). Somar a mancha
    daria 92 km².
  - Logo, **não é** parte de Machadinho ausente do polígono. Pela posição (rio Canoas, logo a montante da
    barragem de Campos Novos), é compatível com o reservatório da UHE Campos Novos. Essa identificação é
    geográfica, não vem de arquivo da ANA.
  - Mapa: `item3_agua_leste_machadinho.png`.
- **Rótulo:** sem bug de referencial, nada muda no resultado oficial, e o estudo **continua experimental**.
