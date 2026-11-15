"""Etapas optical_s2 + validate_cross do orquestrador."""
import sys
import traceback

from shapely.geometry import mapping

from . import crossval, optical_s2, publish, quality

COR_OPTICO = (64, 196, 160, 210)


def rodar(ctx, extras, progresso, referencia=optical_s2.referencia):
    if ctx["spec"].get("optical") is False:
        extras["validacao"] = {"status": "not_optically_validated", "reason": "validação óptica desligada no pedido"}
        return
    cls, datas = ctx["cls"], ctx["datas"]
    aoi_mask = cls["common_valid"]
    geo = mapping(ctx["aoi"])
    por_data, fontes, motivos = [], [], []
    for i, d in enumerate(datas):
        progresso("optical_s2", 0.72 + 0.12 * i / len(datas), f"Sentinel-2 perto de {d['date']}")
        try:
            ref = referencia(geo, d["date"], ctx["xs"], ctx["ys"], ctx["epsg"], aoi_mask)
        except Exception:  # noqa: BLE001  (rede/serviço: a análise de radar continua; detalhe só no log)
            traceback.print_exc(file=sys.stderr)
            ref = {"status": "not_optically_validated", "reason": "Sentinel-2 indisponível (falha de rede ou do serviço)"}
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
