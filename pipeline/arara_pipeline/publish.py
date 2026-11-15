"""Publicação: reamostragem para Web Mercator/lat-lon, máscaras PNG, simplificação."""
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


# ---------- publicação genérica (etapa 3): COG, PNG lat/lon, tiles XYZ, JSON/CSV ----------

TILE = 256
R_MERC = 6378137.0
COR_AGUA = (46, 134, 222, 220)
CORES_FREQUENCIA = {1: (122, 220, 240, 190), 2: (59, 143, 217, 220), 3: (16, 60, 160, 240)}
CORES_MUDANCA = {1: (0, 0, 0, 0), 2: (122, 178, 235, 200), 3: (20, 70, 215, 235), 4: (217, 56, 40, 235)}


def salvar_cog(caminho, arr, xs, ys, epsg, nodata=None):
    """GeoTIFF otimizado para nuvem (COG) na grade original da cena."""
    import rasterio
    from rasterio.transform import from_origin
    dx, dy = float(xs[1] - xs[0]), float(ys[1] - ys[0])
    if dy > 0:                       # COG com o norte em cima
        arr, ys, dy = arr[::-1], ys[::-1], -dy
    perfil = dict(driver="COG", height=arr.shape[0], width=arr.shape[1], count=1, dtype=str(arr.dtype),
                  crs=f"EPSG:{epsg}", transform=from_origin(float(xs[0]) - dx / 2, float(ys[0]) - dy / 2, dx, -dy),
                  compress="DEFLATE", nodata=nodata)
    with rasterio.open(caminho, "w", **perfil) as dst:
        dst.write(arr, 1)


def rgba_mascara(mascara, cor=COR_AGUA):
    out = np.zeros(mascara.shape + (4,), np.uint8)
    out[mascara] = cor
    return out


def rgba_classes(classes, cores=CORES_MUDANCA):
    out = np.zeros(classes.shape + (4,), np.uint8)
    for c, cor in cores.items():
        out[classes == c] = cor
    return out


def rgba_db(db, faixa=(-25.0, -5.0)):
    out = np.zeros(db.shape + (4,), np.uint8)
    out[..., :3] = rampa(escala(db, faixa))
    out[..., 3] = np.where(np.isfinite(db), 255, 0)
    return out


def _indices(gx, gy, crs_origem, xs, ys, epsg):
    ux, uy = Transformer.from_crs(crs_origem, epsg, always_xy=True).transform(gx, gy)
    col = np.rint((ux - xs[0]) / (xs[1] - xs[0])).astype(np.int64)
    lin = np.rint((uy - ys[0]) / (ys[1] - ys[0])).astype(np.int64)
    fora = (col < 0) | (col >= len(xs)) | (lin < 0) | (lin >= len(ys))
    col[fora] = -1
    lin[fora] = -1
    return lin, col


def limites_lonlat(xs, ys, epsg):
    """(oeste, sul, leste, norte) da grade, pela borda."""
    bx = np.concatenate([xs, np.full_like(ys, xs[0]), xs, np.full_like(ys, xs[-1])])
    by = np.concatenate([np.full_like(xs, ys[0]), ys, np.full_like(xs, ys[-1]), ys])
    lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(bx, by)
    return float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())


def grade_latlon(xs, ys, epsg, largura_max=1024):
    """Índices para uma imagem regular em lon/lat (a que o globo usa) e seus limites."""
    oeste, sul, leste, norte = limites_lonlat(xs, ys, epsg)
    largura = int(min(largura_max, len(xs)))
    altura = max(1, int(round(largura * (norte - sul) / (leste - oeste))))
    lon = oeste + (np.arange(largura) + 0.5) * (leste - oeste) / largura
    lat = norte - (np.arange(altura) + 0.5) * (norte - sul) / altura
    gx, gy = np.meshgrid(lon, lat)
    return _indices(gx, gy, 4326, xs, ys, epsg), {"west": round(oeste, 6), "south": round(sul, 6),
                                                   "east": round(leste, 6), "north": round(norte, 6)}


def salvar_png(caminho, rgba, idx=None):
    img = rgba if idx is None else reamostrar(rgba, idx, 0).astype(np.uint8)
    Image.fromarray(img, "RGBA").save(caminho, optimize=True)


def _tile_de(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def zooms_para(pixel_m, lat, z_min=6, z_teto=12):
    """Do zoom de visão geral até o primeiro zoom com pixel de tile <= pixel do dado."""
    z = z_min
    while z < z_teto and 2 * np.pi * R_MERC * np.cos(np.radians(lat)) / (TILE * 2 ** z) > pixel_m:
        z += 1
    return list(range(z_min, z + 1))


def gerar_tiles(camadas, xs, ys, epsg, pasta, zooms=None):
    """Tiles XYZ (Web Mercator, 256 px) de várias camadas RGBA na mesma grade:
    pasta/{camada}/{z}/{x}/{y}.png. Tiles totalmente transparentes não são gravados."""
    import os
    oeste, sul, leste, norte = limites_lonlat(xs, ys, epsg)
    zooms = zooms or zooms_para(abs(float(xs[1] - xs[0])), (sul + norte) / 2)
    total = 0
    mundo = 2 * np.pi * R_MERC
    for z in zooms:
        x0, y0 = _tile_de(oeste, norte, z)
        x1, y1 = _tile_de(leste, sul, z)
        lado = mundo / 2 ** z
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                cx = -mundo / 2 + tx * lado + (np.arange(TILE) + 0.5) * lado / TILE
                cy = mundo / 2 - ty * lado - (np.arange(TILE) + 0.5) * lado / TILE
                idx = _indices(*np.meshgrid(cx, cy), 3857, xs, ys, epsg)
                if (idx[0] < 0).all():
                    continue
                for nome, rgba in camadas.items():
                    img = reamostrar(rgba, idx, 0).astype(np.uint8)
                    if not img[..., 3].any():
                        continue
                    d = os.path.join(pasta, nome, str(z), str(tx))
                    os.makedirs(d, exist_ok=True)
                    Image.fromarray(img, "RGBA").save(os.path.join(d, f"{ty}.png"), optimize=True)
                    total += 1
    return {"zooms": zooms, "count": total}
