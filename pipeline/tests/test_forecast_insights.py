import json
import os

from arara_pipeline import forecast, insights

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def serie_furnas():
    with open(os.path.join(RAIZ, "regression", "furnas", "serie.json"), encoding="utf-8") as f:
        s = json.load(f)
    return [x["data"] for x in s], [x["area_nisar_km2"] for x in s], [x["suspeita_vento"] for x in s]


def test_projecao_na_serie_real_de_furnas_e_sempre_experimental():
    datas, areas, vento = serie_furnas()
    p = forecast.projetar(datas, areas, vento)
    assert p["status"] == "ok" and p["experimental"] is True and p["n_dates_used"] == 7
    assert [x["days_ahead"] for x in p["points"]] == [12, 24, 36]
    assert [x["date"] for x in p["points"]] == ["2026-10-25", "2026-11-06", "2026-11-18"]
    for x in p["points"]:
        assert x["p10"] <= x["water_km2"] <= x["p90"]
        assert 950 < x["water_km2"] < 1090             # perto do último valor medido (1.019,8 km²)
    larguras = [x["p90"] - x["p10"] for x in p["points"]]
    assert larguras == sorted(larguras) and larguras[0] > 0      # a incerteza cresce com o horizonte


def test_projecao_ignora_vento_e_exige_quatro_datas():
    datas, areas, vento = serie_furnas()
    sem = forecast.projetar(datas, areas, vento)
    com = forecast.projetar(datas, areas, [False] * len(datas))
    assert sem["points"] != com["points"]
    pouco = forecast.projetar(datas[:5], areas[:5], [False, False, True, True, False])
    assert pouco["status"] == "unavailable" and "4" in pouco["reason"]


def test_projecao_respeita_zero_e_o_teto_da_area():
    p = forecast.projetar(["2026-01-01", "2026-01-13", "2026-01-25", "2026-02-06"], [3.0, 2.0, 1.0, 0.1])
    assert all(x["p10"] >= 0 and x["water_km2"] >= 0 for x in p["points"])
    p = forecast.projetar(["2026-01-01", "2026-01-13", "2026-01-25", "2026-02-06"], [7.0, 8.0, 9.0, 9.9], teto_km2=10)
    assert all(x["p90"] <= 10 for x in p["points"])


def comp(antes, depois, vento=False):
    d = depois - antes
    return {"before": "2026-06-27", "after": "2026-10-13", "water_km2_before": antes, "water_km2_after": depois,
            "expansion_ha": max(d, 0) * 100, "retraction_ha": max(-d, 0) * 100, "net_change_ha": d * 100, "wind_caveat": vento}


def datas(valores, vento=()):
    return [{"date": f"2026-0{i + 1}-01", "water_km2": v, "suspeita_vento": i in vento} for i, v in enumerate(valores)]


def test_medido_separado_de_hipotese():
    r = insights.interpretar(datas([100, 99, 97, 90]), comp(100, 90))
    assert "100.00 para 90.00 km²" in r["measured"] and "-10.0%" in r["measured"]
    assert "Recuo" in r["hypothesis"] and r["confidence"] == "baixa" and "ANA" in r["check"]
    # nada de causa dentro do campo "medido"
    assert not any(p in r["measured"].lower() for p in ("estiagem", "chuva", "causa", "porque"))


def test_vento_ruido_e_validacao_mudam_a_confianca():
    vento = insights.interpretar(datas([100, 99, 97, 90], vento={3}), comp(100, 90, vento=True))
    assert "vento" in vento["hypothesis"] and vento["confidence"] == "baixa" and "wind" in vento["flags"]
    ruido = insights.interpretar(datas([100, 103, 99, 100.5]), comp(100, 100.5))
    assert "within_noise" in ruido["flags"]
    val = {"status": "validated", "mean_iou": 0.85}
    assert insights.interpretar(datas([100, 99, 97, 90]), comp(100, 90), val)["confidence"] == "média"
    assert insights.interpretar(datas([100, 99, 97, 90]), comp(100, 90), val, experimental=True)["confidence"] == "baixa"
    assert insights.interpretar(datas([100, 104, 108, 120]), comp(100, 120))["hypothesis"].startswith("Avanço")
    so_uma = insights.interpretar(datas([100]), None)
    assert so_uma["hypothesis"] is None and so_uma["flags"] == ["single_date"]
