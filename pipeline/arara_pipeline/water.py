"""Classificação de água em uma série de janelas HH (dB filtrado), para qualquer AOI.

Método validado em Furnas, sem nada de Furnas fixo: limiar no vale água/terra dos blocos de margem,
um limiar só para a série, zona de água = núcleo recorrente dilatado ∩ AOI (sem presumir que o maior
componente é o corpo de interesse), manchas < 0,1 km² removidas e flag de vento por data.
"""
import numpy as np
from scipy.ndimage import distance_transform_edt

from .geom import DILATACAO_ZONA_M, FRACAO_DATAS_ZONA, MANCHA_MIN_KM2, nucleo_do_lago, tirar_manchas
from .sar import FRACAO_SEMENTE, MIN_BLOCOS_MARGEM, SEMENTE_DB, blocos_de_margem, otsu, vale

LIMIAR_FAIXA_DB = (-22.0, -12.0)
FRACAO_AGUA_FAIXA = (0.005, 0.90)
# Em Furnas as datas de vento ficam +1,97 e +2,51 dB acima da mediana da série; a data calma mais
# clara (26/08, erro de área 0,2%) fica +1,57 dB. O corte de ~1,5 dB do enunciado marcaria 26/08.
VENTO_DELTA_DB = 1.75
BLOCO_M = 2000.0          # lado do bloco de margem (em Furnas: 50 px de 40 m)


def limiar_da_data(db, valido, pixel_m):
    """Limiar bimodal de uma data e as checagens de qualidade. Devolve (limiar, problemas)."""
    bloco = max(10, int(round(BLOCO_M / pixel_m)))
    margem = blocos_de_margem(db, valido, bloco, SEMENTE_DB, FRACAO_SEMENTE)
    problemas = []
    if len(margem) < MIN_BLOCOS_MARGEM:
        problemas.append(f"só {len(margem)} blocos de margem água/terra (mínimo {MIN_BLOCOS_MARGEM}); "
                         "limiar pelo Otsu da área toda")
        limiar = float(otsu(db[valido]))
    else:
        limiar = float(vale(margem.ravel()))
    if not LIMIAR_FAIXA_DB[0] <= limiar <= LIMIAR_FAIXA_DB[1]:
        problemas.append(f"limiar {limiar:.1f} dB fora da faixa esperada "
                         f"({LIMIAR_FAIXA_DB[0]:.0f} a {LIMIAR_FAIXA_DB[1]:.0f} dB)")
    return limiar, problemas, int(len(margem))


def zona_de_agua(brutas, pixel_m, aoi, fracao=FRACAO_DATAS_ZONA, dilatacao_m=DILATACAO_ZONA_M):
    """Pixels a até dilatacao_m de água recorrente (água em >= fracao das datas), dentro da AOI.
    Todos os corpos d'água da AOI ficam: não se escolhe "o maior"."""
    nucleo = nucleo_do_lago(brutas, fracao)
    if not nucleo.any():
        return np.zeros_like(nucleo), nucleo
    return (distance_transform_edt(~nucleo) * pixel_m <= dilatacao_m) & aoi, nucleo


def suspeita_vento(brilhos_db, delta=VENTO_DELTA_DB):
    """Datas em que a água está mais clara que o normal da série (vento encrespa a água e ela
    'some' no limiar). Marca, não corrige. Precisa de >= 3 datas para haver um 'normal'."""
    b = np.asarray(brilhos_db, float)
    if np.isfinite(b).sum() < 3:
        return [False] * len(b), None
    ref = float(np.nanmedian(b))
    return [bool(np.isfinite(x) and x > ref + delta) for x in b], ref


def classificar_serie(dbs, validos, aoi, pixel_m, limiar=None):
    """dbs/validos: listas alinhadas (uma por data, mesma grade); aoi: máscara da área pedida.
    Devolve dict com as máscaras de água, o limiar, as métricas por data e a qualidade."""
    comum = aoi.copy()
    for v in validos:
        comum &= v
    n_comum = int(comum.sum())
    if n_comum == 0:
        raise ValueError("nenhum pixel válido em todas as datas dentro da área")
    candidatos = [limiar_da_data(db, v & aoi, pixel_m) for db, v in zip(dbs, validos)]
    motivos = []
    if limiar is None:
        # o MESMO limiar para todas as datas: o da primeira data que passa nas checagens
        bons = [i for i, c in enumerate(candidatos) if not c[1]]
        origem = bons[0] if bons else 0
        limiar = candidatos[origem][0]
        if not bons:
            motivos += candidatos[0][1]
        fonte = {"source": "limiar_bimodal", "date_index": origem}
    else:
        fonte = {"source": "informado"}
    brutas = [(db < limiar) & comum for db in dbs]
    zona, nucleo = zona_de_agua(brutas, pixel_m, aoi)
    aguas = [tirar_manchas(b & zona, pixel_m, MANCHA_MIN_KM2) for b in brutas]
    fracoes = [float(a.sum() / n_comum) for a in aguas]
    for i, f in enumerate(fracoes):
        if not FRACAO_AGUA_FAIXA[0] <= f <= FRACAO_AGUA_FAIXA[1]:
            motivos.append(f"data {i + 1}: fração de água {f:.1%} fora de "
                           f"{FRACAO_AGUA_FAIXA[0]:.1%} a {FRACAO_AGUA_FAIXA[1]:.0%}")
    # brilho HH nos mesmos pixels em todas as datas (água recorrente), para o flag de vento
    ref_px = nucleo & comum
    brilhos = [float(np.nanmedian(db[ref_px])) if ref_px.sum() >= 100 else float("nan") for db in dbs]
    vento, brilho_ref = suspeita_vento(brilhos)
    return {
        "threshold_db": round(float(limiar), 2), "threshold": fonte,
        "water": aguas, "raw": brutas, "zone": zona, "common_valid": comum, "n_common": n_comum,
        "water_fraction": fracoes, "hh_water_db": brilhos, "hh_water_ref_db": brilho_ref, "wind": vento,
        "per_date_threshold_db": [round(c[0], 2) for c in candidatos],
        "margin_blocks": [c[2] for c in candidatos],
        "experimental": bool(motivos), "experimental_reasons": motivos,
    }
