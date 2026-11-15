"""Cache por passagem e leitura em paralelo (processos leitores), com cenas sintéticas no disco."""
import os

import numpy as np
import pytest

from arara_pipeline import cache, passagens
from gcov_sintetico import aoi_lonlat, disco, escrever, nome

N = 300


@pytest.fixture()
def cenas(tmp_path, monkeypatch):
    monkeypatch.setenv("ARARA_CACHE_DIR", str(tmp_path / "cache"))
    out = []
    for i, d in enumerate(["20260627", "20260709", "20260721"]):
        arq = escrever(tmp_path / nome(d), disco(N, 90 - 5 * i), semente=i)
        # "remota" para o cache (local=False), mas a URL é um caminho do disco: abre sem credencial
        out.append({"granule": nome(d)[:-3], "crid": "P05023", "date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "url": str(arq)})
    return out


def test_segunda_leitura_vem_toda_do_cache(cenas):
    aoi = aoi_lonlat(N, 30)
    msgs = []
    prog = lambda e, f, m: msgs.append(m)  # noqa: E731
    a = passagens.ler(cenas, aoi, 1, "db", prog, leitores=2)        # 3 faltando, 2 processos leitores
    assert all(j["source"]["cache"] == "miss" for j in a)
    b = passagens.ler(cenas, aoi, 1, "db", prog, leitores=2)
    assert all(j["source"]["cache"] == "hit" for j in b)
    assert any("3 de 3 passagens já estavam no cache" in m for m in msgs)
    for x, y in zip(a, b):
        np.testing.assert_array_equal(x["db"]["HHHH"], y["db"]["HHHH"])
        np.testing.assert_array_equal(x["valid"]["HHHH"], y["valid"]["HHHH"])
        assert x["window"] == y["window"] and x["epsg"] == y["epsg"]


def test_crid_novo_ou_area_nova_nao_reaproveita(cenas):
    aoi = aoi_lonlat(N, 30)
    passagens.ler(cenas[:1], aoi, 1, "db", lambda *a: None, leitores=1)
    reproc = [dict(cenas[0], crid="P05024")]                         # a NASA reprocessou a cena
    assert passagens.ler(reproc, aoi, 1, "db", lambda *a: None)[0]["source"]["cache"] == "miss"
    assert passagens.ler(cenas[:1], aoi_lonlat(N, 40), 1, "db", lambda *a: None)[0]["source"]["cache"] == "miss"


def test_cena_local_nao_entra_no_cache(cenas):
    locais = [dict(c, local=True) for c in cenas[:1]]
    j = passagens.ler(locais, aoi_lonlat(N, 30), 1, "db", lambda *a: None)[0]
    assert j["source"]["cache"] == "local" and not os.listdir(cache.pasta("sar"))


def test_entrada_quebrada_e_relida_e_limite_apaga_as_mais_antigas(cenas, tmp_path):
    aoi = aoi_lonlat(N, 30)
    passagens.ler(cenas[:1], aoi, 1, "db", lambda *a: None)
    [arq] = os.listdir(cache.pasta("sar"))
    with open(os.path.join(cache.pasta("sar"), arq), "wb") as f:
        f.write(b"lixo")
    assert passagens.ler(cenas[:1], aoi, 1, "db", lambda *a: None)[0]["source"]["cache"] == "miss"
    antes, depois = cache.limitar(0)
    assert antes > 0 and depois == 0 and not os.listdir(cache.pasta("sar"))
