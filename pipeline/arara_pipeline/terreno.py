"""Terreno público na grade da análise: HAND (GLO-30 HAND, ASF) e DEM (Copernicus GLO-30), sem credencial.

HAND = altura acima da drenagem mais próxima. No modo cheia ele separa a planície que pode alagar do
terreno alto, onde água escura no radar é quase sempre terra lisa ou sombra.
"""
import math

import numpy as np

DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM/"
           "Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM.tif")
HAND_URL = "https://glo-30-hand.s3.amazonaws.com/v1/2021/Copernicus_DSM_COG_10_{lat}_00_{lon}_00_HAND.tif"


def nomes_de_tile(oeste, sul, leste, norte):
    """Tiles de 1° (canto sudoeste) que cobrem a caixa lon/lat, no padrão N36/W115."""
    out = []
    for la in range(math.floor(sul), math.floor(norte - 1e-9) + 1):
        for lo in range(math.floor(oeste), math.floor(leste - 1e-9) + 1):
            out.append((f"{'N' if la >= 0 else 'S'}{abs(la):02d}", f"{'E' if lo >= 0 else 'W'}{abs(lo):03d}"))
    return out


def transformacao_da_grade(xs, ys):
    from rasterio.transform import from_origin
    dx, dy = float(xs[1] - xs[0]), float(ys[1] - ys[0])
    y_topo = float(max(ys[0], ys[-1]))
    return from_origin(float(xs[0]) - dx / 2, y_topo + abs(dy) / 2, dx, abs(dy)), dy > 0


def ler_tiles_na_grade(urls, xs, ys, epsg, metodo="bilinear"):
    """Mosaico dos COGs na grade (xs, ys = centros dos pixels); NaN onde nenhum tile cobre.
    Tile que não existe (mar aberto) é pulado."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.errors import RasterioIOError
    from rasterio.vrt import WarpedVRT
    transf, inverter = transformacao_da_grade(xs, ys)
    out = np.full((len(ys), len(xs)), np.nan, "float32")
    lidos = []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES",
                      GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2", GDAL_HTTP_TIMEOUT="60"):
        for url in urls:
            try:
                with rasterio.open(url) as src, WarpedVRT(src, crs=f"EPSG:{epsg}", transform=transf, width=len(xs),
                                                          height=len(ys), resampling=getattr(Resampling, metodo),
                                                          src_nodata=src.nodata, nodata=np.nan, dtype="float32") as vrt:
                    a = vrt.read(1)
            except RasterioIOError:
                continue
            a = a[::-1] if inverter else a
            novo = np.isfinite(a) & ~np.isfinite(out)
            out[novo] = a[novo]
            lidos.append(url)
    return out, lidos


def hand_na_grade(xs, ys, epsg):
    """HAND (m) na grade da análise, com cache por grade. Devolve (hand, urls lidas)."""
    from . import cache
    from .publish import limites_lonlat
    destino = cache.caminho("hand", cache.chave("hand", epsg, float(xs[0]), float(xs[-1]), len(xs),
                                                float(ys[0]), float(ys[-1]), len(ys)))
    lido = cache.ler_npz(destino)
    if lido is not None:
        return lido[1]["hand"], lido[0]["tiles"]
    oeste, sul, leste, norte = limites_lonlat(xs, ys, epsg)
    nomes = nomes_de_tile(oeste, sul, leste, norte)
    hand, lidos = ler_tiles_na_grade([HAND_URL.format(lat=a, lon=b) for a, b in nomes], xs, ys, epsg)
    if lidos:
        cache.salvar_npz(destino, {"tiles": lidos}, hand=hand)
    return hand, lidos
