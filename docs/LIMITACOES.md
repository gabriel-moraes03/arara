# Limitações

O que o Arara não faz, onde ele erra e o que já foi verificado. O que mudou em cada versão está em
[HISTORICO.md](HISTORICO.md).

## Estado da verificação

- **Análises reais de 15/11/2026** (refeitas em `arara-water-0.2.1`: limiar, qualidade e validação iguais às
  da 0.2.0; ids atuais 3dd9b9fc (Furnas), ea442cc4 (Três Marias), 28de0efa (Lake Mead), a59d345b (Pantanal),
  8d2079ef (Nanuque)):

  | Área | Qualidade | Limiar | IoU / precisão / recall |
  |---|---|---|---|
  | Represa de Três Marias (MG) | reliable | −15,64 dB | 0,90 / 0,93 / 0,97 |
  | Furnas, corpo principal (MG), trilha 146 A | reliable (vento em 18/07, marcado) | −15,46 dB | 0,70 (0,82 sem a data de vento) / 0,73 / 0,82 |
  | Lake Mead (EUA), trilha 85 D | experimental (falsos positivos na margem exposta) | −16,27 dB | 0,69 (0,73 sem vento) / 0,75 / 0,91 |
  | Pantanal, Corumbá (MS) | experimental (diverge do óptico) | −15,45 dB | 0,51 / 0,62 / 0,78 |
  | "Minha área 1", Nanuque (MG), pasto sem lago | no_reliable_water | −11,23 dB (Otsu) | Sentinel-2 sem água em 7 de 7 datas |

- **Regressão de Furnas com os `.h5` (15/11/2026)**: os 5 testes passam com as 9 cenas e o `Furnas.gdb`
  (erro médio 1,0% nas 7 datas calmas, 47,4 contra 45,0 km² por metro de cota, áreas oficiais com
  tolerância de 0,5%). Isso valida o **método de Furnas** (`furnas.processar`, limiar −15,65 dB).
- **O fluxo global (`run.py`) nas mesmas 9 cenas**, com a caixa do lago como área e a água medida dentro
  do polígono da ANA: `reliable`, limiar automático −15,54 dB, erro médio de 1,5% (15,7 km²) nas 8 datas
  que ele considera calmas e 64,0 km²/m de sensibilidade à cota. Ele marca vento só em 07/09; o estudo
  validado marca também 01/10. Fica perto do estudo validado, mas **não reproduz exatamente o 1%**.
  Com a área desenhada só sobre a água (o próprio polígono), o fluxo não acha margem água/terra e
  responde `no_reliable_water`: a área precisa ter terra em volta da água.
- **Primeira carga do globo**: ~1,5 s em Chrome headless, cache vazio, localhost. Os 45 s relatados não
  se reproduziram; a parte que dependia de CDN e de fontes externas saiu do caminho crítico.
- Não houve conferência com dado de campo fora de Furnas.
- Em Três Marias, 07/09, 19/09 e 13/10 têm água ~1,3 a 1,5 dB mais clara que a mediana e área menor,
  mas ficam abaixo do corte de 1,75 dB do flag de vento: podem ser vento não marcado.
- A cobertura de um grupo é calculada pelo contorno da cena no catálogo; uma cena pode cobrir a área no
  contorno e não ter dado válido ali (aconteceu no Pantanal em 05/07). Ela é descartada com o motivo.
- O globo, o estudo automático e a vitrine foram abertos num Chrome real (headless); não houve teste
  manual em celular.
- O estudo de Furnas não aparece como análise da API; ele é servido em `/furnas/`.

## Máscara de terreno: medida, não ligada

Falsos positivos em terra seca (Lake Mead). Com HAND (GLO-30 HAND, ASF) e declividade (Copernicus
GLO-30), sobre as 10 datas do Lake Mead contra o Sentinel-2 (`pipeline/scripts/medir_terreno.py`):

| Máscara | Precisão | Recall | IoU |
|---|---|---|---|
| nenhuma (fluxo atual) | 0,750 | 0,911 | 0,699 |
| declividade ≤ 15° | 0,751 | 0,911 | 0,699 |
| HAND ≤ 20 m, dilatada 300 m | 0,751 | 0,911 | 0,699 |
| HAND ≤ 5 m, sem dilatação | 0,852 | 0,911 | 0,787 |
| HAND ≤ 2 m, sem dilatação | 0,896 | 0,910 | 0,824 |
| HAND ≤ 2 m, dilatada 30 m | 0,847 | 0,911 | 0,782 |
| HAND ≤ 2 m, dilatada 150 m | 0,763 | 0,911 | 0,710 |

A declividade não muda nada: os falsos positivos não estão em encosta nem em sombra de radar. 80% deles
estão em HAND acima de 0,5 m, em manchas grandes (78% em manchas de mais de 100 ha) coladas na borda do
lago do DEM: é a margem antiga, exposta desde que o DEM foi feito, lisa e escura no radar. Só um corte
de HAND baixo, **sem dilatação**, atinge precisão > 0,85, e esse corte também apagaria água real acima do
nível do lago na época do DEM (represa que encheu, cheia, lago novo). Qualquer dilatação que proteja esses
casos devolve as manchas. Por isso a máscara não entrou no fluxo; a validação com o Sentinel-2 continua
mostrando a divergência (e ela deixa a análise `experimental`).

## Método

- **Vento** encrespa a água, ela fica mais clara e parte some do limiar. A data é marcada quando o brilho
  mediano HH da água recorrente passa 1,75 dB da mediana da série; precisa de 3 datas. Não há correção.
- **Vegetação alagada e plantas aquáticas** não aparecem como água aberta em HH.
- **Solo liso, sombra de radar e pistas** podem parecer água. Manchas menores que 0,1 km² são removidas.
- O limiar vem do vale água/terra da própria área. Sem pelo menos 5 blocos de margem na data que define o
  limiar, com limiar fora de −22 a −12 dB ou com fração de água fora de 0,5–90% na maioria das datas, a
  análise sai **sem água confiável** (`no_reliable_water`); fração fora da faixa em poucas datas, ou radar
  divergindo do Sentinel-2, deixa a análise **experimental**.
- A zona de água exige recorrência entre datas; com uma ou duas datas ela é pouco restritiva.
- HV é opcional: cenas de polarização simples entram só com HH.
- `normalize` (normalização entre datas) não foi implementado.

## Dados

- Produtos **provisórios** do NISAR podem mudar; o CRID de cada cena fica em `sources.json`.
- O checksum do DAAC cobre o arquivo inteiro e não é conferido na leitura por janela; valida-se
  estrutura, grade, unidade e mask.
- Área de até 2.500 km², até 12 cenas por análise (espaçadas no período), um job pesado por vez.

## Validação óptica

- O Sentinel-2 é referência independente, não verdade de campo; pode estar a até 7 dias do radar.
- Com menos de 60% da área sem nuvem a data fica `not_optically_validated`.
- MNDWI > 0 e radar em L discordam em margens rasas e vegetação alagada.

## Projeção e hipótese

- A projeção é a continuação estatística da série (persistência amortecida), sem chuva nem operação de
  reservatório. Sempre experimental; exige 4 datas calmas e só sai em análise `reliable`.
- A causa provável é uma hipótese por regra, com confiança baixa ou média. O radar mede a mudança, não
  a causa.
