"""Projeção experimental da área de água: persistência amortecida, +12/+24/+36 dias.

Não é previsão hidrológica: é a continuação estatística da própria série, com faixa p10-p90
tirada dos erros que a mesma regra teria cometido no passado. Sempre marcada como experimental.
"""
import datetime

import numpy as np

HORIZONTES_DIAS = (12, 24, 36)
MIN_DATAS = 4
AMORTECIMENTO = 0.6
Z_P90 = 1.2816


def projetar(datas, areas_km2, vento=None, teto_km2=None):
    """datas ISO, áreas em km², vento = lista de bool (datas marcadas ficam fora do ajuste)."""
    vento = vento or [False] * len(datas)
    calmas = [(datetime.date.fromisoformat(d), float(a)) for d, a, v in zip(datas, areas_km2, vento) if not v]
    if len(calmas) < MIN_DATAS:
        return {"status": "unavailable", "experimental": True,
                "reason": f"projeção precisa de pelo menos {MIN_DATAS} datas sem suspeita de vento (há {len(calmas)})"}
    dias = np.array([(d - calmas[0][0]).days for d, _ in calmas], float)
    area = np.array([a for _, a in calmas])
    taxa = np.diff(area) / np.maximum(np.diff(dias), 1)                # km² por dia, entre passagens seguidas
    tendencia = float(np.median(taxa[-3:]))                            # tendência recente, robusta a um salto
    # erro da regra "amanhã = hoje + tendência amortecida" nas passagens passadas, por raiz de 12 dias
    erros = []
    for i in range(2, len(area)):
        passo = dias[i] - dias[i - 1]
        prev = area[i - 1] + AMORTECIMENTO * float(np.median(taxa[max(0, i - 4):i - 1])) * passo
        erros.append((area[i] - prev) / np.sqrt(max(passo, 1) / 12))
    sigma = float(np.sqrt(np.mean(np.square(erros)))) if erros else float(np.std(np.diff(area)))
    ultima_data, ultima = calmas[-1]
    pontos, acumulado = [], 0.0
    for k, h in enumerate(HORIZONTES_DIAS, start=1):
        acumulado += tendencia * 12 * AMORTECIMENTO ** k
        centro = ultima + acumulado
        faixa = Z_P90 * sigma * np.sqrt(k)
        lim = (lambda v: float(min(max(v, 0.0), teto_km2)) if teto_km2 else float(max(v, 0.0)))
        pontos.append({"date": str(ultima_data + datetime.timedelta(days=h)), "days_ahead": h,
                       "water_km2": round(lim(centro), 3), "p10": round(lim(centro - faixa), 3),
                       "p90": round(lim(centro + faixa), 3)})
    return {"status": "ok", "experimental": True, "method": "persistência amortecida", "damping": AMORTECIMENTO,
            "base_date": str(ultima_data), "trend_km2_per_12d": round(tendencia * 12, 4), "sigma_km2": round(sigma, 4),
            "n_dates_used": len(calmas), "points": pontos,
            "note": "Experimental: continuação estatística da série, sem chuva nem operação de reservatório. "
                    "A faixa é p10–p90 dos erros que a mesma regra teve nas passagens anteriores."}


def rodar(ctx, extras, progresso):
    progresso("forecast", 0.87, "projeção experimental das próximas passagens")
    d = ctx["datas"]
    extras["previsao"] = projetar([x["date"] for x in d], [x["water_km2"] for x in d],
                                  [x["suspeita_vento"] for x in d],
                                  teto_km2=ctx["cls"]["n_common"] * ctx["area_px"] / 1e6)
