"""Gera frontend/globe/sul.json: municípios de PR, SC e RS (nome, UF, centro) para a busca do globo.

    .venv/bin/python scripts/gerar_municipios_sul.py

Fonte: APIs públicas do IBGE (localidades e malhas v3, qualidade mínima). O centro é um ponto
dentro do polígono (representative_point), não o centroide, para cair sempre no município.
"""
import json
import os

import requests
from shapely.geometry import shape

IBGE = "https://servicodados.ibge.gov.br/api"
UFS = {"41": "PR", "42": "SC", "43": "RS"}


def main():
    out = []
    for cod, sigla in UFS.items():
        malha = requests.get(f"{IBGE}/v3/malhas/estados/{cod}?formato=application/vnd.geo%2Bjson"
                             "&intrarregiao=municipio&qualidade=minima", timeout=120).json()
        nomes = {str(m["id"]): m["nome"] for m in requests.get(f"{IBGE}/v1/localidades/estados/{cod}/municipios", timeout=60).json()}
        for f in malha["features"]:
            c = str(f["properties"]["codarea"])
            g = shape(f["geometry"])
            p = g.representative_point()
            b = g.bounds
            out.append([nomes.get(c, c), sigla, round(p.x, 4), round(p.y, 4), [round(v, 3) for v in b]])
    out.sort(key=lambda m: (m[1], m[0]))
    destino = os.path.join(os.path.dirname(__file__), "..", "frontend", "globe", "sul.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"fonte": "IBGE, malhas v3 (qualidade mínima) e localidades", "municipios": out}, f, ensure_ascii=False, separators=(",", ":"))
    print(len(out), "municípios ->", os.path.normpath(destino))


if __name__ == "__main__":
    main()
