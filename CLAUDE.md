# Arara

Aplicação web de água vista pelo NISAR. Visão geral em `README.md`, execução em `docs/COMO_RODAR.md`,
limites em `docs/LIMITACOES.md`, mudanças por versão em `docs/HISTORICO.md`.

## Comandos

```
.venv/bin/python -m pytest pipeline/tests -q      # pipeline
./backend/mvnw -f backend test                    # backend
docker compose up -d                              # PostgreSQL (antes do backend)
./backend/mvnw -f backend spring-boot:run         # app em :8080 (roda de dentro de backend/)
```

## Regras que não se negociam

- Dados reais sempre. Sem acesso, cobertura ou cena válida: `unavailable` com o motivo. Nada simulado.
- Uma coleção e uma geometria (trilha, direção, frame) por análise. Registrar o CRID.
- dB uma única vez, a partir de potência linear. Mask GCOV: 0 e 255 inválidos.
- Nada de Furnas fixo no fluxo global (−15,65 dB, polígono da ANA, caminhos). Furnas é regressão.
- Não presumir que o maior componente conectado é o corpo d'água de interesse.
- Credenciais Earthdata só no `.env`/ambiente do backend; nunca em log, resposta, navegador ou Git.
- Mudança medida separada de causa provável. Datas com vento são marcadas, nunca escondidas.

## Onde mexer

- Pipeline: `pipeline/arara_pipeline/run.py` orquestra; cada etapa é um módulo. `ALGORITHM_VERSION` em
  `__init__.py` tem de bater com `arara.algorithm-version` no `application.yml` (entra no id da análise).
  Ao subir a versão, registre o que mudou em `docs/HISTORICO.md`.
- Backend: `br.arara` em domain / application / adapters. Os testes usam uma resposta real gravada da
  ASF e uma pipeline falsa (`FakePipeline`, só em `src/test`).
- Globo: `frontend/globe/index.html`, arquivo único; fala com `api/arara`.
