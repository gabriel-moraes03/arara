"""Modo cheia: água além do nível mais baixo do período, com plausibilidade pelo terreno.

A zona de água do fluxo de reservatórios (núcleo recorrente dilatado 1 km) apaga inundação, que é
justamente água NÃO recorrente. Aqui, para cada passagem:

- água aberta = HH escuro (mesmo limiar da série) ∩ planície (HAND <= 15 m) ∩ dado válido, sem manchas
  menores que 0,1 km²; sem HAND, a planície é a área toda e isso é avisado;
- referência = água aberta da passagem mais seca SEM vento (dilatada 2 px, tolerância de margem);
- água de cheia = água aberta fora da referência;
- possível vegetação alagada = HH pelo menos 3 dB acima da mediana das passagens em que o pixel era
  TERRA (a mediana da série toda seria puxada para baixo nas datas em que ele virou água, e a terra seca
  de antes da cheia pareceria "clara": no delta do Jacuí isso marcava 75 km² em junho), em terreno baixo
  (HAND <= 10 m) e fora da água aberta. Na banda L a água sob a vegetação reflete o sinal duas vezes
  (tronco + água) e a vegetação fica mais clara. Solo encharcado e mudança de cultura também clareiam,
  por isso é sempre "possível", nunca confirmado.

Mede onde há água a mais; não diz por quê (chuva, maré, operação de barragem).
"""
import warnings

import numpy as np
from scipy.ndimage import binary_dilation

from . import publish
from .geom import MANCHA_MIN_KM2, tirar_manchas

HAND_MAX_CHEIA_M = 15.0
HAND_MAX_VEG_M = 10.0
DELTA_VEG_DB = 3.0
MIN_DATAS_VEG = 4
MIN_DATAS_TERRA = 3          # passagens como terra para haver uma base do pixel
TOLERANCIA_REF_PX = 2

COR_REFERENCIA = (31, 79, 160, 200)      # água da passagem mais seca
COR_CHEIA = (34, 211, 238, 235)          # água além dela
COR_VEGETACAO = (192, 132, 252, 210)     # possível vegetação alagada
REF, CHEIA, VEGETACAO = 1, 2, 3
CORES = {REF: COR_REFERENCIA, CHEIA: COR_CHEIA, VEGETACAO: COR_VEGETACAO}


def planicie(hand, limite_m):
    """Pixels que podem alagar. Sem HAND no pixel ele fica (não se corta no escuro)."""
    return ~(np.isfinite(hand) & (hand > limite_m))


def referencia_seca(areas, vento):
    """Índice da passagem com menos água aberta entre as sem vento (vento faz a água 'sumir' no limiar,
    então uma data de vento pareceria falsamente seca). Sem data calma, usa todas."""
    calmas = [i for i, v in enumerate(vento) if not v] or list(range(len(areas)))
    return min(calmas, key=lambda i: areas[i])


def mapear(brutas, dbs, comum, vento, pixel_m, hand=None):
    """brutas: HH < limiar por data (dentro do dado válido comum); dbs: HH filtrado em dB por data.
    Devolve classes por data (0 nada, 1 referência, 2 cheia, 3 possível vegetação alagada) e o índice da
    referência."""
    tem_hand = hand is not None and np.isfinite(hand).any()
    baixo = planicie(hand, HAND_MAX_CHEIA_M) if tem_hand else np.ones_like(comum)
    baixo_veg = planicie(hand, HAND_MAX_VEG_M) if tem_hand else np.ones_like(comum)
    abertas = [tirar_manchas(b & baixo & comum, pixel_m, MANCHA_MIN_KM2) for b in brutas]
    r = referencia_seca([int(a.sum()) for a in abertas], vento)
    ref = binary_dilation(abertas[r], iterations=TOLERANCIA_REF_PX) & comum
    mediana = None
    if len(dbs) >= MIN_DATAS_VEG:
        terra = np.stack([np.where(b, np.nan, d) for b, d in zip(brutas, dbs)])
        n_terra = np.isfinite(terra).sum(axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)              # pixel sempre água: sem base
            mediana = np.nanmedian(terra, axis=0)
        mediana[n_terra < MIN_DATAS_TERRA] = np.nan
    classes = []
    for i, a in enumerate(abertas):
        c = np.zeros(comum.shape, "uint8")
        c[abertas[r]] = REF
        cheia = tirar_manchas(a & ~ref, pixel_m, MANCHA_MIN_KM2)
        c[cheia] = CHEIA
        if mediana is not None:
            with np.errstate(invalid="ignore"):
                clareou = (dbs[i] - mediana >= DELTA_VEG_DB) & baixo_veg & comum & ~a & ~ref
            c[tirar_manchas(clareou, pixel_m, MANCHA_MIN_KM2)] = VEGETACAO
        classes.append(c)
    return classes, r


