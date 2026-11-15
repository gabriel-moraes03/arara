"""Catálogo: usa uma resposta REAL gravada da ASF Search API (Pantanal, 01/06 a 14/11/2026;
listas de browse/s3 encurtadas para o arquivo ficar pequeno)."""
import json
import os

import pytest

from arara_pipeline import catalog_nisar as cat

AOI = [-57.6, -18.6, -57.2, -18.2]


@pytest.fixture(scope="module")
def cenas():
    with open(os.path.join(os.path.dirname(__file__), "data", "asf_gcov_pantanal.json"), encoding="utf-8") as f:
        return [cat.cena_de_feature(x) for x in json.load(f)["features"]]


def test_maturidade():
    assert cat.maturidade("NISAR_L2_GCOV_PROVISIONAL_V1") == "PROVISIONAL"
    assert cat.maturidade("NISAR_L2_GCOV_V1") == "VALIDATED"
    assert cat.maturidade("NISAR_L2_GCOV_BETA_V1") == "BETA"


def test_cena_normalizada(cenas):
    c = next(c for c in cenas if c["granule"].endswith("20261105T215600_20261105T215634_P05036_N_F_J_001"))
    assert (c["track"], c["direction"], c["frame"], c["mode"], c["crid"]) == (10, "D", 98, "2005", "P05036")
    assert c["collection"] == "NISAR_L2_GCOV_V1" and c["maturity"] == "VALIDATED"
    assert c["polarizations"] == ["HH", "HV"] and c["date"] == "2026-11-05"
    assert c["url"].endswith(".h5") and c["size_bytes"] == 1891631104
    assert c["footprint"]["type"] == "Polygon"


def test_grupos_nunca_misturam_colecao_nem_geometria(cenas):
    grupos = cat.agrupar(cenas, AOI)
    assert sum(g["n_dates"] for g in grupos) <= len(cenas)
    for g in grupos:
        assert len({(c["collection"], c["track"], c["direction"], c["frame"]) for c in g["scenes"]}) == 1
        assert len({c["maturity"] for c in g["scenes"]}) == 1
        assert g["dates"] == sorted(set(g["dates"]))
    # a trilha 10 D frame 98 existe nas duas coleções: têm de ser grupos separados
    t10 = [g for g in grupos if (g["track"], g["direction"], g["frame"]) == (10, "D", 98)]
    assert {g["maturity"] for g in t10} == {"PROVISIONAL", "VALIDATED"}


def test_escolhe_o_grupo_elegivel_com_mais_datas(cenas):
    grupos = cat.agrupar(cenas, AOI)
    g, motivo = cat.escolher(grupos)
    assert motivo is None and g["eligible"] and g["aoi_coverage"] >= 0.95
    assert g["n_dates"] == max(x["n_dates"] for x in grupos if x["eligible"])


def test_sem_cobertura_responde_indisponivel(cenas):
    longe = [10.0, 45.0, 10.2, 45.2]
    g, motivo = cat.escolher(cat.agrupar(cenas, longe))
    assert g is None and "cobre" in motivo
    assert cat.escolher([])[0] is None


def test_grupo_pedido_pelo_usuario(cenas):
    grupos = cat.agrupar(cenas, AOI)
    outro = grupos[1]
    g, motivo = cat.escolher(grupos, outro["id"])
    assert (g is outro) if outro["eligible"] else (g is None and motivo)
    assert cat.escolher(grupos, "nao|existe|X|0")[0] is None


def test_limitar_mantem_extremos(cenas):
    lista = sorted(cenas, key=lambda c: c["start_time"])
    menos = cat.limitar(lista, 5)
    assert len(menos) == 5 and menos[0] is lista[0] and menos[-1] is lista[-1]
