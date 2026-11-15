"""GCOV sintético completo (HH, HV, mask, coordenadas, projeção, identificação) para os testes novos."""
import h5py
import numpy as np

from arara_pipeline.sar import GRADE, IDENTIFICACAO

AGUA_DB, TERRA_DB, PIXEL_M = -22.0, -8.0, 20.0
X0, Y0, EPSG = 400000.0, 7700000.0, 32723


def nome(data, trilha=24, frame=99, direcao="D", pol="DHDH"):
    return (f"NISAR_L2_PR_GCOV_024_{trilha:03d}_{direcao}_{frame:03d}_2005_{pol}_A_{data}T211458_"
            f"{data}T211533_P05023_N_F_J_001.h5")


def escrever(caminho, agua, agua_db=AGUA_DB, mask=None, hv=True, semente=0, looks=4, x0=X0, y0=Y0, em_db=False):
    rng = np.random.default_rng(semente)
    media = np.where(agua, 10 ** (agua_db / 10), 10 ** (TERRA_DB / 10))
    hh = (media * rng.gamma(looks, 1 / looks, agua.shape)).astype("float32")
    ny, nx = agua.shape
    with h5py.File(caminho, "w") as h:
        g = h.create_group(GRADE)
        g["HHHH"] = 10 * np.log10(hh) if em_db else hh
        g["HHHH"].attrs["units"] = np.bytes_("dB" if em_db else "1")
        if hv:
            g["HVHV"] = (hh * 0.2).astype("float32")
            g["HVHV"].attrs["units"] = np.bytes_("1")
        g["mask"] = np.ones(agua.shape, "uint8") if mask is None else mask
        g["xCoordinates"] = x0 + PIXEL_M * np.arange(nx)
        g["yCoordinates"] = y0 - PIXEL_M * np.arange(ny)
        g["projection"] = np.uint32(EPSG)
        g["projection"].attrs["epsg_code"] = EPSG
        i = h.create_group(IDENTIFICACAO)
        i["granuleId"] = np.bytes_(str(caminho).split("/")[-1][:-3])
        i["compositeReleaseId"] = np.bytes_("P05023")
        i["trackNumber"] = np.uint32(24)
        i["frameNumber"] = np.uint32(99)
        i["orbitPassDirection"] = np.bytes_("Descending")
    return str(caminho)


def disco(n, raio, centro=None):
    cy, cx = centro or (n / 2, n / 2)
    yy, xx = np.mgrid[:n, :n]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= raio ** 2


def aoi_lonlat(n, margem_px=20):
    """Polígono lon/lat (shapely) que cobre a grade sintética menos uma margem."""
    from pyproj import Transformer
    from shapely.geometry import Polygon
    t = Transformer.from_crs(EPSG, 4326, always_xy=True)
    xa, xb = X0 + margem_px * PIXEL_M, X0 + (n - margem_px) * PIXEL_M
    ya, yb = Y0 - margem_px * PIXEL_M, Y0 - (n - margem_px) * PIXEL_M
    return Polygon([t.transform(x, y) for x, y in ((xa, ya), (xb, ya), (xb, yb), (xa, yb))])
