"""Baixa as Circunscrições Hidrográficas (CHs) de Minas Gerais do GeoServer da IDE-Sisema/IGAM e grava
frontend/globe/bacias_mg.json, simplificado para o globo (contorno só para exibir, não para medir).

    python pipeline/scripts/exportar_bacias.py [--tolerancia 0.004]

Fonte: IDE-Sisema / IGAM, camada ide_1108_mg_circunscricoes_hidrograficas_pol (base GEIRH).
"""
import argparse
import json
import os
import urllib.parse
import urllib.request

from shapely.geometry import shape

WFS = "https://geoserver.meioambiente.mg.gov.br/IDE/ows"
CAMADA = "IDE:ide_1108_mg_circunscricoes_hidrograficas_pol"
SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend", "globe", "bacias_mg.json")


def baixar():
    q = urllib.parse.urlencode({"service": "WFS", "version": "1.0.0", "request": "GetFeature", "typeName": CAMADA,
                                "outputFormat": "application/json", "srsName": "EPSG:4326"})
    with urllib.request.urlopen(f"{WFS}?{q}", timeout=180) as r:
        return json.load(r)


def limpo(s):
    return " ".join(str(s or "").replace("\xa0", " ").split())


def arredondar(g, casas=4):
    def r(c):
        return [round(c[0], casas), round(c[1], casas)] if isinstance(c[0], (int, float)) else [r(x) for x in c]
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerancia", type=float, default=0.004, help="simplificação em graus (padrão 0,004 ≈ 400 m)")
    ap.add_argument("--saida", default=SAIDA)
    a = ap.parse_args()
    feats = []
    for f in baixar()["features"]:
        p, geo = f["properties"], shape(f["geometry"])
        s = geo.simplify(a.tolerancia, preserve_topology=True)
        oeste, sul, leste, norte = geo.bounds
        feats.append({"type": "Feature", "geometry": arredondar(s.__geo_interface__), "properties": {
            "k": "bacia-" + str(p["sigla"]).lower(), "sigla": p["sigla"], "n": limpo(p["nome"]), "uge": limpo(p.get("uge_nm")),
            "ueg": p.get("sigla_ueg"), "cbh": p.get("cbh"), "situ_cbh": p.get("situ_cbh"), "descr": limpo(p.get("descrio")),
            "federal": limpo(p.get("bacia_fede")), "area_km2": round(p["area_km2"]), "decreto": limpo(p.get("decreto")),
            "bbox": [round(oeste, 4), round(sul, 4), round(leste, 4), round(norte, 4)]}})
    feats.sort(key=lambda f: f["properties"]["sigla"])
    out = {"type": "FeatureCollection", "fonte": "IDE-Sisema / IGAM, Circunscrições Hidrográficas de MG (GEIRH)", "features": feats}
    with open(a.saida, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(feats)} bacias, {os.path.getsize(a.saida) / 1e6:.2f} MB -> {os.path.normpath(a.saida)}")


if __name__ == "__main__":
    main()
