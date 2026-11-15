"""Gera a vitrine estática do Arara: o mesmo globo e o mesmo estudo automático, lendo análises já
concluídas de arquivos, sem backend, sem pipeline e sem credencial (para GitHub Pages).

    python scripts/exportar_vitrine.py --servidor http://localhost:8081 --ids <id> <id> ... [--saida dist/vitrine]

As análises são lidas pela API do servidor no ar (a mesma resposta que o globo recebe, já com o
controle de qualidade aplicado). A interface não é duplicada: as páginas de frontend/ são copiadas e
recebem só `window.ARARA_STATIC = true`. Teste com:

    python -m http.server 8090 -d dist/vitrine
"""
import argparse
import json
import os
import shutil
import sys
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAG = '<script>window.ARARA_STATIC = true;</script>\n'


def baixar(servidor, caminho):
    with urllib.request.urlopen(urllib.parse.urljoin(servidor, caminho), timeout=120) as r:
        return r.read()


def gravar(destino, dados):
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "wb") as f:
        f.write(dados)


def marcar_estatico(html):
    """Liga o modo vitrine antes do primeiro <script> da página."""
    with open(html, encoding="utf-8") as f:
        texto = f.read()
    i = texto.index("<script")
    with open(html, "w", encoding="utf-8") as f:
        f.write(texto[:i] + FLAG + texto[i:])


def exportar(servidor, ids, saida):
    if os.path.isdir(saida):
        shutil.rmtree(saida)                      # a pasta de saída é sempre gerada do zero
    front = os.path.join(RAIZ, "frontend")
    shutil.copytree(os.path.join(front, "globe"), saida)
    shutil.copytree(os.path.join(front, "estudo"), os.path.join(saida, "estudo"))
    shutil.copytree(os.path.join(front, "furnas"), os.path.join(saida, "furnas"))
    shutil.copytree(os.path.join(front, "uruguai"), os.path.join(saida, "uruguai"))
    marcar_estatico(os.path.join(saida, "index.html"))
    marcar_estatico(os.path.join(saida, "estudo", "index.html"))

    lista = json.loads(baixar(servidor, "/api/arara/analyses?status=completed"))
    por_id = {a["analysis_id"]: a for a in lista["analyses"]}
    faltando = [i for i in ids if i not in por_id]
    if faltando:
        raise SystemExit(f"análises não encontradas (ou não concluídas) no servidor: {', '.join(faltando)}")
    escolhidas = [por_id[i] for i in ids]
    for a in escolhidas:
        aid = a["analysis_id"]
        base = os.path.join(saida, "data", "analyses", aid)
        detalhe = json.loads(baixar(servidor, f"/api/arara/analyses/{aid}"))
        detalhe.pop("layers_url", None)
        gravar(os.path.join(base, "analysis.json"), json.dumps(detalhe, ensure_ascii=False).encode("utf-8"))
        gravar(os.path.join(base, "sources.json"), baixar(servidor, f"/api/arara/analyses/{aid}/sources"))
        gravar(os.path.join(base, "metrics.json"), baixar(servidor, f"/api/arara/analyses/{aid}/metrics"))
        gravar(os.path.join(base, "metrics.csv"), baixar(servidor, f"/api/arara/analyses/{aid}/metrics?format=csv"))
        for camada in detalhe.get("layers", []):
            gravar(os.path.join(base, "png", camada["id"] + ".png"),
                   baixar(servidor, f"/api/arara/analyses/{aid}/png/{camada['id']}.png"))
        q = detalhe.get("quality", "?")
        print(f"{aid}  {a.get('name') or ''}  [{q}]  {len(detalhe.get('layers', []))} camadas")
    gravar(os.path.join(saida, "data", "analyses.json"),
           json.dumps({"count": len(escolhidas), "analyses": escolhidas}, ensure_ascii=False).encode("utf-8"))
    gravar(os.path.join(saida, ".nojekyll"), b"")         # GitHub Pages: servir as pastas como estão

    # nada de credencial ou endereço do servidor dentro da vitrine
    for pasta, _, arquivos in os.walk(os.path.join(saida, "data")):
        for nome in arquivos:
            if nome.endswith((".json", ".csv")):
                texto = open(os.path.join(pasta, nome), encoding="utf-8").read()
                if "EARTHDATA" in texto or "password" in texto.lower():
                    raise SystemExit(f"{nome}: conteúdo sensível na exportação; abortado")
    tamanho = sum(os.path.getsize(os.path.join(p, n)) for p, _, ns in os.walk(saida) for n in ns)
    print(f"vitrine em {saida} ({tamanho / 1e6:.1f} MB, {len(escolhidas)} análises)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--servidor", default="http://localhost:8081", help="servidor do Arara no ar, com as análises")
    ap.add_argument("--ids", nargs="+", required=True, help="ids das análises concluídas a incluir")
    ap.add_argument("--saida", default=os.path.join(RAIZ, "dist", "vitrine"))
    a = ap.parse_args(argv)
    exportar(a.servidor.rstrip("/") + "/", a.ids, os.path.abspath(a.saida))


if __name__ == "__main__":
    sys.exit(main())
