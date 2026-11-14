import numpy as np
import pytest

from arara_pipeline import gcov_read, sar
from gcov_sintetico import PIXEL_M, X0, Y0, aoi_lonlat, disco, escrever, nome

N = 400


@pytest.fixture
def arquivo(tmp_path):
    return escrever(tmp_path / nome("20260627"), disco(N, 80))


def test_valida_estrutura_e_metadados(arquivo):
    with gcov_read.abrir(arquivo) as h:
        meta = gcov_read.validar_estrutura(h, exigir=("HHHH", "HVHV"))
    assert meta["epsg"] == 32723 and meta["pixel_x_m"] == PIXEL_M and meta["shape"] == [N, N]
    assert meta["units"] == {"HHHH": "linear", "HVHV": "linear"}
    assert meta["identification"]["compositeReleaseId"] == "P05023"


def test_le_so_a_janela_da_aoi_com_margem(arquivo):
    aoi = aoi_lonlat(N, margem_px=150)                      # 100 x 100 px no centro
    caixa = gcov_read.caixa_da_aoi(aoi, 32723, margem_m=1000)   # + 50 px de cada lado
    j = gcov_read.ler_cena(arquivo, caixa)
    ny, nx = j["bands"]["HHHH"].shape
    assert 198 <= ny <= 204 and 198 <= nx <= 204            # muito menor que a cena (400 x 400)
    assert j["window"]["row_start"] in range(97, 101) and j["window"]["col_start"] in range(97, 101)
    assert j["xs"][0] == X0 + PIXEL_M * j["window"]["col_start"]
    assert j["ys"][0] == Y0 - PIXEL_M * j["window"]["row_start"]
    assert j["pixel_area_m2"] == PIXEL_M ** 2 and j["valid_fraction"] == 1.0
    assert j["source"]["access"] == "local"


def test_leitura_por_objeto_de_arquivo_como_no_streaming(arquivo):
    # o streaming entrega ao h5py um objeto de arquivo do fsspec; aqui o mesmo caminho de código, local
    import fsspec
    import h5py
    with fsspec.open(arquivo, "rb", block_size=gcov_read.BLOCO_BYTES).open() as f, h5py.File(f, "r") as h:
        j = gcov_read.ler_janela(h, gcov_read.caixa_da_aoi(aoi_lonlat(N, 150), 32723))
    assert j["bands"]["HVHV"].shape == j["bands"]["HHHH"].shape


def test_mask_0_e_255_invalidos(tmp_path):
    mask = np.ones((N, N), "uint8")
    mask[:, :100] = 0
    mask[:, 300:] = 255
    mask[:, 150:160] = 254
    arq = escrever(tmp_path / nome("20260709"), disco(N, 80), mask=mask)
    j = gcov_read.ler_cena(arq, gcov_read.caixa_da_aoi(aoi_lonlat(N, 0), 32723, 0))
    v = j["valid"]["HHHH"]
    assert not v[:, :100].any() and not v[:, 300:].any() and v[:, 100:300].all()


def test_db_uma_unica_vez_mesmo_se_o_arquivo_vier_em_db(tmp_path):
    agua = disco(N, 80)
    lin = escrever(tmp_path / nome("20260627"), agua, semente=3)
    em_db = escrever(tmp_path / nome("20260709"), agua, semente=3, em_db=True)
    caixa = gcov_read.caixa_da_aoi(aoi_lonlat(N, 0), 32723, 0)
    a, b = gcov_read.ler_cena(lin, caixa), gcov_read.ler_cena(em_db, caixa)
    assert b["meta"]["units"]["HHHH"] == "dB"
    np.testing.assert_allclose(a["bands"]["HHHH"], b["bands"]["HHHH"], rtol=1e-4)
    db = sar.db_filtrado(a["bands"]["HHHH"], a["valid"]["HHHH"])
    assert -23 < np.nanmedian(db[agua]) < -21 and -9 < np.nanmedian(db[~agua]) < -7


def test_db_filtrado_igual_ao_metodo_validado_de_furnas(arquivo):
    db_ref, valido_ref, _, _ = sar.ler_recorte(arquivo, recorte=(0.0, 1.0, 0.0, 1.0), passo=1)
    j = gcov_read.ler_cena(arquivo, (X0, X0 + PIXEL_M * (N - 1), Y0, Y0 - PIXEL_M * (N - 1)))
    db = sar.db_filtrado(j["bands"]["HHHH"], j["valid"]["HHHH"])
    np.testing.assert_array_equal(valido_ref, j["valid"]["HHHH"])
    np.testing.assert_allclose(db, db_ref, rtol=1e-6)


def test_cena_sem_hh_ou_fora_da_area_sai_com_motivo(tmp_path, arquivo):
    import h5py
    with h5py.File(arquivo, "a") as h:
        del h[sar.GRADE]["HHHH"]
    with pytest.raises(gcov_read.CenaInvalida, match="HHHH"):
        gcov_read.ler_cena(arquivo, (X0, X0 + 1000, Y0, Y0 - 1000))
    ok = escrever(tmp_path / nome("20260721"), disco(N, 80))
    with pytest.raises(gcov_read.CenaInvalida, match="fora da grade"):
        gcov_read.ler_cena(ok, (0, 1000, 0, 1000))


def test_streaming_sem_credencial_diz_o_motivo(monkeypatch):
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    with pytest.raises(gcov_read.AcessoIndisponivel, match="EARTHDATA_USERNAME"):
        gcov_read.abrir("https://nisar.asf.earthdatacloud.nasa.gov/NISAR/x/y.h5")
