import json
import os

import numpy as np

from arara_pipeline import patterns

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def furnas():
    s = json.load(open(os.path.join(RAIZ, "regression", "furnas", "serie.json"), encoding="utf-8"))
    return [x["data"] for x in s], [x["area_nisar_km2"] for x in s], [x["suspeita_vento"] for x in s]


def test_tendencia_robusta_na_serie_real_de_furnas():
    d, a, v = furnas()
    t = patterns.tendencia(d, a, v)
    assert t["status"] == "ok" and t["n_dates"] == 7 and t["direction"] in ("perdendo", "ganhando")
    sem = patterns.tendencia(d, a, [False] * len(d))
    assert sem["km2_per_week"] != t["km2_per_week"]                 # as datas de vento mudam o ajuste
    assert patterns.tendencia(d[:3], a[:3])["status"] == "unavailable"
    crescente = patterns.tendencia(["2026-01-01", "2026-01-13", "2026-01-25", "2026-02-06"], [1, 2, 3, 4])
    assert crescente["direction"] == "ganhando" and abs(crescente["km2_per_week"] - 7 / 12) < 1e-3


def test_alerta_compara_a_ultima_com_o_normal():
    d, a, v = furnas()
    r = patterns.anomalia(d, a, v)
    assert r["status"] == "ok" and r["last_is_wind_suspect"] is False and r["level"] in ("normal", "atenção", "alerta")
    seco = patterns.anomalia(["a"] * 6, [100, 101, 99, 100, 100.5, 60])
    assert seco["level"] == "alerta" and seco["direction"] == "abaixo" and seco["pct_vs_normal"] < -30
    assert patterns.anomalia(["a"] * 6, [100, 101, 99, 100, 100.5, 100.2])["level"] == "normal"


def test_permanencia_separa_leito_varzea_e_enchente():
    n = 60
    base = np.zeros((n, n), bool)
    datas = []
    for i in range(10):
        m = base.copy(); m[:, :20] = True                      # leito: sempre
        if i < 5: m[:, 20:40] = True                          # várzea: metade das datas
        if i == 3: m[:, 40:50] = True                         # enchente rara: 1 de 10
        datas.append(m)
    cls, info = patterns.permanencia(datas, np.ones((n, n), bool))
    assert (cls[:, :20] == patterns.PERMANENTE).all() and (cls[:, 20:40] == patterns.SAZONAL).all()
    assert (cls[:, 40:50] == patterns.OCASIONAL).all() and (cls[:, 50:] == 0).all()
    assert patterns.resumo_permanencia(cls, 400.0)["permanent_km2"] == round(60 * 20 * 400 / 1e6, 3)
    assert patterns.permanencia(datas[:2], np.ones((n, n), bool))[0] is None


def test_trechos_que_mais_secaram_com_coordenadas():
    n = 100
    ret = np.zeros((n, n), bool)
    ret[10:30, 10:50] = True          # 800 px
    ret[60:70, 60:70] = True          # 100 px
    ret[90, 90] = True                # ruído de 1 px (fora: < 1 ha)
    xs = 400000 + 20.0 * np.arange(n); ys = 7700000 - 20.0 * np.arange(n)
    t = patterns.trechos_secos(ret, xs, ys, 32723, 400.0)
    assert [x["rank"] for x in t] == [1, 2] and t[0]["area_ha"] == 800 * 400 / 1e4
    assert -70 < t[0]["lon"] < -30 and -40 < t[0]["lat"] < 0 and t[0]["bbox"][0] < t[0]["lon"] < t[0]["bbox"][2]
