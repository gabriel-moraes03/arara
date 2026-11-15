"""
Sensibilidade do estudo Barra Grande + Machadinho à resolução. NÃO substitui o resultado oficial
(estudo_uruguai.py, pixel de 40 m): só recalcula a série a 20 m nativo, com média 5x5 e 3x3 em dB,
o MESMO limiar da série, o mesmo polígono, a mesma máscara de encostas e a mesma área esperada.

    python pipeline/scripts/sensibilidade_uruguai.py --h5 <pasta dos 7 .h5>

Saída: regression/barra_machadinho/sensibilidade.json e frontend/uruguai/data/sensibilidade.json.
"""
import argparse
import glob
import json
import os
import sys

import h5py
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from arara_pipeline.geom import caixa_do_poligono, km2, ler_poligono_geojson, mascara_do_poligono, tirar_manchas  # noqa: E402
from arara_pipeline.sar import GRADE, coordenadas_recorte, data_do_nome, db_filtrado, valido_da_mask  # noqa: E402
from arara_pipeline.validate_ana import ler_csv, ler_curva  # noqa: E402
from estudo_uruguai import FATOR_RTC_LAYOVER, FATOR_RTC_SOMBRA, RESERVATORIOS, fator_rtc  # noqa: E402


def ler_linear(arquivo, caixa, passo=1):
    """HH em potência linear e validade (mask 0 e 255 inválidos), na grade de coordenadas_recorte."""
    with h5py.File(arquivo, "r") as h:
        g = h[GRADE]
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        x0, x1, y0, y1 = caixa
        cols = np.where((x >= min(x0, x1)) & (x <= max(x0, x1)))[0]
        rows = np.where((y >= min(y0, y1)) & (y <= max(y0, y1)))[0]
        r, c = slice(rows[0], rows[-1] + 1, passo), slice(cols[0], cols[-1] + 1, passo)
        hh = g["HHHH"][r, c].astype("float32")
        valido = np.isfinite(hh) & (hh > 0) & valido_da_mask(g["mask"][r, c])
        return hh, valido, abs(x[1] - x[0]) * passo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--h5", required=True)
    ap.add_argument("--ana", default=os.path.join("data", "ana"))
    ap.add_argument("--regressao", default=os.path.join("regression", "barra_machadinho"))
    ap.add_argument("--web", default=os.path.join("frontend", "uruguai", "data"))
    args = ap.parse_args()
    meta = json.load(open(os.path.join(args.regressao, "meta.json"), encoding="utf-8"))
    limiar = meta["metodo"]["limiar_db"]
    arquivos = sorted(glob.glob(os.path.join(args.h5, "*.h5")), key=data_do_nome)
    cotas = ler_csv(os.path.join(args.ana, "cota_uruguai_ana.csv"))
    saida = {"limiar_db": limiar, "nota": "sensibilidade à resolução; o resultado oficial é o de 40 m", "variantes": {}}
    for chave, info in RESERVATORIOS.items():
        aneis = ler_poligono_geojson(os.path.join(args.ana, f"{chave}_poligono.geojson"), 32722)
        caixa = caixa_do_poligono(aneis, 2000)
        xs, ys = coordenadas_recorte(arquivos[0], caixa, 1)
        dentro = mascara_do_poligono(aneis, xs, ys)
        lidos = {data_do_nome(a): ler_linear(a, caixa) for a in arquivos}
        valido_sempre = np.logical_and.reduce([v for _, v, _ in lidos.values()])
        fator, _ = fator_rtc(arquivos[0], caixa, 1)
        zona = dentro & valido_sempre & ~((fator < FATOR_RTC_SOMBRA) | (fator > FATOR_RTC_LAYOVER))
        frac = zona.sum() / dentro.sum()
        curva = ler_curva(os.path.join(args.ana, f"{chave}_cota_area.csv"))
        cota = {l["data"].replace("-", ""): float(l["cota_m"]) for l in cotas if l["reservatorio"] == info["ana"]}
        for tamanho in (5, 3):
            nome = f"20m_{tamanho}x{tamanho}"
            linhas = []
            for d, (hh, valido, px) in lidos.items():
                db = db_filtrado(hh, valido, "db", tamanho)
                area = km2(tirar_manchas((db < limiar) & valido & dentro, px) & zona, px)
                esp = float(np.interp(cota[d], curva[:, 0], curva[:, 1])) * frac
                linhas.append({"data": d, "area_nisar_km2": area, "area_esperada_km2": round(esp, 1),
                               "diferenca_pct": round(100 * (area - esp) / esp, 1)})
            erro = round(float(np.mean([abs(l["diferenca_pct"]) for l in linhas])), 1)
            saida["variantes"].setdefault(nome, {})[chave] = {"erro_abs_medio_pct": erro, "fracao_usada": round(float(frac), 4),
                                                              "datas": linhas}
            print(f"{info['nome']} {nome}: erro abs médio {erro}% | " + " ".join(f"{l['diferenca_pct']:+.1f}" for l in linhas))
    oficial = {k: meta["metricas"][k]["todas"]["erro_abs_medio_pct"] for k in RESERVATORIOS}
    saida["variantes"]["40m_5x5_oficial"] = {k: {"erro_abs_medio_pct": v} for k, v in oficial.items()}
    for pasta in (args.regressao, args.web):
        with open(os.path.join(pasta, "sensibilidade.json"), "w", encoding="utf-8") as f:
            json.dump(saida, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
