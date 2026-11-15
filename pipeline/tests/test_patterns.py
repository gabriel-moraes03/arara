import json
import os

import numpy as np
import pytest

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


# ---------- rodada 2: permanência sem datas de vento, alerta preso ao ruído da série ----------

def test_permanencia_ignora_data_com_vento():
    n = 40
    lago = np.zeros((n, n), bool)
    lago[:, :20] = True
    aguas = [lago.copy() for _ in range(9)]
    aguas[2] = np.zeros((n, n), bool)                          # dia de vento: a água some do radar
    vento = [i == 2 for i in range(9)]
    cls, info = patterns.permanencia(aguas, np.ones((n, n), bool), vento)
    assert (cls[:, :20] == patterns.PERMANENTE).all() and info["n_dates"] == 8 and info["n_wind_excluded"] == 1
    assert info["note"] == patterns.VENTO_FORA
    sem_excluir, _ = patterns.permanencia(aguas, np.ones((n, n), bool))
    assert not (sem_excluir == patterns.PERMANENTE).any()     # o bug: 8/9 < 90% derrubava tudo para sazonal
    assert patterns.permanencia(aguas[:3], np.ones((n, n), bool), [True, False, False])[0] is None


FURNAS_2E7B = os.path.join(RAIZ, "data", "analyses", "2e7b08493f2ac033578b8a88")


@pytest.mark.skipif(not os.path.isdir(os.path.join(FURNAS_2E7B, "cog")), reason="análise 2e7b0849 de Furnas não está no disco")
def test_furnas_2e7b0849_tem_agua_permanente():
    import rasterio
    r = json.load(open(os.path.join(FURNAS_2E7B, "result.json"), encoding="utf-8"))
    aguas = []
    for d in r["dates"]:
        with rasterio.open(os.path.join(FURNAS_2E7B, "cog", f"water_{d['date'].replace('-', '')}.tif")) as src:
            aguas.append(src.read(1) == 1)
    vento = [d["suspeita_vento"] for d in r["dates"]]
    assert vento.count(True) == 1                                # 18/07
    cls, _ = patterns.permanencia(aguas, np.ones(aguas[0].shape, bool), vento)
    resumo = patterns.resumo_permanencia(cls, r["pixel_area_m2"])
    assert resumo["permanent_km2"] > 100                         # a lâmina principal (~150 km²) é permanente


# série real da análise 2e7b0849 (Furnas): a última passagem fica 12,9 km² abaixo do normal, menos que o
# ruído entre passagens (15,1 km²); o alerta dizia "atenção" e a leitura dizia "dentro do ruído"
FURNAS_DATAS = ["2026-06-24", "2026-07-06", "2026-07-18", "2026-08-11", "2026-08-23", "2026-09-04", "2026-09-16", "2026-09-28", "2026-10-10"]
FURNAS_AREAS = [161.546, 165.821, 7.004, 165.279, 188.47, 160.941, 151.586, 167.547, 152.421]
FURNAS_VENTO = [False, False, True, False, False, False, False, False, False]


def test_alerta_dentro_do_ruido_e_normal_e_nao_contradiz_a_leitura():
    from arara_pipeline import insights
    a = patterns.anomalia(FURNAS_DATAS, FURNAS_AREAS, FURNAS_VENTO)
    assert a["level"] == "normal" and a["within_noise"] and abs(a["z"]) >= 2      # z alto, mas dentro do ruído
    assert abs(a["deviation_km2"]) < a["series_noise_km2"]
    datas = [{"date": d, "water_km2": x, "suspeita_vento": v} for d, x, v in zip(FURNAS_DATAS, FURNAS_AREAS, FURNAS_VENTO)]
    comp = {"before": FURNAS_DATAS[0], "after": FURNAS_DATAS[-1], "water_km2_before": 161.546, "water_km2_after": 152.421,
            "expansion_ha": 470.3, "retraction_ha": 1382.9, "net_change_ha": -912.5, "wind_caveat": False}
    leitura = insights.interpretar(datas, comp, alerta=a)
    assert "within_noise" in leitura["flags"] and leitura["series_noise_km2"] == a["series_noise_km2"]


def test_alerta_fora_do_ruido_continua_alertando_e_a_leitura_admite():
    from arara_pipeline import insights
    d = [f"2026-0{i + 1}-01" for i in range(7)]
    a = patterns.anomalia(d, [100, 101, 99, 100.5, 99.5, 100, 93.8])   # última: -6 km², ruído ~1
    assert a["level"] in ("atenção", "alerta") and not a["within_noise"]
    datas = [{"date": x, "water_km2": v, "suspeita_vento": False} for x, v in zip(d, [100, 101, 99, 100.5, 99.5, 100, 93.8])]
    comp = {"before": d[0], "after": d[-1], "water_km2_before": 100, "water_km2_after": 93.8, "expansion_ha": 0,
            "retraction_ha": 620, "net_change_ha": -620, "wind_caveat": False}
    assert "Recuo" in insights.interpretar(datas, comp, alerta=a)["hypothesis"]
    # primeira x última dentro do ruído, mas a última fora da faixa: a leitura não pode dizer só "sem mudança"
    falso = dict(a, level="atenção", direction="abaixo")
    ruido = insights.interpretar([dict(x, water_km2=v) for x, v in zip(datas, [94, 101, 99, 100.5, 99.5, 100, 93.8])],
                                 dict(comp, water_km2_before=94, net_change_ha=-20, retraction_ha=20), alerta=falso)
    assert "within_noise" in ruido["flags"] and "faixa normal" in ruido["hypothesis"]
