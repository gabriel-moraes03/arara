#!/usr/bin/env bash
# Carrega as análises já feitas na VPS: arquivos no volume do backend e linhas no Postgres.
# Idempotente: os arquivos são extraídos por cima (mesmo conteúdo) e o banco só é importado se a
# tabela de análises estiver vazia (o dump também usa ON CONFLICT DO NOTHING). Rodar de novo não duplica.
#
#   cd deploy && ./restore.sh
# Espera deploy/.env preenchido e deploy/seed/arara_seed.sql.gz + deploy/seed/arara_data.tar.gz.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "falta deploy/.env (copie de .env.example)"; exit 1; }
for f in seed/arara_seed.sql.gz seed/arara_data.tar.gz; do
  [ -f "$f" ] || { echo "falta deploy/$f (copie os seeds para a VPS)"; exit 1; }
done
set -a; . ./.env; set +a
DB_USER="${ARARA_DB_USER:-arara}"
compose() { docker compose -f docker-compose.prod.yml "$@"; }
# pasta dos seeds como o Docker a enxerga (Git Bash no Windows: caminho C:/...; Linux: o normal)
SEED_DIR="$(pwd -W 2>/dev/null || pwd)/seed"
export MSYS_NO_PATHCONV=1

echo "1/4 subindo banco e backend (o Flyway cria as tabelas na primeira subida)"
compose up -d --build db backend
for i in $(seq 1 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$(compose ps -q backend)")" = healthy ] && break
  sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' "$(compose ps -q backend)")" = healthy ] \
  || { echo "o backend não ficou saudável; veja: docker compose -f docker-compose.prod.yml logs backend"; exit 1; }

echo "2/4 arquivos das análises -> volume arara-data"
compose run --rm --no-deps -T -v "$SEED_DIR:/seed:ro" --entrypoint tar backend \
  -xzf /seed/arara_data.tar.gz -C /data

echo "3/4 banco"
n=$(compose exec -T db psql -U "$DB_USER" -d arara -Atc "select count(*) from analysis")
if [ "$n" = "0" ]; then
  gunzip -c seed/arara_seed.sql.gz | compose exec -T db psql -q -v ON_ERROR_STOP=1 -U "$DB_USER" -d arara >/dev/null
  echo "   importado: $(compose exec -T db psql -U "$DB_USER" -d arara -Atc "select count(*) from analysis") análises"
else
  echo "   o banco já tem $n análises; nada importado"
fi

echo "4/4 reiniciando o backend e subindo o Caddy"
compose restart backend
compose up -d caddy
echo "pronto. Confira: curl -s http://localhost/api/arara/config"
