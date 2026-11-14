"""Leitura da análise: o que foi MEDIDO separado da CAUSA PROVÁVEL (hipótese, com confiança e o
que conferir). O radar mede onde há água; a causa nunca é afirmada."""
import numpy as np

CONFERIR = ("nível ou vazão de uma estação próxima (ANA Hidroweb / SNIRH), chuva acumulada no período "
            "(GPM IMERG ou CHIRPS) e uma imagem óptica sem nuvem")


def interpretar(datas, comparacao, validacao=None, experimental=False):
    if not comparacao:
        return {"measured": "Uma única passagem válida: há área de água medida, mas não há mudança para descrever.",
                "hypothesis": None, "confidence": None, "check": None, "flags": ["single_date"]}
    areas = np.array([d["water_km2"] for d in datas if not d["suspeita_vento"]])
    c = comparacao
    saldo_km2 = c["net_change_ha"] / 100
    antes = max(c["water_km2_before"], 1e-9)
    pct = 100 * saldo_km2 / antes
    medido = (f"Entre {c['before']} e {c['after']} a água passou de {c['water_km2_before']:.2f} para "
              f"{c['water_km2_after']:.2f} km² ({pct:+.1f}%): {c['expansion_ha']:.1f} ha de água nova e "
              f"{c['retraction_ha']:.1f} ha que deixaram de ser água.")
    flags = []
    # ruído da série: mediana das variações entre passagens calmas seguidas
    ruido = float(np.median(np.abs(np.diff(areas)))) if len(areas) >= 3 else None
    if c.get("wind_caveat"):
        flags.append("wind")
    if experimental:
        flags.append("experimental")
    v_ok = bool(validacao and validacao.get("status") == "validated" and (validacao.get("mean_iou") or 0) >= 0.7)
    if v_ok:
        flags.append("optically_consistent")

    if c.get("wind_caveat"):
        hip = ("Uma das duas datas tem suspeita de vento: a água encrespada fica mais clara no radar e parte dela "
               "deixa de ser classificada. A diferença pode ser, no todo ou em parte, efeito do vento e não mudança real.")
        conf = "baixa"
    elif abs(pct) < 1.0 or (ruido is not None and abs(saldo_km2) <= ruido):
        flags.append("within_noise")
        hip = ("A diferença é do tamanho da variação normal entre passagens desta série; não há indício de mudança "
               "além do ruído da medida.")
        conf = "média" if ruido is not None else "baixa"
    elif saldo_km2 < 0:
        hip = ("Recuo da lâmina d'água. As causas mais comuns são estiagem, vazante sazonal ou retirada de água "
               "(operação de reservatório, irrigação). Vegetação aquática cobrindo a superfície também faz a água "
               "aberta sumir do radar. Só com a área não dá para separar essas causas.")
        conf = "média" if v_ok and not experimental else "baixa"
    else:
        hip = ("Avanço da lâmina d'água. As causas mais comuns são chuva na bacia, cheia sazonal ou enchimento de "
               "reservatório. Solo muito liso ou encharcado também pode parecer água para o radar. Só com a área "
               "não dá para separar essas causas.")
        conf = "média" if v_ok and not experimental else "baixa"
    return {"measured": medido, "hypothesis": hip, "confidence": conf, "check": CONFERIR, "flags": flags,
            "series_noise_km2": None if ruido is None else round(ruido, 3), "net_change_pct": round(pct, 2)}


def rodar(ctx, extras, progresso):
    progresso("insights", 0.89, "separando o que foi medido da hipótese de causa")
    extras["insights"] = interpretar(ctx["datas"], ctx["comparacao"], extras.get("validacao"), ctx["cls"]["experimental"])
