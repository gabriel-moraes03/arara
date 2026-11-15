"""Leitura e preparo do GCOV (HH/HV em dB) e limiar de água.

Regras: mask do GCOV 0 e 255 inválidos, 1..254 válidos; dB uma única vez, a partir de potência linear;
filtro 5x5 em dB; o mesmo limiar para todas as datas de uma análise.
"""
import os

import h5py
import numpy as np
from scipy.ndimage import gaussian_filter1d, uniform_filter
from scipy.signal import find_peaks

GRADE = "/science/LSAR/GCOV/grids/frequencyA"
IDENTIFICACAO = "/science/LSAR/identification"
PASSO = 2  # 1 = resolução cheia; 2 = metade (Furnas: 40 m)

# Recorte histórico de Furnas em fração da imagem (trilha 024 D 099). Só é usado quando não há
# polígono nem caixa; o fluxo global sempre passa a caixa da AOI.
RECORTE = (0.42, 0.83, 0.28, 0.72)

# Limiar: só nos blocos de margem (com água E terra). No recorte inteiro a água é ~3% dos pixels e
# o Otsu "puro" corta dentro da terra (deu -12 dB no real).
BLOCO = 50
SEMENTE_DB = -20.0
FRACAO_SEMENTE = (0.2, 0.8)
MIN_BLOCOS_MARGEM = 5


def data_do_nome(caminho):
    # NISAR_L2_PR_GCOV_024_024_D_099_2005_DHDH_M_20260627T211458_... -> 20260627
    return os.path.basename(caminho).split("_")[11][:8]


