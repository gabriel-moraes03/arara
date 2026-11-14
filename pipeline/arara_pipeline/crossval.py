"""Validação cruzada radar x óptico. O óptico é a referência (não a verdade de campo)."""
import numpy as np
from scipy.ndimage import binary_erosion, distance_transform_edt


def metricas(sar, optico, valido, pixel_area_m2, pixel_m=None):
    """IoU, precisão, recall, F1, acurácia e áreas, só nos pixels válidos nos dois sensores."""
    vp = int((sar & optico & valido).sum())
    fp = int((sar & ~optico & valido).sum())
    fn = int((~sar & optico & valido).sum())
    vn = int((~sar & ~optico & valido).sum())
    n = vp + fp + fn + vn

    def razao(a, b):
        return round(a / b, 4) if b else None

    m = {"n_pixels": n, "compared_km2": round(n * pixel_area_m2 / 1e6, 3),
         "true_positive": vp, "false_positive": fp, "false_negative": fn, "true_negative": vn,
         "iou": razao(vp, vp + fp + fn), "precision": razao(vp, vp + fp), "recall": razao(vp, vp + fn),
         "f1": razao(2 * vp, 2 * vp + fp + fn), "accuracy": razao(vp + vn, n),
         "sar_water_km2": round((vp + fp) * pixel_area_m2 / 1e6, 3),
         "optical_water_km2": round((vp + fn) * pixel_area_m2 / 1e6, 3),
         "sar_only_ha": round(fp * pixel_area_m2 / 1e4, 2), "optical_only_ha": round(fn * pixel_area_m2 / 1e4, 2)}
    if pixel_m and (fp + fn) and optico.any() and not optico.all():
        # distância de cada discordância até a margem da água óptica: perto = borda/pixel misto
        margem = optico & ~binary_erosion(optico)
        dist = distance_transform_edt(~margem) * pixel_m
        d = dist[(sar ^ optico) & valido]
        m["disagreement_median_m"] = round(float(np.median(d)), 1)
        m["disagreement_within_2px_pct"] = round(float((d <= 2 * pixel_m).mean() * 100), 1)
    return m
