"""Modo cheia, chuva IMERG, municípios e leitura simples, sem rede."""
import numpy as np
import pytest
from shapely.geometry import box

from arara_pipeline import cheia, chuva, leitura, municipios

PIXEL = 20.0


def cena(n=200, rio=20, alagado=None, hh_terra=-8.0, hh_agua=-22.0):
    db = np.full((n, n), hh_terra)
    db[:, n // 2 - rio // 2:n // 2 + rio // 2] = hh_agua
    if alagado is not None:
        db[alagado] = hh_agua
    return db


def test_cheia_e_agua_alem_da_passagem_mais_seca():
    n = 200
    plan = np.zeros((n, n), bool)
    plan[50:150, 120:180] = True                      # várzea que alaga na 2a data (60x100 px = 2,4 km²)
    dbs = [cena(), cena(alagado=plan), cena()]
    comum = np.ones((n, n), bool)
    brutas = [d < -15 for d in dbs]
    classes, r = cheia.mapear(brutas, dbs, comum, [False] * 3, PIXEL)
    assert r in (0, 2)
    km2 = lambda m: m.sum() * PIXEL ** 2 / 1e6
    assert km2(classes[1] == cheia.CHEIA) == pytest.approx(2.4, rel=0.02)
    assert km2(classes[0] == cheia.CHEIA) == 0 and km2(classes[1] == cheia.REF) > 0


def test_referencia_ignora_data_de_vento():
    # a data 0 parece seca por causa do vento; a referência tem de ser a passagem calma com menos água
    assert cheia.referencia_seca([10, 50, 40], [True, False, False]) == 2
    assert cheia.referencia_seca([10, 50], [True, True]) == 0


def test_hand_alto_corta_falso_positivo():
    n = 200
    alto = np.zeros((n, n), bool)
    alto[0:60, 0:60] = True                           # terra lisa escura em morro (HAND 40 m)
    dbs = [cena(), cena(alagado=alto), cena()]
    hand = np.where(alto, 40.0, 2.0)
    classes, _ = cheia.mapear([d < -15 for d in dbs], dbs, np.ones((n, n), bool), [False] * 3, PIXEL, hand)
    assert not (classes[1] == cheia.CHEIA).any()


def test_vegetacao_alagada_e_clareamento_forte_em_terreno_baixo():
    n = 200
    mata = np.zeros((n, n), bool)
    mata[20:80, 130:190] = True
    dbs = [cena() for _ in range(5)]
    dbs[3] = dbs[3].copy()
    dbs[3][mata] += 5.0                                # dupla reflexão: +5 dB
    classes, _ = cheia.mapear([d < -15 for d in dbs], dbs, np.ones((n, n), bool), [False] * 5, PIXEL, np.full((n, n), 3.0))
    assert (classes[3] == cheia.VEGETACAO).sum() == mata.sum()
    assert not (classes[2] == cheia.VEGETACAO).any()


def test_indices_e_ascii_do_imerg():
    (i0, i1), (j0, j1) = chuva.indices(-51.35, -30.15, -51.05, -29.85)
    assert (i0, i1) == (1286, 1289) and (j0, j1) == (598, 601)
    assert chuva.indices(-51.2, -30.0, -51.2, -30.0)[0][0] == chuva.indices(-51.2, -30.0, -51.2, -30.0)[0][1]
    txt = "Dataset: x\nprecipitation.precipitation[1][2][2]\n[0][0], 1.5, 2.5\n[0][1], -9999.9, 4.0\n"
    v = chuva.ler_ascii(txt)
    assert np.nanmean(v) == pytest.approx(8 / 3)
    u = chuva.url_opendap(chuva.DADOS + "GPM_L3/GPM_3IMERGDL.07/2026/10/3B-DAY-L.MS.MRG.3IMERG.20261001-S000000-E235959.V07C.nc4", (1, 2), (3, 4))
    assert u.startswith(chuva.OPENDAP) and u.endswith(".nc4.ascii?precipitation[0:0][1:2][3:4]")


def test_serie_diaria_e_acumulados():
    urls = {f"2026-10-{d:02d}": chuva.DADOS + f"X/3B-DAY-L.MS.MRG.3IMERG.202610{d:02d}-S0.nc4" for d in range(1, 11)}
    diaria = chuva.serie_diaria((-51.3, -30.1, -51.1, -29.9), "2026-10-01", "2026-10-10",
                                buscar=lambda a, b: urls, baixar=lambda u: "[0][0], 10.0, 20.0\n")
    assert diaria["2026-10-05"] == 15.0
    assert chuva.acumulado(diaria, "2026-10-10", 7) == 105.0
    assert chuva.acumulado(diaria, "2026-10-03", 7) is None          # faltam dias: nada inventado
    r = chuva.resumir(diaria, ["2026-10-10"])
    assert r["per_date"][0]["rain_3d_mm"] == 45.0 and r["total_mm"] == 150.0


def test_chuva_sem_autorizacao_fica_indisponivel():
    def nega(*a):
        raise chuva.ChuvaIndisponivel(chuva.SEM_AUTORIZACAO)
    ctx = {"spec": {}, "aoi": box(-51.3, -30.1, -51.1, -29.9), "datas": [{"date": "2026-10-10"}]}
    extras = {}
    chuva.rodar(ctx, extras, lambda *a: None, serie=nega)
    assert extras["chuva"]["status"] == "unavailable" and "GESDISC" in extras["chuva"]["reason"]


def test_municipios_contam_cheia_e_populacao(monkeypatch):
    from pyproj import Transformer
    epsg = 32722
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    x0, y0 = tr.transform(-51.2, -30.0)
    xs = x0 + np.arange(100) * PIXEL
    ys = y0 - np.arange(100) * PIXEL
    inv = Transformer.from_crs(epsg, 4326, always_xy=True)
    w, n = inv.transform(xs[0], ys[0])
    e, s = inv.transform(xs[49] + 10, ys[-1])
    geo = box(w - 0.01, s - 0.01, e, n + 0.01).__geo_interface__
    classes = np.zeros((100, 100), "uint8")
    classes[:, :25] = cheia.CHEIA
    classes[:, 75:] = cheia.CHEIA
    linhas = municipios.contar(classes, [("4300001", "Oeste", "RS", geo)], xs, ys, epsg, PIXEL ** 2, cheia.CHEIA, cheia.VEGETACAO)
    assert linhas[0]["flood_km2"] == pytest.approx(100 * 25 * 400 / 1e6, rel=0.05)
    pop = municipios.populacao(["4314902"], obter=lambda u, *a: [{"resultados": [{"series": [
        {"localidade": {"id": "4314902"}, "serie": {"2022": "1332845"}}]}]}])
    assert pop == {"4314902": 1332845}


def test_confianca_e_resumo():
    datas = [{"date": "2026-09-01", "suspeita_vento": True, "valid_fraction_aoi": 1.0},
             {"date": "2026-09-13", "suspeita_vento": False, "valid_fraction_aoi": 0.96},
             {"date": "2026-09-25", "suspeita_vento": False, "valid_fraction_aoi": 1.0}]
    fl = {"status": "ok", "terrain": {"product": "x"}, "reference_date": "2026-09-01", "peak_date": "2026-09-25",
          "per_date": [{"date": d["date"], "flood_km2": f, "flooded_vegetation_km2": 0.0} for d, f in zip(datas, (0, 1, 12.34))]}
    leitura.confianca(datas, "reliable", None, fl)
    assert [d["confidence"]["level"] for d in datas] == ["baixa", "média", "alta"]
    ch = {"status": "ok", "per_date": [{"date": "2026-09-25", "rain_7d_mm": 87.4}]}
    mu = {"municipalities": [{"name": "Eldorado do Sul", "uf": "RS", "flood_km2": 9.0, "flooded_vegetation_km2": 0},
                             {"name": "Guaíba", "uf": "RS", "flood_km2": 3.0, "flooded_vegetation_km2": 0}]}
    t = leitura.resumo(datas, 500.0, fl, ch, mu)["text"]
    assert "25/09/2026" in t and "12,3 km²" in t and "Eldorado do Sul (RS) e Guaíba (RS)" in t
    assert "87 mm" in t and "Uma data com vento (01/09)" in t


def test_terra_seca_antes_da_cheia_nao_vira_vegetacao_alagada():
    """Pixel que é terra (-8 dB) nas 2 primeiras passagens e água (-22 dB) nas 3 últimas: a mediana da série
    (-22) deixaria a terra de antes 14 dB "acima do normal". A base é só das passagens como terra."""
    n = 200
    campo = np.zeros((n, n), bool)
    campo[20:120, 130:190] = True
    dbs = [cena(), cena(), cena(alagado=campo), cena(alagado=campo), cena(alagado=campo)]
    classes, _ = cheia.mapear([d < -15 for d in dbs], dbs, np.ones((n, n), bool), [False] * 5, PIXEL, np.full((n, n), 3.0))
    assert not any((c == cheia.VEGETACAO).any() for c in classes)
    assert (classes[3] == cheia.CHEIA).sum() > 0.9 * campo.sum()
