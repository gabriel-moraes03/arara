"""Leitura de JANELAS do GCOV: arquivo local ou URL por streaming (HTTPS com faixa de bytes).

Política "pega, processa e apaga": só a janela da AOI (+ margem) é lida, em blocos de ~8 MB; o .h5
inteiro nunca é baixado. O checksum do DAAC vale para o arquivo inteiro, então para janelas
valida-se a estrutura e os metadados e registra-se essa limitação.
"""
import os

import h5py
import numpy as np
from pyproj import Transformer

from .sar import GRADE, IDENTIFICACAO, valido_da_mask

BLOCO_BYTES = 8 * 2 ** 20
MARGEM_M = 1000.0
LIMITACAO_CHECKSUM = ("leitura por janela: o checksum do DAAC cobre o arquivo inteiro e não pôde ser "
                      "conferido; validados estrutura, grade, unidade e mask")


class AcessoIndisponivel(RuntimeError):
    """Falta de credencial, de rede ou de permissão. Nunca é mascarada com dado simulado."""


class CenaInvalida(ValueError):
    """A cena não serve para a análise (o motivo vai para o relatório; a análise continua)."""


def _sessao_earthdata():
    usuario, senha = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if not (usuario and senha):
        raise AcessoIndisponivel("credenciais Earthdata ausentes: defina EARTHDATA_USERNAME e "
                                 "EARTHDATA_PASSWORD no ambiente do backend")
    import earthaccess
    try:
        auth = earthaccess.login(strategy="environment")
    except Exception as e:  # noqa: BLE001
        raise AcessoIndisponivel(f"login Earthdata falhou: {type(e).__name__}") from e
    if not getattr(auth, "authenticated", False):
        raise AcessoIndisponivel("login Earthdata recusado: confira usuário e senha")
    return earthaccess.get_fsspec_https_session()


def abrir(fonte, fs=None):
    """h5py.File de um caminho local ou de uma URL http(s) (streaming com cache de blocos de 8 MB)."""
    if not str(fonte).lower().startswith(("http://", "https://")):
        if not os.path.exists(fonte):
            raise AcessoIndisponivel(f"arquivo local não encontrado: {os.path.basename(str(fonte))}")
        return h5py.File(fonte, "r")
    fs = fs or _sessao_earthdata()
    try:
        f = fs.open(fonte, mode="rb", block_size=BLOCO_BYTES, cache_type="blockcache")
        return h5py.File(f, "r")
    except AcessoIndisponivel:
        raise
    except Exception as e:  # noqa: BLE001
        raise AcessoIndisponivel(f"não foi possível abrir a cena por streaming: {type(e).__name__}: {e}") from e


def _texto(v):
    v = v[()] if isinstance(v, h5py.Dataset) else v
    if isinstance(v, np.ndarray):
        v = v.item() if v.ndim == 0 else v.tolist()
    return v.decode() if isinstance(v, bytes) else v


def epsg_da_grade(g):
    proj = g["projection"]
    return int(_texto(proj.attrs["epsg_code"]) if "epsg_code" in proj.attrs else _texto(proj))


def unidade(ds):
    """'linear' ou 'dB', pelo atributo de unidade do dataset (sem atributo: linear, como no GCOV)."""
    u = str(_texto(ds.attrs["units"])) if "units" in ds.attrs else ""
    return "dB" if "db" in u.lower() else "linear"


def validar_estrutura(h, exigir=("HHHH",)):
    """Confere frequência A, bandas, coordenadas, projeção e mask. Devolve os metadados da grade."""
    if GRADE not in h:
        raise CenaInvalida("sem grade na frequência A")
    g = h[GRADE]
    faltam = [n for n in (*exigir, "xCoordinates", "yCoordinates", "projection", "mask") if n not in g]
    if faltam:
        raise CenaInvalida("faltam na frequência A: " + ", ".join(faltam))
    x, y = g["xCoordinates"], g["yCoordinates"]
    if g[exigir[0]].shape != (y.shape[0], x.shape[0]):
        raise CenaInvalida("a grade não bate com as coordenadas")
    dx = float(x[1] - x[0])
    dy = float(y[1] - y[0])
    meta = {"epsg": epsg_da_grade(g), "pixel_x_m": abs(dx), "pixel_y_m": abs(dy),
            "shape": [int(y.shape[0]), int(x.shape[0])],
            "bands": [n for n in ("HHHH", "HVHV", "VVVV", "VHVH") if n in g],
            "units": {n: unidade(g[n]) for n in ("HHHH", "HVHV") if n in g}}
    if IDENTIFICACAO in h:
        i = h[IDENTIFICACAO]
        meta["identification"] = {k: _texto(i[k]) for k in (
            "granuleId", "zeroDopplerStartTime", "trackNumber", "frameNumber", "orbitPassDirection",
            "compositeReleaseId", "productVersion", "absoluteOrbitNumber", "processingCenter") if k in i}
    return meta