def rodar(ctx, extras, progresso, hand_fn=None):
    progresso("flood", 0.80, "procurando água além do nível mais baixo do período (modo cheia)")
    cls, datas, area_px = ctx["cls"], ctx["datas"], ctx["area_px"]
    hand, fonte_hand, aviso_hand = None, None, None
    if hand_fn is None:
        from .terreno import hand_na_grade as hand_fn
    try:
        if ctx["spec"].get("terrain") is False:
            raise RuntimeError("terreno desligado no pedido")
        hand, lidos = hand_fn(ctx["xs"], ctx["ys"], ctx["epsg"])
        if not lidos or not np.isfinite(hand).any():
            hand, aviso_hand = None, "HAND sem cobertura nesta área"
        else:
            fonte_hand = {"product": "GLO-30 HAND (ASF, 2021)", "tiles": lidos}
    except Exception as e:  # noqa: BLE001  (rede: segue sem terreno, com aviso)
        hand, aviso_hand = None, ("HAND desligado no pedido" if ctx["spec"].get("terrain") is False
                                  else f"HAND indisponível ({type(e).__name__})")
    vento = [bool(d["suspeita_vento"]) for d in datas]
    classes, r = mapear(cls["raw"], ctx["dbs"], cls["common_valid"], vento, ctx["pixel_m"], hand)
    km2 = lambda m: round(float(m.sum() * area_px / 1e6), 3)  # noqa: E731
    por_data = []
    for d, c in zip(datas, classes):
        por_data.append({"date": d["date"], "reference_water_km2": km2(c == REF), "flood_km2": km2(c == CHEIA),
                         "flooded_vegetation_km2": km2(c == VEGETACAO), "suspeita_vento": d["suspeita_vento"]})
    pico = max(range(len(classes)), key=lambda i: por_data[i]["flood_km2"] + por_data[i]["flooded_vegetation_km2"])
    limitacoes = ["referência = passagem mais seca do período: uma cheia que durou o período inteiro não aparece",
                  "vegetação alagada é possível, não confirmada: solo encharcado e mudança de cultura também clareiam o HH"]
    if aviso_hand:
        limitacoes.insert(0, aviso_hand + ": sem corte por terreno, terra lisa em áreas altas pode aparecer como água")
        ctx["avisos"].append(aviso_hand + "; o modo cheia rodou sem corte por terreno")
    if len(datas) < MIN_DATAS_VEG:
        limitacoes.append(f"menos de {MIN_DATAS_VEG} passagens: vegetação alagada não avaliada")
    extras["cheia"] = {
        "status": "ok", "method": "agua_alem_da_passagem_mais_seca",
        "reference_date": datas[r]["date"], "peak_date": datas[pico]["date"],
        "peak_flood_km2": por_data[pico]["flood_km2"],
        "peak_flooded_vegetation_km2": por_data[pico]["flooded_vegetation_km2"],
        "per_date": por_data, "terrain": fonte_hand,
        "params": {"hand_max_m": HAND_MAX_CHEIA_M if hand is not None else None,
                   "hand_max_vegetation_m": HAND_MAX_VEG_M if hand is not None else None,
                   "vegetation_delta_db": DELTA_VEG_DB, "reference_tolerance_px": TOLERANCIA_REF_PX,
                   "min_patch_km2": MANCHA_MIN_KM2},
        "limitations": limitacoes,
    }
    extras["mascaras_cheia"] = {"classes": classes, "peak": pico}
    camadas = extras.setdefault("camadas", {})
    for d, c in zip(datas, classes):
        s = d["date"].replace("-", "")
        camadas[f"flood_{s}"] = ("flood", d["date"], publish.rgba_classes(c, CORES),
                                 f"Cheia em {d['date']} (referência {datas[r]['date']})")
