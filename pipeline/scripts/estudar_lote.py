"""Gera estudos em lote: para cada área de um arquivo JSON, pede a análise ao backend, acompanha o job e
imprime o link do estudo (/estudo/?id=...). É a versão automática do que foi feito à mão em Furnas.

    python pipeline/scripts/estudar_lote.py data/estudos_mg.json [--url http://localhost:8080]
                                            [--inicio AAAA-MM-DD] [--fim AAAA-MM-DD] [--refazer] [--so SIGLA ...]

O arquivo é uma lista de {"id", "nome", "bbox": [oeste, sul, leste, norte], "bacia"?}. Áreas acima do limite
do servidor (2.500 km²) ou sem cenas NISAR saem como "unavailable", com o motivo. Um job roda por vez no
servidor; o script espera cada um terminar. Credenciais Earthdata ficam só no servidor (.env).
"""
import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.request


def chamar(url, corpo=None):
    req = urllib.request.Request(url, data=None if corpo is None else json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if corpo is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode() or "{}") | {"http": e.code}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lista")
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--inicio", default=str(datetime.date.today() - datetime.timedelta(days=150)))
    ap.add_argument("--fim", default=str(datetime.date.today()))
    ap.add_argument("--refazer", action="store_true", help="apaga o resultado anterior e roda de novo")
    ap.add_argument("--so", nargs="*", help="só estas ids da lista")
    a = ap.parse_args()
    cfg = chamar(f"{a.url}/api/arara/config")
    if not cfg.get("on_demand_available"):
        sys.exit("servidor sem credenciais Earthdata: " + cfg.get("on_demand_reason", "indisponível"))
    areas = json.load(open(a.lista, encoding="utf-8"))
    if a.so:
        areas = [x for x in areas if x["id"] in a.so]
    resultado = []
    for i, x in enumerate(areas, start=1):
        print(f"[{i}/{len(areas)}] {x['nome']}", flush=True)
        r = chamar(f"{a.url}/api/arara/analysis", {"name": x["nome"], "bbox": ",".join(map(str, x["bbox"])), "start": a.inicio,
                                                   "end": a.fim, "refresh": a.refazer})
        if r.get("http"):
            print(f"    recusada: {r.get('reason')}")
            resultado.append({"id": x["id"], "status": "recusada", "motivo": r.get("reason")})
            continue
        aid, job = r["analysis_id"], r.get("job_id")
        status = r["status"]
        while job and status in ("queued", "downloading", "processing"):
            time.sleep(15)
            j = chamar(f"{a.url}/api/arara/jobs/{job}")
            status = j["status"]
            print(f"    {status} {j.get('stage')} {int((j.get('progress') or 0) * 100)}%", flush=True)
        motivo = None
        if status != "completed":
            motivo = chamar(f"{a.url}/api/arara/jobs/{job}").get("reason") if job else None
            print(f"    {status}: {motivo}")
        else:
            print(f"    pronto: {a.url}/estudo/?id={aid}")
        resultado.append({"id": x["id"], "analysis_id": aid, "status": status, "motivo": motivo,
                          "estudo": f"/estudo/?id={aid}" if status == "completed" else None})
    print(json.dumps(resultado, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