def caixa_da_aoi(aoi_lonlat, epsg, margem_m=MARGEM_M):
    """Caixa (x0, x1, y0, y1) em metros, no EPSG da grade, que contém a AOI + margem."""
    oeste, sul, leste, norte = aoi_lonlat.bounds
    t = Transformer.from_crs(4326, epsg, always_xy=True)
    n = 16
    lon = np.concatenate([np.linspace(oeste, leste, n), np.full(n, leste), np.linspace(leste, oeste, n), np.full(n, oeste)])
    lat = np.concatenate([np.full(n, sul), np.linspace(sul, norte, n), np.full(n, norte), np.linspace(norte, sul, n)])
    x, y = t.transform(lon, lat)
    return (float(x.min() - margem_m), float(x.max() + margem_m), float(y.min() - margem_m), float(y.max() + margem_m))


def ler_janela(h, caixa, passo=1, bandas=("HHHH", "HVHV")):
    """Lê só a janela da caixa (em metros). Devolve um dict com as bandas EM POTÊNCIA LINEAR
    (convertendo de volta se o arquivo já vier em dB), a validade (mask 1..254 e valor > 0),
    as coordenadas dos centros e a janela em linhas/colunas, para a proveniência."""
    meta = validar_estrutura(h)
    g = h[GRADE]
    x, y = g["xCoordinates"][:], g["yCoordinates"][:]
    x0, x1, y0, y1 = caixa
    cols = np.where((x >= min(x0, x1)) & (x <= max(x0, x1)))[0]
    rows = np.where((y >= min(y0, y1)) & (y <= max(y0, y1)))[0]
    if len(cols) < 2 or len(rows) < 2:
        raise CenaInvalida("a área fica fora da grade da cena")
    r = slice(int(rows[0]), int(rows[-1]) + 1, passo)
    c = slice(int(cols[0]), int(cols[-1]) + 1, passo)
    mask = g["mask"][r, c]
    na_passagem = valido_da_mask(mask)
    saida = {"xs": x[c], "ys": y[r], "epsg": meta["epsg"],
             "pixel_m": meta["pixel_x_m"] * passo, "pixel_area_m2": meta["pixel_x_m"] * meta["pixel_y_m"] * passo ** 2,
             "window": {"row_start": r.start, "row_stop": r.stop, "col_start": c.start, "col_stop": c.stop, "step": passo},
             "meta": meta, "mask": mask, "bands": {}, "valid": {}}
    for nome in bandas:
        if nome not in g:
            continue
        v = g[nome][r, c].astype("float32")
        if meta["units"].get(nome) == "dB":      # raro; volta para linear para haver UMA conversão só
            v = np.where(np.isfinite(v), 10 ** (v / 10), np.nan).astype("float32")
        saida["bands"][nome] = v
        saida["valid"][nome] = np.isfinite(v) & (v > 0) & na_passagem
    if "HHHH" not in saida["bands"]:
        raise CenaInvalida("sem HH na frequência A")
    saida["valid_fraction"] = float(saida["valid"]["HHHH"].mean())
    return saida


def ler_cena(fonte, caixa, passo=1, fs=None):
    """Abre (local ou streaming), lê a janela e fecha. Para URLs, registra a limitação do checksum."""
    with abrir(fonte, fs) as h:
        j = ler_janela(h, caixa, passo)
    remoto = str(fonte).lower().startswith("http")
    j["source"] = {"access": "streaming" if remoto else "local", "block_bytes": BLOCO_BYTES if remoto else None,
                   "checksum": LIMITACAO_CHECKSUM if remoto else "não conferido nesta leitura"}
    return j
