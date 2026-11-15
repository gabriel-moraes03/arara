import json
import os

import numpy as np

from arara_pipeline import change, water
from arara_pipeline.sar import db_filtrado
from gcov_sintetico import AGUA_DB, TERRA_DB, PIXEL_M, disco

N = 600
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cena(agua, agua_db=AGUA_DB, semente=0):
    rng = np.random.default_rng(semente)
    lin = (np.where(agua, 10 ** (agua_db / 10), 10 ** (TERRA_DB / 10)) * rng.gamma(4, 0.25, agua.shape)).astype("float32")
    valido = np.ones(agua.shape, bool)
    return db_filtrado(lin, valido), valido


def test_serie_recupera_area_e_usa_um_limiar_so():
    raios = [150, 148, 140, 135]
    dois_lagos = [disco(N, r, (200, 200)) | disco(N, 60, (480, 470)) for r in raios]
    pares = [cena(a, semente=i) for i, a in enumerate(dois_lagos)]
    aoi = np.ones((N, N), bool)
    r = water.classificar_serie([p[0] for p in pares], [p[1] for p in pares], aoi, PIXEL_M)
    assert -19 < r["threshold_db"] < -11 and not r["experimental"]
    for agua, verdade in zip(r["water"], dois_lagos):
        assert abs(agua.sum() - verdade.sum()) / verdade.sum() < 0.02
        # o lago menor não é descartado por não ser "o maior componente"
        assert agua[480, 470] and agua[200, 200]


def test_fora_da_aoi_nao_conta():
    agua = disco(N, 150, (300, 300))
    db, valido = cena(agua)
    aoi = np.zeros((N, N), bool)
    aoi[:, :300] = True
    r = water.classificar_serie([db], [valido], aoi, PIXEL_M)
    assert not r["water"][0][:, 300:].any()
    assert abs(r["water"][0].sum() - (agua & aoi).sum()) / (agua & aoi).sum() < 0.03


def test_sem_margem_agua_terra_vira_experimental():
    db, valido = cena(np.zeros((N, N), bool))
    r = water.classificar_serie([db], [valido], np.ones((N, N), bool), PIXEL_M)
    assert r["experimental"] and r["experimental_reasons"]


def test_vento_com_os_brilhos_reais_de_furnas():
    with open(os.path.join(RAIZ, "regression", "furnas", "serie.json"), encoding="utf-8") as f:
        serie = json.load(f)
    flags, ref = water.suspeita_vento([s["brilho_agua_hh_db"] for s in serie])
    assert flags == [s["suspeita_vento"] for s in serie]
    assert [s["data"] for s, f in zip(serie, flags) if f] == ["2026-09-07", "2026-10-01"]
    assert water.suspeita_vento([-20.0, -17.0]) == ([False, False], None)     # sem série, sem flag


def test_vento_marca_a_data_mas_nao_corrige():
    agua = disco(N, 150)
    pares = [cena(agua, semente=i) for i in range(4)] + [cena(agua, agua_db=AGUA_DB + 3.5, semente=9)]
    r = water.classificar_serie([p[0] for p in pares], [p[1] for p in pares], np.ones((N, N), bool), PIXEL_M)
    assert r["wind"] == [False, False, False, False, True]


def test_comparacao_em_hectares():
    a, b = disco(N, 150), disco(N, 140)
    b[:20, :20] = True
    valido = np.ones((N, N), bool)
    valido[-50:] = False
    classes, m = change.comparar(a, b, valido, PIXEL_M ** 2)
    assert m["retraction_ha"] == round((a & ~b & valido).sum() * 400 / 10000, 2)
    assert m["expansion_ha"] == 400 * 400 / 10000 == 16.0
    assert m["net_change_ha"] == round(m["expansion_ha"] - m["retraction_ha"], 2)
    assert m["water_km2_before"] == round(a.sum() * 400 / 1e6, 3)
    assert (classes[-50:] == change.SEM_DADO).all() and classes[300, 300] == change.AGUA_ESTAVEL
    assert sum(m["pixels"].values()) == N * N


def test_semente_adaptativa_acha_margem_com_agua_clara():
    """Água perto de -17 dB (delta do Jacuí, trilha 53 D): a semente de -20 dB não acha margem; a de -16 acha
    e o limiar fica entre água e terra, em vez de cair no Otsu da área toda."""
    from arara_pipeline import water
    rng = np.random.default_rng(3)
    n = 600                                      # blocos de 2 km = 100 px; a margem cai no meio de um bloco
    agua = np.zeros((n, n), bool)
    agua[:, :250] = True
    db = np.where(agua, -17.5, -7.0) + rng.normal(0, 0.8, (n, n))
    lim, problemas, blocos, semente = water.limiar_da_data(db, np.ones((n, n), bool), 20.0)
    assert semente == -16.0 and blocos >= 5 and not problemas
    assert -14.0 < lim < -12.0
    # água escura como em Furnas: continua na semente de -20 dB
    db2 = np.where(agua, -23.0, -7.0) + rng.normal(0, 0.8, (n, n))
    assert water.limiar_da_data(db2, np.ones((n, n), bool), 20.0)[3] == -20.0
