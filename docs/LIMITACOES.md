# Limitações

## Estado da verificação

- **Nenhuma análise real de NISAR fora de Furnas foi executada.** A máquina de desenvolvimento não tinha
  credenciais Earthdata; a leitura por streaming foi testada com arquivos sintéticos e com objeto de
  arquivo, não com uma cena remota. O catálogo (ASF) e o Sentinel-2 foram testados ao vivo.
- **A regressão de Furnas com os `.h5` não foi rodada depois da migração** (os arquivos e o `Furnas.gdb`
  não estavam no disco). Os testes da ANA reproduzem os números publicados.
- **O globo não foi aberto num navegador real**, só testado com DOM simulado.
- O estudo de Furnas não aparece como análise da API; ele é servido em `/furnas/`.

## Método

- **Vento** encrespa a água, ela fica mais clara e parte some do limiar. A data é marcada quando o brilho
  mediano HH da água recorrente passa 1,75 dB da mediana da série; precisa de 3 datas. Não há correção.
- **Vegetação alagada e plantas aquáticas** não aparecem como água aberta em HH.
- **Solo liso, sombra de radar e pistas** podem parecer água. Manchas menores que 0,1 km² são removidas.
- O limiar vem do vale água/terra da própria área. Sem pelo menos 5 blocos de margem, com limiar fora de
  −22 a −12 dB ou fração de água fora de 0,5–90%, a análise sai marcada **experimental**.
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
  reservatório. Sempre experimental; exige 4 datas calmas.
- A causa provável é uma hipótese por regra, com confiança baixa ou média. O radar mede a mudança, não
  a causa.
