"""Validação contra a ANA (só Furnas): cota dos boletins -> área esperada pela curva cota × área,
comparada com a área medida pelo NISAR. Migrado de terrapulse/scripts/analise.py e exportar_web.py.

As datas com suspeita de vento ficam na série, marcadas, e fora das métricas principais.
"""
import csv

import numpy as np


def ler_csv(caminho):
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def ler_curva(caminho):
    """cota_m, area_km2 -> array (n, 2) ordenado pela cota."""
    return np.array(sorted((float(l["cota_m"]), float(l["area_km2"])) for l in ler_csv(caminho)))


def ler_cotas(caminho):
    """{AAAAMMDD: linha do boletim} a partir de data,cota_furnas_m,volume_util_pct,boletim_ana."""
    return {l["data"].replace("-", ""): l for l in ler_csv(caminho)}


def ler_areas(caminho):
    """{AAAAMMDD: area_km2} de um area_agua.csv."""
    return {l["data"]: float(l["area_km2"]) for l in ler_csv(caminho)}


def serie_ana(areas, cotas, curva, datas_vento=(), brilho=None):
    """Uma linha por data: cota, área esperada (curva ANA), área NISAR, deltas e flag de vento."""
    datas_vento = set(datas_vento)
    serie = []
    for d in sorted(set(areas) & set(cotas)):
        c = float(cotas[d]["cota_furnas_m"])
        esp = float(np.interp(c, curva[:, 0], curva[:, 1]))
        linha = {"data": f"{d[:4]}-{d[4:6]}-{d[6:]}", "cota_ana_m": c,
                 "volume_util_pct": float(cotas[d]["volume_util_pct"]),
                 "boletim_ana": cotas[d]["boletim_ana"],
                 "area_esperada_km2": round(esp, 1), "area_nisar_km2": areas[d],
                 "suspeita_vento": d in datas_vento}
        if brilho is not None:
            linha["brilho_agua_hh_db"] = brilho[d]
        serie.append(linha)
    for s in serie:
        s["delta_esperado_km2"] = round(s["area_esperada_km2"] - serie[0]["area_esperada_km2"], 1)
        s["delta_nisar_km2"] = round(s["area_nisar_km2"] - serie[0]["area_nisar_km2"], 1)
        s["diferenca_km2"] = round(s["area_nisar_km2"] - s["area_esperada_km2"], 1)
        s["diferenca_pct"] = round(100 * s["diferenca_km2"] / s["area_esperada_km2"], 2)
    return serie


def metricas_ana(serie, curva):
    """Concordância NISAR × ANA. As métricas principais usam só as datas sem suspeita de vento."""
    cal = [s for s in serie if not s["suspeita_vento"]]
    vento = [s for s in serie if s["suspeita_vento"]]
    dif = np.array([s["diferenca_km2"] for s in cal])
    cc = np.array([s["cota_ana_m"] for s in cal])
    aa = np.array([s["area_nisar_km2"] for s in cal])
    todas_c = np.array([s["cota_ana_m"] for s in serie])
    faixa = (curva[:, 0] >= todas_c.min() - 1e-9) & (curva[:, 0] <= todas_c.max() + 1e-9)
    i_max, i_min = int(np.argmax(todas_c)), int(np.argmin(todas_c))
    incl, inter = np.polyfit(cc, aa, 1)
    m = {
        "n_datas": len(serie), "n_datas_calmas": len(cal),
        "erro_abs_medio_km2": round(float(np.mean(np.abs(dif))), 1),
        "erro_abs_medio_pct": round(float(np.mean([abs(s["diferenca_pct"]) for s in cal])), 1),
        "vies_km2": round(float(np.mean(dif)), 1),
        "ruido_dp_km2": round(float(np.std(dif, ddof=1)), 1),
        "inclinacao_nisar_km2_por_m": round(float(incl), 1),
        "intercepto_nisar_km2": round(float(inter), 1),
        "inclinacao_ana_km2_por_m": round(float(np.polyfit(curva[faixa, 0], curva[faixa, 1], 1)[0]), 1),
        "r_cota_area": round(float(np.corrcoef(cc, aa)[0, 1]), 2),
        "cota_max_m": float(todas_c[i_max]), "cota_max_data": serie[i_max]["data"],
        "cota_min_m": float(todas_c[i_min]), "cota_min_data": serie[i_min]["data"],
        "queda_cota_m": round(float(todas_c[i_max] - todas_c[i_min]), 2),
        "variacao_area_esperada_km2": round(serie[i_max]["area_esperada_km2"] - serie[i_min]["area_esperada_km2"], 1),
        "erro_abs_medio_todas_km2": round(float(np.mean([abs(s["diferenca_km2"]) for s in serie])), 1),
        "area_esperada_faixa_km2": [min(s["area_esperada_km2"] for s in serie),
                                    max(s["area_esperada_km2"] for s in serie)],
        "area_nisar_calmas_faixa_km2": [float(aa.min()), float(aa.max())],
    }
    if vento:
        m["pior_diferenca_vento_km2"] = min(s["diferenca_km2"] for s in vento)
    if all("brilho_agua_hh_db" in s for s in serie):
        m["brilho_agua_calmas_db"] = round(float(np.mean([s["brilho_agua_hh_db"] for s in cal])), 1)
        m["brilho_agua_vento_db"] = [s["brilho_agua_hh_db"] for s in vento]
    return m
