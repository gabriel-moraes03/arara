"""Padrões medidos na série de água: tendência, alerta, permanência, trechos que mais secaram.
Tudo sai dos mapas de água já classificados; nenhuma causa é inferida aqui."""
import datetime

import numpy as np
from scipy.ndimage import label

PERMANENTE, SAZONAL, OCASIONAL = 3, 2, 1
LIM_PERMANENTE, LIM_SAZONAL = 0.9, 0.25
MIN_DATAS_TENDENCIA = 4
MIN_DATAS_ANOMALIA = 4
VENTO_FORA = "datas com suspeita de vento ficam fora do ajuste"


def _calmas(datas, areas, vento):
    vento = vento or [False] * len(datas)
    return [(datetime.date.fromisoformat(d), float(a)) for d, a, v in zip(datas, areas, vento) if not v]


def ruido_serie(areas_calmas):
    """Ruído da série: mediana das variações entre passagens calmas seguidas (km²). Mesmo número no
    alerta e na leitura (insights), para os dois nunca se contradizerem."""
    a = np.asarray(areas_calmas, float)
    return float(np.median(np.abs(np.diff(a)))) if len(a) >= 3 else None


def tendencia(datas, areas, vento=None):
    """Theil-Sen (mediana das inclinações entre pares): robusto a uma data ruim. km² por semana."""
    c = _calmas(datas, areas, vento)
    if len(c) < MIN_DATAS_TENDENCIA:
        return {"status": "unavailable", "reason": f"tendência precisa de {MIN_DATAS_TENDENCIA} datas sem suspeita de vento (há {len(c)})"}
    dias = np.array([(d - c[0][0]).days for d, _ in c], float)
    area = np.array([a for _, a in c])
    incl = [(area[j] - area[i]) / (dias[j] - dias[i]) for i in range(len(c)) for j in range(i + 1, len(c)) if dias[j] > dias[i]]
    semana = float(np.median(incl)) * 7
    ref = float(np.median(area))
    return {"status": "ok", "km2_per_week": round(semana, 4), "km2_per_month": round(semana * 30 / 7, 3),
            "pct_per_month": round(100 * semana * 30 / 7 / ref, 2) if ref else None,
            "direction": "ganhando" if semana > 0 else "perdendo" if semana < 0 else "estável",
            "since": str(c[0][0]), "n_dates": len(c), "method": "Theil-Sen", "note": VENTO_FORA}


def anomalia(datas, areas, vento=None):
    """Última passagem contra o normal da série anterior (mediana e MAD das datas sem vento)."""
    vento = vento or [False] * len(datas)
    if len(datas) < MIN_DATAS_ANOMALIA:
        return {"status": "unavailable", "reason": f"alerta precisa de {MIN_DATAS_ANOMALIA} datas"}
    antes = [float(a) for a, v in zip(areas[:-1], vento[:-1]) if not v]
    if len(antes) < MIN_DATAS_ANOMALIA - 1:
        return {"status": "unavailable", "reason": "poucas datas anteriores sem suspeita de vento"}
    mediana = float(np.median(antes))
    mad = float(np.median(np.abs(np.array(antes) - mediana))) * 1.4826
    ultima = float(areas[-1])
    z = (ultima - mediana) / mad if mad > 0 else 0.0
    pct = 100 * (ultima - mediana) / mediana if mediana else 0.0
    # só sobe de nível se o desvio sai da faixa p10-p90 dos resíduos das datas anteriores E passa o ruído
    # entre passagens; senão é variação normal da medida, por maior que pareça o z
    desvio = ultima - mediana
    p10, p90 = (float(x) for x in np.percentile(np.array(antes) - mediana, [10, 90]))
    ruido = ruido_serie([float(a) for a, v in zip(areas, vento) if not v])
    fora = (desvio < p10 or desvio > p90) and (ruido is None or abs(desvio) > ruido)
    nivel = "normal" if not fora or abs(z) < 2 else "atenção" if abs(z) < 3 else "alerta"
    return {"status": "ok", "level": nivel, "last_date": datas[-1], "last_km2": round(ultima, 3), "normal_km2": round(mediana, 3),
            "pct_vs_normal": round(pct, 2), "z": round(float(z), 2), "direction": "abaixo" if ultima < mediana else "acima",
            "deviation_km2": round(desvio, 3), "residual_band_km2": [round(p10, 3), round(p90, 3)],
            "series_noise_km2": None if ruido is None else round(ruido, 3), "within_noise": not fora,
            "last_is_wind_suspect": bool(vento[-1]),
            "note": "A última data tem suspeita de vento: a área pode estar subestimada." if vento[-1] else None}


def permanencia(aguas, valido, vento=None):
    """Fração das datas sem suspeita de vento em que cada pixel foi água -> permanente (>=90%),
    sazonal (25-90%), ocasional. Data com vento fica fora: nela a água encrespada some do radar e um
    único dia derrubaria toda a lâmina permanente para sazonal."""
    vento = vento or [False] * len(aguas)
    calmas = [a for a, v in zip(aguas, vento) if not v]
    if len(calmas) < 3:
        return None, {"status": "unavailable", "reason": f"frequência de água precisa de 3 datas sem suspeita de vento (há {len(calmas)})"}
    freq = np.mean(np.stack(calmas).astype("float32"), axis=0)
    cls = np.zeros(freq.shape, "uint8")
    cls[(freq > 0) & (freq < LIM_SAZONAL)] = OCASIONAL
    cls[(freq >= LIM_SAZONAL) & (freq < LIM_PERMANENTE)] = SAZONAL
    cls[freq >= LIM_PERMANENTE] = PERMANENTE
    cls[~valido] = 0
    return cls, {"status": "ok", "n_dates": len(calmas), "n_wind_excluded": len(aguas) - len(calmas),
                 "thresholds": {"permanent": LIM_PERMANENTE, "seasonal": LIM_SAZONAL}, "freq": freq,
                 "note": VENTO_FORA if len(calmas) < len(aguas) else None}


def resumo_permanencia(cls, area_px_m2):
    k = lambda c: round(float((cls == c).sum()) * area_px_m2 / 1e6, 3)
    return {"permanent_km2": k(PERMANENTE), "seasonal_km2": k(SAZONAL), "occasional_km2": k(OCASIONAL)}


def trechos_secos(retracao, xs, ys, epsg, area_px_m2, topo=3, min_ha=1.0):
    """Os trechos contíguos que mais deixaram de ser água, com centro em lon/lat."""
    from pyproj import Transformer
    rot, n = label(retracao, structure=np.ones((3, 3)))
    if n == 0:
        return []
    tam = np.bincount(rot.ravel())[1:]
    ordem = np.argsort(-tam)[:topo]
    t = Transformer.from_crs(epsg, 4326, always_xy=True)
    out = []
    for r, i in enumerate(ordem, start=1):
        ha = float(tam[i]) * area_px_m2 / 1e4
        if ha < min_ha:
            continue
        ys_i, xs_i = np.nonzero(rot == i + 1)
        lon, lat = t.transform(float(xs[xs_i].mean()), float(ys[ys_i].mean()))
        l0, a0 = t.transform(float(xs[xs_i].min()), float(ys[ys_i].min()))
        l1, a1 = t.transform(float(xs[xs_i].max()), float(ys[ys_i].max()))
        out.append({"rank": r, "area_ha": round(ha, 2), "lon": round(lon, 5), "lat": round(lat, 5),
                    "bbox": [round(min(l0, l1), 5), round(min(a0, a1), 5), round(max(l0, l1), 5), round(max(a0, a1), 5)]})
    return out
