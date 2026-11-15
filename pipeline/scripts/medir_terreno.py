"""Mede o efeito de uma máscara de terreno (HAND/declividade) numa análise já gravada (item 2.3).

    python pipeline/scripts/medir_terreno.py data/analyses/<id> [--cache s2.npz]

Lê as máscaras de água (cog/water_*.tif) e refaz a referência Sentinel-2 de cada data na mesma grade;
lê HAND (GLO-30 HAND, ASF) e DEM (Copernicus GLO-30) públicos, sem credencial, e imprime precisão,
recall e IoU com e sem a máscara, para várias combinações de HAND máximo, declividade e dilatação.

Não faz parte do fluxo: no Lake Mead o corte que atinge precisão > 0,85 (HAND <= 2 m, sem dilatação)
também cortaria água real acima do nível do lago na época do DEM; ver docs/LIMITACOES.md.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
from scipy.ndimage import distance_transform_edt, uniform_filter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from arara_pipeline.terreno import DEM_URL, HAND_URL, ler_tiles_na_grade, nomes_de_tile  # noqa: E402

DECLIVIDADE_MAX_GRAUS = 15.0
HAND_MAX_M = 20.0
DILATACAO_HAND_M = 300.0
DECLIVIDADE_SUAVIZACAO_M = 90.0   # a declividade é tirada do DEM de 30 m, em janelas de ~3 px dele


def declividade_graus(dem, pixel_m, suavizacao_m=DECLIVIDADE_SUAVIZACAO_M):
    """Declividade (graus) do DEM já na grade; suaviza antes para não tirar ruído de 30 m reamostrado."""
    z = np.where(np.isfinite(dem), dem, np.nanmedian(dem) if np.isfinite(dem).any() else 0.0)
    k = max(1, int(round(suavizacao_m / pixel_m)))
    if k > 1:
        z = uniform_filter(z, k)
    gy, gx = np.gradient(z, pixel_m)
    s = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
    s[~np.isfinite(dem)] = np.nan
    return s


def plausivel(hand, declividade, pixel_m, hand_max=HAND_MAX_M, decl_max=DECLIVIDADE_MAX_GRAUS,
              dilatacao_m=DILATACAO_HAND_M):
    """Máscara de onde pode haver água. Sem dado de terreno no pixel, ele fica (não se corta no escuro)."""
    sem_dado = ~np.isfinite(hand) | ~np.isfinite(declividade)
    baixo = np.isfinite(hand) & (hand <= hand_max)
    if baixo.any() and dilatacao_m > 0:
        baixo = distance_transform_edt(~baixo) * pixel_m <= dilatacao_m
    plano = ~(np.isfinite(declividade) & (declividade > decl_max))
    return (baixo & plano) | sem_dado




def medir(pasta, cache=None, hands=(2, 3, 5, 10, 20, 1e9), declividades=(15, 90), dilatacoes=(0, 30, 150, 300)):
    import rasterio
    from pyproj import Transformer

    from arara_pipeline import crossval, optical_s2
    spec = json.load(open(os.path.join(pasta, "spec.json"), encoding="utf-8"))
    arqs = sorted(glob.glob(os.path.join(pasta, "cog", "water_*.tif")))
    with rasterio.open(arqs[0]) as s:
        t, epsg, (h, w) = s.transform, s.crs.to_epsg(), s.shape
    xs = t.c + t.a * (np.arange(w) + 0.5)
    ys = t.f + t.e * (np.arange(h) + 0.5)
    pixel = abs(t.a)
    agua, datas = [], []
    for a in arqs:
        with rasterio.open(a) as s:
            agua.append(s.read(1))
        d = os.path.basename(a)[6:14]
        datas.append(f"{d[:4]}-{d[4:6]}-{d[6:]}")
    valido = np.all([x != 255 for x in agua], axis=0)
    agua = [x == 1 for x in agua]
    if cache and os.path.exists(cache):
        z = np.load(cache)
        refs = [(z[f"w{i}"], z[f"v{i}"]) if f"w{i}" in z else None for i in range(len(datas))]
    else:
        refs, salvar = [], {}
        for i, d in enumerate(datas):
            r = optical_s2.referencia(spec["aoi"], d, xs, ys, epsg, valido)
            refs.append((r["water"], r["valid"]) if r["status"] == "ok" else None)
            if r["status"] == "ok":
                salvar[f"w{i}"], salvar[f"v{i}"] = r["water"], r["valid"]
        if cache:
            np.savez_compressed(cache, **salvar)
    tr = Transformer.from_crs(epsg, 4326, always_xy=True)
    lo0, la0 = tr.transform(xs.min(), ys.min())
    lo1, la1 = tr.transform(xs.max(), ys.max())
    nomes = nomes_de_tile(min(lo0, lo1), min(la0, la1), max(lo0, lo1), max(la0, la1))
    hand, _ = ler_tiles_na_grade([HAND_URL.format(lat=a, lon=b) for a, b in nomes], xs, ys, epsg)
    dem, _ = ler_tiles_na_grade([DEM_URL.format(lat=a, lon=b) for a, b in nomes], xs, ys, epsg)
    decl = declividade_graus(dem, pixel)

    def avaliar(m):
        vp = fp = fn = 0
        for a, r in zip(agua, refs):
            if r is None:
                continue
            x = crossval.metricas(a & m, r[0], r[1] & valido, 1.0)
            vp, fp, fn = vp + x["true_positive"], fp + x["false_positive"], fn + x["false_negative"]
        return vp / max(vp + fp, 1), vp / max(vp + fn, 1), vp / max(vp + fp + fn, 1)

    print(f"{len([r for r in refs if r])} datas com Sentinel-2; sem máscara: P=%.3f R=%.3f IoU=%.3f" % avaliar(np.ones_like(valido)))
    for hmax in hands:
        for dmax in declividades:
            for dil in dilatacoes:
                m = plausivel(hand, decl, pixel, hand_max=hmax, decl_max=dmax, dilatacao_m=dil)
                print("HAND<=%-5g decl<=%-3g dil=%-4g excluído=%.3f  P=%.3f R=%.3f IoU=%.3f"
                      % ((hmax, dmax, dil, 1 - m.mean()) + avaliar(m)), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pasta")
    ap.add_argument("--cache", help="arquivo .npz para guardar/reusar as máscaras do Sentinel-2")
    a = ap.parse_args()
    medir(a.pasta, a.cache)
