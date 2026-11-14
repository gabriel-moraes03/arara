"""Publicação: reamostragem para Web Mercator/lat-lon, máscaras PNG, simplificação.
Migrado de terrapulse/scripts/exportar_web.py; COG, tiles e JSON entram na etapa 3."""
import numpy as np
from PIL import Image
from pyproj import Transformer

TOM_ESCURO = np.array([9, 15, 19], float)
TOM_CLARO = np.array([232, 226, 212], float)


def grade_mercator(xs, ys, epsg, largura):
    """Grade regular em Web Mercator que cobre o recorte; devolve índices (linha, coluna) no recorte
    para cada pixel de saída (-1 fora) e os limites em lat/lon."""
    para_merc = Transformer.from_crs(epsg, 3857, always_xy=True)
    de_merc = Transformer.from_crs(3857, epsg, always_xy=True)
    para_ll = Transformer.from_crs(3857, 4326, always_xy=True)
    bx = np.concatenate([xs, np.full_like(ys, xs[0]), xs, np.full_like(ys, xs[-1])])
    by = np.concatenate([np.full_like(xs, ys[0]), ys, np.full_like(xs, ys[-1]), ys])
    mx, my = para_merc.transform(bx, by)
    mx0, mx1, my0, my1 = mx.min(), mx.max(), my.min(), my.max()
    altura = int(round(largura * (my1 - my0) / (mx1 - mx0)))
    px = (mx1 - mx0) / largura
    cx = mx0 + (np.arange(largura) + 0.5) * px
    cy = my1 - (np.arange(altura) + 0.5) * (my1 - my0) / altura
    gx, gy = np.meshgrid(cx, cy)
    ux, uy = de_merc.transform(gx, gy)
    col = np.rint((ux - xs[0]) / (xs[1] - xs[0])).astype(np.int64)
    lin = np.rint((uy - ys[0]) / (ys[1] - ys[0])).astype(np.int64)
    fora = (col < 0) | (col >= len(xs)) | (lin < 0) | (lin >= len(ys))
    col[fora] = -1
    lin[fora] = -1
    lon0, lat0 = para_ll.transform(mx0, my0)
    lon1, lat1 = para_ll.transform(mx1, my1)
    return (lin, col), [[round(lat0, 6), round(lon0, 6)], [round(lat1, 6), round(lon1, 6)]], (largura, altura)


def reamostrar(arr, idx, vazio):
    lin, col = idx
    out = arr[lin.clip(0), col.clip(0)]
    out = np.where(lin >= 0, out, vazio) if out.ndim == 2 else np.where((lin >= 0)[..., None], out, vazio)
    return out


def escala(db, faixa):
    a, b = faixa
    return np.clip((db - a) / (b - a), 0, 1)


def rampa(t):
    """0..1 -> do tom do fundo ao off-white (RGB uint8); NaN -> fundo."""
    t = np.nan_to_num(t, nan=0.0)[..., None]
    return (TOM_ESCURO + (TOM_CLARO - TOM_ESCURO) * t ** 1.2).astype(np.uint8)


def salvar_mascara(caminho, mascara, cor, alfa=235):
    rgba = np.zeros(mascara.shape + (4,), np.uint8)
    rgba[mascara] = (*cor, alfa)
    Image.fromarray(rgba, "RGBA").quantize(colors=4, method=Image.Quantize.FASTOCTREE).save(caminho, optimize=True)


def simplificar(pontos, tol):
    """Douglas-Peucker iterativo."""
    manter = np.zeros(len(pontos), bool)
    manter[[0, -1]] = True
    pilha = [(0, len(pontos) - 1)]
    while pilha:
        i, j = pilha.pop()
        if j <= i + 1:
            continue
        a, b = pontos[i], pontos[j]
        seg = b - a
        n = np.hypot(*seg)
        p = pontos[i + 1:j] - a
        d = np.abs(seg[0] * p[:, 1] - seg[1] * p[:, 0]) / n if n > 0 else np.hypot(p[:, 0], p[:, 1])
        k = int(np.argmax(d))
        if d[k] > tol:
            manter[i + 1 + k] = True
            pilha += [(i, i + 1 + k), (i + 1 + k, j)]
    return pontos[manter]


def area_anel_km2(a):
    x, y = a[:, 0], a[:, 1]
    return abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2 / 1e6
