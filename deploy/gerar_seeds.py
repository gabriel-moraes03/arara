"""
Gera os seeds da VPS a partir da máquina de desenvolvimento (banco do docker-compose.yml + data/analyses):

    python deploy/gerar_seeds.py [--servidor http://localhost:8081]

- deploy/seed/arara_seed.sql.gz: só os dados (INSERT ... ON CONFLICT DO NOTHING) das análises escolhidas,
  dos jobs e do histórico (observation). O esquema vem do Flyway do próprio backend na VPS.
- deploy/seed/arara_data.tar.gz: analyses/<id>/ só com o que o globo e o estudo usam (png/ e os JSON/CSV);
  sem COG, tiles, cache nem log.
Escolha: a análise concluída mais recente, não superada, de cada região de frontend/globe/regioes.json,
mais as análises extras (--extra, padrão: Furnas e Três Marias). Falhas e jobs em andamento ficam de fora
(o backend retomaria jobs ativos na subida). Os dois arquivos não vão para o Git.
"""
import argparse
import gzip
import json
import os
import subprocess
import sys
import tarfile
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRAS = ["3dd9b9fcb60bedff29ef4cb8", "ea442cc413ae9ff0edd0ccd1"]   # Furnas e Três Marias (0.2.1)
ARQUIVOS = ("result.json", "metrics.json", "metrics.csv", "sources.json", "spec.json")


def psql(sql, banco="arara", saida=False):
    cmd = ["docker", "exec", "-i", "arara-db", "sh", "-c", f'psql -v ON_ERROR_STOP=1 -q -At -U "$POSTGRES_USER" -d {banco}']
    r = subprocess.run(cmd, input=sql.encode(), capture_output=True, check=True)
    return r.stdout.decode().strip() if saida else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--servidor", default="http://localhost:8081")
    ap.add_argument("--extra", nargs="*", default=EXTRAS)
    a = ap.parse_args()
    saida = os.path.join(RAIZ, "deploy", "seed")
    os.makedirs(saida, exist_ok=True)

    regioes = json.load(open(os.path.join(RAIZ, "frontend", "globe", "regioes.json"), encoding="utf-8"))["regioes"]
    with urllib.request.urlopen(a.servidor.rstrip("/") + "/api/arara/analyses?status=completed", timeout=60) as r:
        concluidas = json.load(r)["analyses"]                 # a API já omite as superadas
    ids = []
    for reg in regioes:
        cand = sorted((x for x in concluidas if x["name"] == reg["n"]), key=lambda x: x["updated_at"], reverse=True)
        if cand:
            ids.append(cand[0]["analysis_id"])
            print(f"região {reg['id']:<11} {cand[0]['analysis_id']}  {cand[0]['summary'].get('quality')}")
        else:
            print(f"região {reg['id']:<11} sem análise concluída (fica 'aguardando')")
    for e in a.extra:
        if any(x["analysis_id"] == e for x in concluidas):
            ids.append(e)
            print(f"extra       {e}  {next(x['name'] for x in concluidas if x['analysis_id'] == e)}")
        else:
            sys.exit(f"análise extra {e} não está concluída no servidor")
    for i in ids:
        if not os.path.isfile(os.path.join(RAIZ, "data", "analyses", i, "result.json")):
            sys.exit(f"{i}: falta data/analyses/{i}/result.json")

    # banco: cópia temporária, só as linhas escolhidas, dump só de dados
    lista = ",".join(f"'{i}'" for i in ids)
    psql("DROP DATABASE IF EXISTS arara_seed;", "postgres")
    psql("CREATE DATABASE arara_seed;", "postgres")
    try:
        subprocess.run(["docker", "exec", "arara-db", "sh", "-c",
                        'pg_dump -U "$POSTGRES_USER" arara | psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d arara_seed'],
                       check=True, capture_output=True)
        psql(f"DELETE FROM observation WHERE analysis_id NOT IN ({lista});"
             f"DELETE FROM job WHERE analysis_id NOT IN ({lista}) OR status <> 'COMPLETED';"
             f"DELETE FROM analysis WHERE id NOT IN ({lista});", "arara_seed")
        cont = psql("SELECT (SELECT count(*) FROM analysis)||' análises, '||(SELECT count(*) FROM job)||' jobs, '"
                    "||(SELECT count(*) FROM observation)||' observações';", "arara_seed", saida=True)
        dump = subprocess.run(["docker", "exec", "arara-db", "sh", "-c",
                               'pg_dump -U "$POSTGRES_USER" -d arara_seed --data-only --inserts --on-conflict-do-nothing '
                               '--no-owner --no-privileges --exclude-table-data=flyway_schema_history'],
                              check=True, capture_output=True).stdout
    finally:
        psql("DROP DATABASE IF EXISTS arara_seed;", "postgres")
    with gzip.open(os.path.join(saida, "arara_seed.sql.gz"), "wb") as f:
        f.write(dump)

    # arquivos: só png/ e os JSON/CSV de cada análise escolhida
    tar = os.path.join(saida, "arara_data.tar.gz")
    with tarfile.open(tar, "w:gz") as t:
        for i in ids:
            base = os.path.join(RAIZ, "data", "analyses", i)
            for nome in ARQUIVOS:
                if os.path.isfile(os.path.join(base, nome)):
                    t.add(os.path.join(base, nome), arcname=f"analyses/{i}/{nome}")
            t.add(os.path.join(base, "png"), arcname=f"analyses/{i}/png")
    mb = lambda p: os.path.getsize(p) / 1e6
    print(f"banco: {cont}")
    print(f"deploy/seed/arara_seed.sql.gz {mb(os.path.join(saida, 'arara_seed.sql.gz')):.1f} MB | "
          f"deploy/seed/arara_data.tar.gz {mb(tar):.1f} MB")


if __name__ == "__main__":
    main()