def otsu(valores, bins=256):
    """Acha o melhor corte entre os dois 'morros' do histograma (água x terra)."""
    hist, bordas = np.histogram(valores, bins=bins)
    centros = (bordas[:-1] + bordas[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centros) / np.maximum(w0, 1)
    m1 = (np.sum(hist * centros) - np.cumsum(hist * centros)) / np.maximum(w1, 1)
    entre = w0 * w1 * (m0 - m1) ** 2
    return centros[np.argmax(entre)]


def vale(valores, bins=120, suavizar=3):
    """Mínimo do histograma (suavizado) entre os dois picos mais proeminentes (água e terra).
    Se não houver dois picos, usa o Otsu."""
    hist, bordas = np.histogram(valores, bins=bins)
    centros = (bordas[:-1] + bordas[1:]) / 2
    hist = gaussian_filter1d(hist.astype(float), suavizar)
    picos, props = find_peaks(np.concatenate([[0], hist, [0]]), prominence=0)
    if len(picos) < 2:
        return otsu(valores)
    i_agua, i_terra = np.sort(picos[np.argsort(props["prominences"])[-2:]] - 1)
    return centros[i_agua + np.argmin(hist[i_agua:i_terra + 1])]


def blocos_de_margem(db, valido, bloco=BLOCO, semente=SEMENTE_DB, fracao=FRACAO_SEMENTE):
    """Valores (n_blocos, bloco²) dos blocos totalmente válidos com 20-80% de pixels < semente."""
    ny, nx = (db.shape[0] // bloco) * bloco, (db.shape[1] // bloco) * bloco
    if ny == 0 or nx == 0:
        return np.empty((0, bloco * bloco), db.dtype)
    forma = (ny // bloco, bloco, nx // bloco, bloco)
    blocos = db[:ny, :nx].reshape(forma).swapaxes(1, 2).reshape(-1, bloco * bloco)
    cheios = valido[:ny, :nx].reshape(forma).swapaxes(1, 2).reshape(-1, bloco * bloco).all(1)
    escuro = (blocos < semente).mean(1)
    return blocos[cheios & (escuro > fracao[0]) & (escuro < fracao[1])]


def limiar_bimodal(db, valido, bloco=BLOCO, semente=SEMENTE_DB, fracao=FRACAO_SEMENTE):
    """Vale água/terra nos blocos de margem (20-80% de pixels < semente), não na imagem toda."""
    margem = blocos_de_margem(db, valido, bloco, semente, fracao)
    if len(margem) < MIN_BLOCOS_MARGEM:  # sem blocos de margem suficientes: cai no Otsu da imagem toda
        return otsu(db[valido])
    return vale(margem.ravel())


def valido_da_mask(mask):
    """mask do GCOV: 1..254 = número da subfaixa (válido), 0 = amostra inválida, 255 = fora da passagem."""
    return (mask >= 1) & (mask < 255)


def caixa_do_recorte(x, y, recorte=RECORTE):
    """Converte o recorte em frações da imagem numa caixa em METROS (x0, x1, y0, y1)."""
    xa, xb, ya, yb = recorte
    return (
        x[int(xa * len(x))], x[int(xb * len(x)) - 1],
        y[int(ya * len(y))], y[int(yb * len(y)) - 1],
    )


def ler_recorte(caminho, caixa=None, recorte=RECORTE, passo=PASSO):
    with h5py.File(caminho, "r") as h:
        g = h[GRADE]
        x = g["xCoordinates"][:]
        y = g["yCoordinates"][:]
        if caixa is None:  # primeira imagem: define a caixa do lago em METROS
            caixa = caixa_do_recorte(x, y, recorte)
        x0, x1, y0, y1 = caixa
        cols = np.where((x >= min(x0, x1)) & (x <= max(x0, x1)))[0]
        rows = np.where((y >= min(y0, y1)) & (y <= max(y0, y1)))[0]
        r = slice(rows[0], rows[-1] + 1, passo)
        c = slice(cols[0], cols[-1] + 1, passo)
        hh = g["HHHH"][r, c].astype("float32")
        pixel_m = abs(x[1] - x[0]) * passo
        valido = np.isfinite(hh) & (hh > 0)
        if "mask" in g:
            valido &= valido_da_mask(g["mask"][r, c])
    db = 10 * np.log10(np.where(valido, hh, 1e-10))
    # tira o granulado: média 5x5 feita em dB, para não "comer" as margens finas do lago
    db = uniform_filter(np.where(valido, db, np.nanmedian(db[valido])), size=5)
    db[~valido] = np.nan
    return db, valido, pixel_m, caixa


def coordenadas_recorte(caminho, caixa, passo=PASSO):
    """Coordenadas (m) dos centros de coluna e linha do recorte, na mesma grade de ler_recorte."""
    with h5py.File(caminho, "r") as h:
        x = h[GRADE]["xCoordinates"][:]
        y = h[GRADE]["yCoordinates"][:]
    x0, x1, y0, y1 = caixa
    cols = np.where((x >= min(x0, x1)) & (x <= max(x0, x1)))[0]
    rows = np.where((y >= min(y0, y1)) & (y <= max(y0, y1)))[0]
    return x[cols[0]:cols[-1] + 1:passo], y[rows[0]:rows[-1] + 1:passo]


def epsg_do_h5(caminho):
    with h5py.File(caminho, "r") as h:
        proj = h[GRADE]["projection"]
        return int(proj.attrs.get("epsg_code", proj[()]))


def ler_banda(caminho, caixa, banda, passo=PASSO):
    """Mesmo recorte e filtro de area_agua.ler_recorte, para qualquer banda (ex.: HVHV)."""
    with h5py.File(caminho, "r") as h:
        g = h[GRADE]
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        x0, x1, y0, y1 = caixa
        cols = np.where((x >= min(x0, x1)) & (x <= max(x0, x1)))[0]
        rows = np.where((y >= min(y0, y1)) & (y <= max(y0, y1)))[0]
        r = slice(rows[0], rows[-1] + 1, passo)
        c = slice(cols[0], cols[-1] + 1, passo)
        v = g[banda][r, c].astype("float32")
        valido = np.isfinite(v) & (v > 0) & valido_da_mask(g["mask"][r, c])
    db = 10 * np.log10(np.where(valido, v, 1e-10))
    db = uniform_filter(np.where(valido, db, np.nanmedian(db[valido])), size=5)
    db[~valido] = np.nan
    return db


def identificacao(caminho):
    with h5py.File(caminho, "r") as h:
        i = h["/science/LSAR/identification"]
        ler = lambda k: i[k][()].decode() if isinstance(i[k][()], bytes) else i[k][()].item()
        return {k: ler(k) for k in ("granuleId", "zeroDopplerStartTime", "trackNumber", "frameNumber",
                                    "orbitPassDirection", "compositeReleaseId", "productVersion",
                                    "absoluteOrbitNumber", "processingCenter")}


def db_filtrado(linear, valido, filtro="db", tamanho=5):
    """Potência linear -> dB (uma única vez) com média 5x5. filtro="db" (padrão, método validado em
    Furnas: não "come" margens finas), "linear" (média da potência, depois dB) ou None.
    Pixels inválidos saem como NaN e não contaminam os vizinhos (entram com a mediana dos válidos)."""
    if not valido.any():
        return np.full(linear.shape, np.nan, "float32")
    if filtro == "linear":
        media = uniform_filter(np.where(valido, linear, np.nanmedian(linear[valido])).astype("float64"), size=tamanho)
        db = 10 * np.log10(np.maximum(media, 1e-10))
    else:
        db = 10 * np.log10(np.where(valido, linear, 1e-10))
        if filtro == "db":
            db = uniform_filter(np.where(valido, db, np.nanmedian(db[valido])), size=tamanho)
    db = db.astype("float32")
    db[~valido] = np.nan
    return db
