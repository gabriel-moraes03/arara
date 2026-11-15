"""Confiança de cada passagem e um resumo em linguagem simples, montados só a partir dos números medidos.

Sem IA e sem adjetivos: cada frase vem de um campo da análise. A confiança é um selo por data
(alta, média, baixa) com os motivos, para quem não vai ler a tabela inteira.
"""
VALIDO_MINIMO_SELO = 0.99      # abaixo de 95% a cena já é descartada; entre 95 e 99% ela fica com selo médio
ALTA, MEDIA, BAIXA = "alta", "média", "baixa"
CHEIA_RELEVANTE_KM2 = 1.0
CHEIA_RELEVANTE_FRACAO = 0.005


def num(v, casas=1):
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def br(data):
    a, m, d = data.split("-")
    return f"{d}/{m}/{a}"


def confianca(datas, quality, validacao=None, cheia=None):
    """Acrescenta date['confidence'] = {level, reasons} em cada passagem."""
    concord = {p["date"]: p.get("agreement") for p in ((validacao or {}).get("divergence") or {}).get("per_date", [])}
    sem_terreno = bool(cheia and cheia.get("status") == "ok" and not cheia.get("terrain"))
    for d in datas:
        motivos, nivel = [], ALTA
        if d.get("suspeita_vento"):
            nivel = BAIXA
            motivos.append("vento: a água desta passagem pode estar subestimada")
        vf = d.get("valid_fraction_aoi")
        if vf is not None and vf < VALIDO_MINIMO_SELO:
            nivel = BAIXA if nivel == BAIXA else MEDIA
            motivos.append(f"só {num(vf * 100, 0)}% da área com dado válido")
        if concord.get(d["date"]) in ("diverge", "optical_no_water"):
            nivel = BAIXA if nivel == BAIXA else MEDIA
            motivos.append("o Sentinel-2 vê uma área de água diferente nesta data")
        if quality == "experimental":
            nivel = BAIXA if nivel == BAIXA else MEDIA
            motivos.append("análise experimental")
        if sem_terreno:
            nivel = BAIXA if nivel == BAIXA else MEDIA
            motivos.append("sem modelo de terreno (HAND): cheia sem corte de áreas altas")
        if nivel == ALTA:
            motivos.append("cena completa, sem vento" + (", coerente com o Sentinel-2" if concord.get(d["date"]) == "agree" else ""))
        d["confidence"] = {"level": nivel, "reasons": motivos}


def resumo(datas, area_km2, cheia=None, chuva=None, municipios=None):
    """Texto curto para leigos. Medido primeiro; chuva e municípios como contexto, nunca como causa."""
    frases = []
    vento = [br(d["date"])[:5] for d in datas if d.get("suspeita_vento")]
    if cheia and cheia.get("status") == "ok":
        pico = next(p for p in cheia["per_date"] if p["date"] == cheia["peak_date"])
        total = pico["flood_km2"] + pico["flooded_vegetation_km2"]
        ref = br(cheia["reference_date"])
        if total < max(CHEIA_RELEVANTE_KM2, CHEIA_RELEVANTE_FRACAO * area_km2):
            frases.append(f"O radar não viu cheia relevante no período: a maior diferença para a passagem mais seca "
                          f"({ref}) foi de {num(total, 2)} km².")
        else:
            veg = (f", mais {num(pico['flooded_vegetation_km2'])} km² de possível vegetação alagada"
                   if pico["flooded_vegetation_km2"] >= 0.1 else "")
            frases.append(f"Em {br(pico['date'])} o radar viu {num(pico['flood_km2'])} km² de água além da passagem "
                          f"mais seca ({ref}){veg}.")
            ms = [m for m in (municipios or {}).get("municipalities", []) if m["flood_km2"] + m["flooded_vegetation_km2"] >= 0.1]
            if ms:
                nomes = [f"{m['name']} ({m['uf']})" for m in ms[:3]]
                frases.append(("A maior parte fica em " if len(ms) > 1 else "Toda ela fica em ")
                              + (", ".join(nomes[:-1]) + " e " + nomes[-1] if len(nomes) > 1 else nomes[0]) + ".")
            if chuva and chuva.get("status") == "ok":
                c = next((p for p in chuva["per_date"] if p["date"] == pico["date"]), None)
                if c and c["rain_7d_mm"] is not None:
                    frases.append(f"Nos 7 dias antes dessa passagem choveu {num(c['rain_7d_mm'], 0)} mm em média na "
                                  "área (GPM IMERG).")
    if vento:
        frases.append(f"{'Uma data' if len(vento) == 1 else str(len(vento)) + ' datas'} com vento "
                      f"({', '.join(vento)}) pode{'' if len(vento) == 1 else 'm'} subestimar a água.")
    return {"text": " ".join(frases), "generated_by": "regras sobre os números medidos (sem IA)"}
