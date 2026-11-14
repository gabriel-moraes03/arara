"""Sentinel-2: itens STAC REAIS gravados (Pantanal, Earth Search); a leitura dos COGs é trocada por
arrays sintéticos nos testes (a leitura real é provada à parte, com rede)."""
import json
import os

import numpy as np

from arara_pipeline import crossval, optical_s2
from gcov_sintetico import disco

N = 200


def itens():
    with open(os.path.join(os.path.dirname(__file__), "data", "stac_s2_pantanal.json"), encoding="utf-8") as f:
        return json.load(f)["features"]


def test_candidatos_mais_perto_da_data_primeiro():
    c = optical_s2.candidatos(itens(), "2026-07-05")
    assert [dia for dia, _, _ in c][:2] == ["2026-07-01", "2026-07-09"] and c[0][1] == 4   # empatam em 4 dias: menos nuvem
    assert c[-1][0] == "2026-07-04"                    # 99,99% de nuvem no tile: por último


def test_offset_nao_e_aplicado_duas_vezes():
    it = itens()[0]
    assert it["properties"]["earthsearch:boa_offset_applied"] is True and optical_s2.offset_do_item(it) == 0
    cru = {"properties": {"s2:processing_baseline": "05.12"}}
    antigo = {"properties": {"s2:processing_baseline": "03.01"}}
    assert optical_s2.offset_do_item(cru) == -1000 and optical_s2.offset_do_item(antigo) == 0


def test_mndwi_e_mascara_scl():
    verde = np.full((4, 4), 600, "uint16")
    swir = np.full((4, 4), 2000, "uint16")
    verde[:2], swir[:2] = 500, 100                    # água: verde > SWIR
    scl = np.full((4, 4), 4, "uint8")
    scl[0, 0], scl[3, 3], scl[0, 1] = 9, 3, 6         # nuvem, sombra de nuvem, água
    verde[1, 1] = 0                                   # sem dado
    agua, valido, _ = optical_s2.agua_mndwi(verde, swir, scl)
    assert not valido[0, 0] and not valido[3, 3] and not valido[1, 1] and valido[0, 1]
    assert agua[0, 1] and agua[1, 0] and not agua[2:].any() and not agua[0, 0]
    # com o +1000 embutido e não removido, a mesma água some; removendo, volta
    assert not optical_s2.agua_mndwi(verde + 1000, swir + 1000, scl)[0][2:].any()
    np.testing.assert_array_equal(optical_s2.agua_mndwi(verde + 1000, swir + 1000, scl, -1000)[0], agua)


def leitor(nuvem_no_dia):
    def ler(item, xs, ys, epsg):
        agua = disco(N, 60)
        verde = np.where(agua, 500, 600).astype("uint16")
        swir = np.where(agua, 100, 2000).astype("uint16")
        nublado = item["properties"]["datetime"][:10] in nuvem_no_dia
        return verde, swir, np.full((N, N), 9 if nublado else 4, "uint8")
    return ler


def test_referencia_pula_dia_nublado_e_declara_quando_nao_ha():
    xs, ys, aoi = np.arange(N) * 20.0, -np.arange(N) * 20.0, np.ones((N, N), bool)
    r = optical_s2.referencia(None, "2026-07-05", xs, ys, 32721, aoi, itens=itens(), ler=leitor({"2026-07-01"}))
    assert r["status"] == "ok" and r["date"] == "2026-07-09" and r["days_apart"] == 4 and r["clear_fraction"] == 1.0
    tudo = {"2026-07-04", "2026-07-09", "2026-07-01", "2026-06-29"}
    r = optical_s2.referencia(None, "2026-07-05", xs, ys, 32721, aoi, itens=itens(), ler=leitor(tudo))
    assert r["status"] == "not_optically_validated" and "nuvem" in r["reason"]
    r = optical_s2.referencia(None, "2026-07-05", xs, ys, 32721, aoi, itens=[])
    assert r["status"] == "not_optically_validated"


def test_metricas_de_concordancia():
    sar, opt = disco(N, 60), disco(N, 50)
    valido = np.ones((N, N), bool)
    m = crossval.metricas(sar, opt, valido, 400.0, 20.0)
    assert m["recall"] == 1.0 and m["false_negative"] == 0
    assert m["iou"] == round(opt.sum() / sar.sum(), 4) == m["precision"]
    assert m["f1"] == round(2 * opt.sum() / (opt.sum() + sar.sum()), 4)
    assert m["sar_only_ha"] == round((sar.sum() - opt.sum()) * 400 / 1e4, 2)
    assert 0 < m["disagreement_median_m"] <= 200
    igual = crossval.metricas(sar, sar, valido, 400.0, 20.0)
    assert igual["iou"] == igual["f1"] == igual["accuracy"] == 1.0
    assert crossval.metricas(sar, opt, np.zeros((N, N), bool), 400.0)["iou"] is None
