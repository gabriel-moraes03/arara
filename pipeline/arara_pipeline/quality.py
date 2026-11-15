"""Estado de qualidade da análise: reliable | experimental | no_reliable_water, com os motivos.

no_reliable_water quer dizer que o radar não separou água de terra nesta área: nada de área, saldo,
tendência, alerta, permanência, trechos, projeção ou vento é publicado, só o status, os motivos,
as cenas e o radar HH para inspeção. experimental mantém os números, sem projeção.
"""
import math

from .sar import MIN_BLOCOS_MARGEM
from .water import FRACAO_AGUA_FAIXA, LIMIAR_FAIXA_DB

RELIABLE, EXPERIMENTAL, NO_RELIABLE_WATER = "reliable", "experimental", "no_reliable_water"

# divergência forte: o Sentinel-2 vê ~0 água onde o radar vê bastante
OPTICO_SEM_AGUA = 0.005
RADAR_COM_AGUA = 0.05
# divergência moderada: área do radar difere mais de 30% da óptica, ou IoU médio < 0,7
DIVERGENCIA_RELATIVA = 0.30
IOU_MINIMO = 0.70
# rótulo da tabela radar x Sentinel-2: "concordam" só com diferença de fração abaixo de 5 pontos percentuais
CONCORDA_PP = 5.0

O_QUE_TENTAR = ("desenhe uma área menor em volta do corpo d'água, com margem de terra dos dois lados, "
                "ou escolha outra geometria (trilha/frame) no catálogo")


def divergencia(por_data):
    """Classifica cada data validada: forte (óptico ~0 água, radar com água), moderada ou nenhuma.
    Data com suspeita de vento fica na lista como 'wind' e não conta: a água dela já é sabidamente
    subestimada e está marcada."""
    linhas = []
    for p in por_data:
        if p.get("status") != "validated" or not p.get("compared_km2"):
            continue
        f_radar = p["sar_water_km2"] / p["compared_km2"]
        f_opt = p["optical_water_km2"] / p["compared_km2"]
        if p.get("suspeita_vento"):
            nivel = "wind"
        elif f_opt < OPTICO_SEM_AGUA and f_radar >= RADAR_COM_AGUA:
            nivel = "strong"
        elif f_opt > 0 and abs(p["sar_water_km2"] - p["optical_water_km2"]) / p["optical_water_km2"] > DIVERGENCIA_RELATIVA:
            nivel = "moderate"
        else:
            nivel = "none"
        linhas.append({"date": p["date"], "sar_water_fraction": round(f_radar, 4),
                       "optical_water_fraction": round(f_opt, 4), "level": nivel, **concordancia(f_radar, f_opt, nivel)})
    return linhas


def concordancia(f_radar, f_opt, nivel):
    """Rótulo por data, também nas datas de vento (que não entram na contagem): optical_no_water,
    diverge ou agree. 'agree' exige diferença < CONCORDA_PP pontos e nenhuma divergência."""
    pp = round(abs(f_radar - f_opt) * 100, 1)          # arredonda antes de comparar: 22% - 17% dá 4,9999...
    if f_opt < OPTICO_SEM_AGUA and f_radar >= RADAR_COM_AGUA:
        rotulo = "optical_no_water"
    elif pp >= CONCORDA_PP or nivel in ("strong", "moderate"):
        rotulo = "diverge"
    else:
        rotulo = "agree"
    return {"difference_pp": pp, "agreement": rotulo}


def resumo_divergencia(linhas, mean_iou=None):
    """mean_iou: IoU médio das datas sem vento."""
    n = sum(1 for x in linhas if x["level"] != "wind")
    fortes = sum(1 for x in linhas if x["level"] == "strong")
    moderadas = sum(1 for x in linhas if x["level"] == "moderate")
    if n and fortes >= max(1, math.ceil(n / 2)):
        nivel = "strong"
    elif n >= 3 and (fortes + moderadas >= 2 or (mean_iou is not None and mean_iou < IOU_MINIMO)):
        nivel = "moderate"
    else:
        nivel = "none"
    return {"level": nivel, "n_dates": n, "n_strong": fortes, "n_moderate": moderadas, "per_date": linhas}


def avaliar(cls, validacao=None):
    """cls: saída de water.classificar_serie; validacao: extras['validacao'] da etapa óptica."""
    graves, leves = [], []
    origem = (cls.get("threshold") or {}).get("date_index")
    margem = cls["margin_blocks"]
    if (cls.get("threshold") or {}).get("source") == "limiar_bimodal" and origem is not None and margem[origem] < MIN_BLOCOS_MARGEM:
        graves.append(f"o radar não achou margem água/terra nítida (só {margem[origem]} blocos de margem, mínimo "
                      f"{MIN_BLOCOS_MARGEM}): não há lago ou rio largo o bastante na área para calibrar o limiar")
    lim = cls["threshold_db"]
    if not LIMIAR_FAIXA_DB[0] <= lim <= LIMIAR_FAIXA_DB[1]:
        graves.append(f"o limiar água/terra saiu em {lim:.1f} dB, fora da faixa da água calma "
                      f"({LIMIAR_FAIXA_DB[0]:.0f} a {LIMIAR_FAIXA_DB[1]:.0f} dB): o que ficou escuro é terra lisa, não água")
    # datas com vento ficam fora: a água delas já é sabidamente subestimada e está marcada
    vento = cls.get("wind") or [False] * len(cls["water_fraction"])
    fracoes = [f for f, v in zip(cls["water_fraction"], vento) if not v]
    fora = [f for f in fracoes if not FRACAO_AGUA_FAIXA[0] <= f <= FRACAO_AGUA_FAIXA[1]]
    if fracoes and len(fora) > len(fracoes) / 2:
        graves.append(f"em {len(fora)} de {len(fracoes)} datas a água ficou fora de "
                      f"{FRACAO_AGUA_FAIXA[0]:.1%} a {FRACAO_AGUA_FAIXA[1]:.0%} da área")
    elif fora:
        leves.append(f"em {len(fora)} de {len(fracoes)} datas a água ficou fora de "
                     f"{FRACAO_AGUA_FAIXA[0]:.1%} a {FRACAO_AGUA_FAIXA[1]:.0%} da área")
    div = (validacao or {}).get("divergence") or {}
    if div.get("level") == "strong":
        graves.append(f"o Sentinel-2 não vê água onde o radar vê (em {div['n_strong']} de {div['n_dates']} datas "
                      "comparadas): o radar está contando terra como água")
    elif div.get("level") == "moderate":
        iou = validacao.get("mean_iou_calm", validacao.get("mean_iou"))
        leves.append(f"o radar diverge do Sentinel-2 em {div['n_strong'] + div['n_moderate']} de {div['n_dates']} datas sem vento"
                     + (f" (IoU médio {iou:.2f})" if iou is not None else ""))
    # motivos de qualidade por data que o classificador já registrou e não são as checagens acima
    for m in cls.get("experimental_reasons", []):
        if "fração de água" in m or "blocos de margem" in m or "fora da faixa" in m:
            continue
        leves.append(m)
    if graves:
        return {"quality": NO_RELIABLE_WATER, "reasons": graves + leves, "what_to_try": O_QUE_TENTAR}
    if leves:
        return {"quality": EXPERIMENTAL, "reasons": leves}
    return {"quality": RELIABLE, "reasons": []}
