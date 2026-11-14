"""Comparação entre duas datas: o que medimos (não a causa)."""
import numpy as np

SEM_DADO, TERRA_ESTAVEL, AGUA_ESTAVEL, EXPANSAO, RETRACAO = 0, 1, 2, 3, 4
CLASSES = {SEM_DADO: "no_data", TERRA_ESTAVEL: "stable_land", AGUA_ESTAVEL: "stable_water",
           EXPANSAO: "expansion", RETRACAO: "retraction"}


def comparar(antes, depois, valido, pixel_area_m2):
    """Raster de classes (uint8) e métricas. area_ha = pixels * area_pixel_m2 / 10000."""
    classes = np.full(antes.shape, SEM_DADO, "uint8")
    classes[valido & ~antes & ~depois] = TERRA_ESTAVEL
    classes[valido & antes & depois] = AGUA_ESTAVEL
    classes[valido & ~antes & depois] = EXPANSAO
    classes[valido & antes & ~depois] = RETRACAO
    px = {nome: int((classes == c).sum()) for c, nome in CLASSES.items()}
    ha = {nome: round(n * pixel_area_m2 / 10000, 2) for nome, n in px.items()}
    n_valido = int(valido.sum())

    def agua(m):
        n = int((m & valido).sum())
        return round(n * pixel_area_m2 / 1e6, 3), round(100 * n / n_valido, 3) if n_valido else None

    a_km2, a_pct = agua(antes)
    d_km2, d_pct = agua(depois)
    return classes, {
        "pixels": px, "pixel_area_m2": pixel_area_m2,
        "stable_water_ha": ha["stable_water"], "stable_land_ha": ha["stable_land"],
        "expansion_ha": ha["expansion"], "retraction_ha": ha["retraction"],
        "net_change_ha": round(ha["expansion"] - ha["retraction"], 2),
        "water_km2_before": a_km2, "water_km2_after": d_km2,
        "water_pct_before": a_pct, "water_pct_after": d_pct,
        "valid_km2": round(n_valido * pixel_area_m2 / 1e6, 3),
    }
