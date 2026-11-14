"""Regressão de Furnas. Os números de Furnas são TESTE, não parâmetros do fluxo global.

- test_validacao_ana_*: roda sempre (usa só regression/furnas e data/ana, dados reais versionados).
- os marcados com furnas_h5: só com os 9 .h5 locais (FURNAS_H5_DIR) e o polígono da ANA.
"""
import glob
import json
import os

import pytest

from arara_pipeline import furnas, sar
from arara_pipeline.geom import ler_poligono
from arara_pipeline.validate_ana import ler_areas, ler_cotas, ler_curva, metricas_ana, serie_ana

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
VENTO = {"20260907", "20261001"}
LIMIAR_OFICIAL_DB = -15.65


@pytest.fixture(scope="session")
def raiz():
    return RAIZ


@pytest.fixture(scope="session")
def furnas_h5():
    """Os .h5 de Furnas, em ordem de data. Sem FURNAS_H5_DIR, o teste é pulado (não simulado)."""
    pasta = os.environ.get("FURNAS_H5_DIR")
    if not pasta:
        pytest.skip("FURNAS_H5_DIR não definido: regressão com os .h5 de Furnas não roda nesta máquina")
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.h5")), key=lambda a: os.path.basename(a).split("_")[11])
    if len(arquivos) != 9:
        pytest.skip(f"esperava 9 .h5 em FURNAS_H5_DIR, achei {len(arquivos)}")
    return arquivos


@pytest.fixture(scope="session")
def furnas_poligono():
    """Polígono ANA: FURNAS_POLIGONO (.gdb/.geojson) ou data/ana/furnas_poligono.geojson."""
    caminho = os.environ.get("FURNAS_POLIGONO") or os.path.join(RAIZ, "data", "ana", "furnas_poligono.geojson")
    if not os.path.exists(caminho):
        pytest.skip("polígono da ANA ausente: defina FURNAS_POLIGONO ou gere data/ana/furnas_poligono.geojson "
                    "com pipeline/scripts/exportar_poligono.py")
    return caminho


@pytest.fixture(scope="module")
def referencia(raiz):
    ref = os.path.join(raiz, "regression", "furnas")
    ana = os.path.join(raiz, "data", "ana")
    with open(os.path.join(ref, "serie.json"), encoding="utf-8") as f:
        serie = json.load(f)
    with open(os.path.join(ref, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    return {"areas": ler_areas(os.path.join(ref, "area_agua.csv")), "serie": serie, "meta": meta,
            "cotas": ler_cotas(os.path.join(ana, "cota_furnas_ana.csv")),
            "curva": ler_curva(os.path.join(ana, "furnas_cota_area.csv"))}


def test_referencia_tem_as_9_areas(referencia):
    a = referencia["areas"]
    assert len(a) == 9
    assert a["20260627"] == pytest.approx(1039.8) and a["20261013"] == pytest.approx(1019.84)


def test_validacao_ana_reproduz_a_serie_publicada(referencia):
    serie = serie_ana(referencia["areas"], referencia["cotas"], referencia["curva"], VENTO)
    assert len(serie) == 9
    for nova, ref in zip(serie, referencia["serie"]):
        for chave, valor in nova.items():
            assert valor == ref[chave], (nova["data"], chave)


def test_validacao_ana_erro_de_1_por_cento_nas_datas_calmas(referencia):
    serie = serie_ana(referencia["areas"], referencia["cotas"], referencia["curva"], VENTO)
    m = metricas_ana(serie, referencia["curva"])
    assert m["n_datas_calmas"] == 7
    assert m["erro_abs_medio_pct"] == pytest.approx(1.0, abs=0.05)
    assert m["erro_abs_medio_km2"] == pytest.approx(10.4, abs=0.05)
    assert m["inclinacao_nisar_km2_por_m"] == pytest.approx(47.4, abs=0.05)
    assert m["inclinacao_ana_km2_por_m"] == pytest.approx(45.0, abs=0.05)
    assert m["queda_cota_m"] == pytest.approx(0.87)
    ref = referencia["meta"]["metricas"]
    for chave, valor in m.items():
        assert valor == ref[chave], chave


@pytest.fixture(scope="module")
def serie_oficial(furnas_h5, furnas_poligono, tmp_path_factory):
    aneis = ler_poligono(furnas_poligono, sar.epsg_do_h5(furnas_h5[0]))
    return furnas.processar(furnas_h5, str(tmp_path_factory.mktemp("furnas_b0")), poligono=aneis,
                            limiar=LIMIAR_OFICIAL_DB, buffer_m=0)


@pytest.mark.furnas_h5
def test_areas_oficiais_com_poligono_ana_sem_buffer(serie_oficial, referencia):
    assert len(serie_oficial) == 9
    for data, area, *_ in serie_oficial:
        assert area == pytest.approx(referencia["areas"][data], rel=0.005), data


@pytest.mark.furnas_h5
def test_limiar_adaptativo_fica_perto_de_menos_15_6(furnas_h5, furnas_poligono):
    """O limiar_bimodal, sem nenhum número de Furnas, tem de cair perto de -15,6 dB."""
    from arara_pipeline.geom import caixa_do_poligono
    aneis = ler_poligono(furnas_poligono, sar.epsg_do_h5(furnas_h5[0]))
    db, valido, _, _ = sar.ler_recorte(furnas_h5[0], caixa_do_poligono(aneis, 2000))
    assert sar.limiar_bimodal(db, valido) == pytest.approx(-15.6, abs=0.3)
