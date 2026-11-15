# Arara: Furnas 2026, NISAR × ANA (resumo)

**Dados:** NISAR GCOV HH, trilha 024 D, frame 099, 9 datas (27/06 a 13/10/2026), pixel processado de 40 m. Limite do reservatório, curva cota × área e cota diária: ANA/SNIRH e boletins ANA/ONS.

## Método (o que mudou)
- **Polígono oficial:** é a camada `Reservatório` do GDB da ANA, com linhas na cota 768,2 m SGB (= 768,0 m de operação, o nível máximo normal). As 2.068 linhas foram costuradas em anéis e as ilhas viram buracos. O polígono resultante tem **1.332,0 km²**; a ficha técnica da ANA dá 1.332,14 km².
- **Contagem:** água = HH filtrado < −15,6 dB, só dentro do polígono (+ 500 m, como pedido, e sem buffer, para comparar), descartando manchas < 0,1 km². O recorte passou a ser a caixa do polígono.
- **Área esperada:** interpolação da curva "Curvas Atualizadas" da ANA na coluna *Cota de Operação*, a mesma referência dos boletins.

## Cobertura
- **Furnas: 100%** do polígono tem dado válido (`mask` 1) nas 9 datas. O recorte antigo cobria 99,9%: cortava a ponta leste.
- **Funil: só 21%.** A borda leste da passagem NISAR corta o lago, então a série do Funil (~4,5 km²) é parcial e **não serve de grupo de controle** nesta trilha.

## Tabela (km²)
| data | cota (m) | esperada | Δ esp. | +500 m | sem buffer | Δ sem buffer | −18 dB |
|---|---|---|---|---|---|---|---|
| 27/06 | 763,65 | 1.042 | 0 | 1.047 | 1.040 | 0 | 843 |
| 09/07 | 763,72 | 1.045 | +3 | 1.063 | 1.042 | +2 | 820 |
| 21/07 | 763,67 | 1.043 | +1 | 1.109 | 1.071 | **+32** | 894 |
| 14/08 | 763,41 | 1.030 | −12 | 1.095 | 1.053 | +13 | 897 |
| 26/08 | 763,22 | 1.022 | −20 | 1.075 | 1.024 | −16 | 643 |
| 07/09 ⚠ | 762,85 | 1.006 | −36 | 932 | 924 | **−116** | 146 |
| 19/09 | 763,01 | 1.013 | −29 | 1.045 | 1.024 | −16 | 795 |
| 01/10 ⚠ | 762,93 | 1.009 | −33 | 1.009 | 986 | −53 | 455 |
| 13/10 | 763,10 | 1.017 | −25 | 1.034 | 1.020 | −20 | 827 |

⚠ = água mais clara e uniforme no radar, compatível com vento. Detalhes em `metricas.txt`.

## Concordância com a ANA (−15,6 dB; 7 datas sem vento | 9 datas)
| variante | erro abs. médio | desvio padrão das dif. (ruído) | r(cota, área) | inclinação (ANA: 45 km²/m) | r(Δ) |
|---|---|---|---|---|---|
| **sem buffer** | **10 km² (1,0%)** \| 20 km² (1,9%) | **12 km²** \| 33 km² | +0,75 \| +0,79 | **47 km²/m** | +0,74 |
| + 500 m | 37 km² (3,6%) \| 37 km² | 25 km² \| 43 km² | +0,47 \| +0,72 | 45 km²/m | +0,46 |
| −18 dB (+500 m) | 213 km² (21%) \| 323 km² | 81 km² \| 241 km² | +0,44 \| +0,71 | 129 km²/m | +0,44 |

## O que ainda é suspeito
- **O buffer de 500 m só acrescenta erro.** O lago está ~5 m abaixo da cota do contorno, então fora do polígono só há terra. Essa terra fica escura na seca e chega a +50 km² em 26/08. É a principal causa da tendência invertida que restava.
- **21/07 tem +32 km² a mais que o esperado**, mesmo sem buffer. Provavelmente é a faixa exposta entre ~763 m e 768 m (solo liso e escuro) dentro do polígono. Não verificado.
- **Vento (07/09 e 01/10):** a área cai até 116 km² sem que a cota explique. Também infla o r com 9 datas.

## Recomendação
**−15,6 dB, polígono sem buffer, com 07/09 e 01/10 marcadas como "afetadas por vento".** O −18 dB fica a 2–3 dB da água calma (−20 a −21 dB) e perde o lago com qualquer vento.

## O que a NISAR consegue e não consegue afirmar
Em dias sem vento, a NISAR mede a área de Furnas em 2026 com ~1% de erro e reproduz a sensibilidade da curva da ANA (47 contra 45 km²/m). Mas a variação real no período (~40 km², cota caindo 0,9 m) é só ~3 vezes o ruído do método (~12 km²). Por isso ela confirma a ordem de grandeza e o sentido geral da queda, mas não consegue resolver mudanças de poucos km² entre datas próximas sem a cota da ANA ao lado.
