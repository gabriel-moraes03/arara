"""Etapas optical_s2 + validate_cross do orquestrador.

As datas são consultadas em paralelo (S2_WORKERS) e cada referência óptica fica no cache, com a chave
(data do radar, área, grade). "Com nuvem" só fica no cache para datas com mais de 10 dias: perto de
hoje uma cena nova do Sentinel-2 ainda pode chegar. Falha de rede nunca fica no cache.
"""
import datetime
import hashlib
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from shapely import wkt as shapely_wkt
from shapely.geometry import mapping

from . import cache, crossval, optical_s2, publish, quality

S2_WORKERS = 4
DIAS_PARA_FIXAR = 10


def referencia_com_cache(referencia, geo, data, xs, ys, epsg, aoi_mask, aoi_wkt):
    usar = referencia is optical_s2.referencia          # nos testes a referência é falsa: sem cache
    destino = None
    if usar:
        destino = cache.caminho("s2", cache.chave("s2", data, aoi_wkt, epsg, float(xs[0]), float(xs[-1]), len(xs),
                                                  float(ys[0]), float(ys[-1]), len(ys),
                                                  hashlib.md5(np.packbits(aoi_mask).tobytes()).hexdigest()))
        lido = cache.ler_npz(destino)
        if lido is not None:
            meta, a = lido
            return {**meta, **a, "cache": "hit"}
    try:
        ref = referencia(geo, data, xs, ys, epsg, aoi_mask)
    except Exception:  # noqa: BLE001  (rede/serviço: a análise de radar continua; detalhe só no log)
        traceback.print_exc(file=sys.stderr)
        return {"status": "not_optically_validated", "reason": "Sentinel-2 indisponível (falha de rede ou do serviço)"}
    if usar and (ref["status"] == "ok" or (datetime.date.today() - datetime.date.fromisoformat(data)).days > DIAS_PARA_FIXAR):
        meta = {k: v for k, v in ref.items() if k not in ("water", "valid")}
        arrays = {k: ref[k] for k in ("water", "valid") if k in ref}
        try:
            cache.salvar_npz(destino, meta, **arrays)
        except (OSError, TypeError, ValueError):
            traceback.print_exc(file=sys.stderr)
    return {**ref, "cache": "miss"}

COR_OPTICO = (64, 196, 160, 210)


def rodar(ctx, extras, progresso, referencia=optical_s2.referencia):
    if ctx["spec"].get("optical") is False:
        extras["validacao"] = {"status": "not_optically_validated", "reason": "validação óptica desligada no pedido"}
        return
    cls, datas = ctx["cls"], ctx["datas"]
    aoi_mask = cls["common_valid"]
    geo = mapping(ctx["aoi"])
    por_data, fontes, motivos = [], [], []
    aoi_wkt = shapely_wkt.dumps(ctx["aoi"], rounding_precision=7)
    progresso("optical_s2", 0.72, f"Sentinel-2 perto de {len(datas)} passagens ({S2_WORKERS} por vez)")
    with ThreadPoolExecutor(S2_WORKERS) as ex:
        refs = list(ex.map(lambda d: referencia_com_cache(referencia, geo, d["date"], ctx["xs"], ctx["ys"], ctx["epsg"],
                                                          aoi_mask, aoi_wkt), datas))
    for i, (d, ref) in enumerate(zip(datas, refs)):
        progresso("optical_s2", 0.72 + 0.12 * (i + 1) / len(datas), f"Sentinel-2 perto de {d['date']}")
        if ref["status"] != "ok":
            motivos.append(ref["reason"])
            por_data.append({"date": d["date"], "status": "not_optically_validated", "reason": ref["reason"]})
            continue
        valido = ref["valid"] & aoi_mask
        m = crossval.metricas(cls["water"][i], ref["water"], valido, ctx["area_px"], ctx["pixel_m"])
        por_data.append({"date": d["date"], "status": "validated", "optical_date": ref["date"],
                         "days_apart": ref["days_apart"], "clear_fraction": ref["clear_fraction"],
                         "suspeita_vento": d["suspeita_vento"], **m})
        fontes.append({"sar_date": d["date"], **{k: ref[k] for k in (
            "date", "days_apart", "items", "cloud_cover_pct", "processing_baseline", "boa_offset_added", "assets")}})
        s = ref["date"].replace("-", "")
        extras.setdefault("camadas", {})[f"s2_water_{s}"] = (
            "optical_water", ref["date"], publish.rgba_mascara(ref["water"] & valido, COR_OPTICO),
            f"Água no Sentinel-2 (MNDWI > 0) em {ref['date']}")
    progresso("validate_cross", 0.86, "comparando radar e óptico")
    ok = [p for p in por_data if p["status"] == "validated"]
    extras["fontes_opticas"] = {"catalog": optical_s2.STAC_URL, "collection": optical_s2.COLECAO,
                                "method": "MNDWI = (B03 - B11) / (B03 + B11) > 0; SCL 0,1,3,8,9,10,11 mascarados",
                                "scenes": fontes}
    if not ok:
        extras["validacao"] = {"status": "not_optically_validated", "per_date": por_data,
                               "reason": motivos[0] if motivos else "sem pixels comparáveis"}
        return

    medias, n_por_metrica = {}, {}
    for chave in ("iou", "f1", "precision", "recall"):
        medias[chave], n_por_metrica[chave] = media(ok, chave)
    iou_calmas, _ = media([p for p in ok if not p.get("suspeita_vento")], "iou")
    extras["validacao"] = {
        "status": "validated", "reference": "Sentinel-2 L2A, MNDWI > 0 (referência independente, não verdade de campo)",
        "n_dates_validated": len(ok), "n_dates": len(datas),
        "mean_iou": medias["iou"], "mean_f1": medias["f1"], "mean_precision": medias["precision"], "mean_recall": medias["recall"],
        "n_dates_per_metric": n_por_metrica, "mean_iou_calm": iou_calmas,
        "divergence": quality.resumo_divergencia(quality.divergencia(ok), iou_calmas),
        "per_date": por_data,
        "limitations": ["datas do óptico diferem do radar em até 7 dias", "o radar vê água sob nuvem; o óptico não",
                        "vegetação alagada: o radar em L pode não ver como água aberta o que o MNDWI vê, e vice-versa"],
    }


def media(datas, chave):
    """Média da métrica nas datas em que ela existe. Sem água em nenhum dos dois sensores, precisão,
    recall e IoU são 0/0 (None): a data fica fora daquela média. Devolve (média ou None, n de datas)."""
    vals = [p[chave] for p in datas if p.get(chave) is not None]
    return (round(sum(vals) / len(vals), 4) if vals else None), len(vals)
