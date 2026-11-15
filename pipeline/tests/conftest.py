import os
import sys

import h5py
import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")
# o cache dos testes nunca toca o cache de verdade (~/.cache/arara ou data/cache)
import tempfile  # noqa: E402
os.environ["ARARA_CACHE_DIR"] = tempfile.mkdtemp(prefix="arara-cache-teste-")
RAIZ_PIPELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RAIZ_PIPELINE)
sys.path.insert(0, os.path.join(RAIZ_PIPELINE, "scripts"))

import area_agua  # noqa: E402

AGUA_DB = -22.0
TERRA_DB = -8.0
PIXEL_M = 20.0


def nome_nisar(data):
    return f"NISAR_L2_PR_GCOV_024_024_D_099_2005_DHDH_M_{data}T211458_{data}T211533_P05023_N_F_J_001.h5"


def escrever_gcov(caminho, agua, x0=400000.0, y0=7700000.0, mask=None, looks=4, semente=0):
    """Grava um .h5 mínimo com a estrutura do GCOV: HHHH com speckle gamma, mask e coordenadas."""
    rng = np.random.default_rng(semente)
    media = np.where(agua, 10 ** (AGUA_DB / 10), 10 ** (TERRA_DB / 10))
    hh = (media * rng.gamma(looks, 1 / looks, agua.shape)).astype("float32")
    ny, nx = agua.shape
    with h5py.File(caminho, "w") as h:
        g = h.create_group(area_agua.GRADE)
        g["HHHH"] = hh
        g["mask"] = np.ones(agua.shape, "uint8") if mask is None else mask
        g["xCoordinates"] = x0 + PIXEL_M * np.arange(nx)
        g["yCoordinates"] = y0 - PIXEL_M * np.arange(ny)  # norte para cima, como no GCOV
    return caminho


@pytest.fixture
def gcov(tmp_path):
    def fazer(data, agua, **kw):
        return escrever_gcov(str(tmp_path / nome_nisar(data)), agua, **kw)
    return fazer
