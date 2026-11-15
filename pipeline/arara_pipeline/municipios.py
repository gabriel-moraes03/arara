"""Municípios onde o radar viu água de cheia, com a população do Censo 2022 (IBGE).

Contexto, não dano: a população é a do município inteiro, não o número de pessoas atingidas. Malhas
e populações vêm das APIs públicas do IBGE e ficam em cache local (ARARA_CACHE_DIR ou ~/.cache/arara).
"""
import json
import os

import numpy as np
from shapely.geometry import shape

from .geom import aneis_do_geojson, mascara_do_poligono, reprojetar_aneis

IBGE = "https://servicodados.ibge.gov.br/api"
UFS_URL = IBGE + "/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson&intrarregiao=UF&qualidade=minima"
MUN_URL = IBGE + "/v3/malhas/estados/{uf}?formato=application/vnd.geo%2Bjson&intrarregiao=municipio&qualidade=intermediaria"
NOMES_URL = IBGE + "/v1/localidades/estados/{uf}/municipios"
POP_URL = IBGE + "/v3/agregados/4709/periodos/2022/variaveis/93?localidades=N6[{ids}]"
NOTA = "população do município inteiro (Censo 2022, IBGE), não o número de pessoas atingidas"


def pasta_cache():
    from . import cache
    return cache.pasta("ibge")


def obter_json(url, nome=None, timeout=60):
    """GET com cache em disco quando `nome` é dado."""
    import requests
    caminho = os.path.join(pasta_cache(), nome) if nome else None
    if caminho and os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    dado = r.json()
    if caminho:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dado, f, ensure_ascii=False)
    return dado


def municipios_na_area(aoi, obter=obter_json):
    """[(código, nome, sigla UF, geometria GeoJSON)] dos municípios que tocam a AOI (lon/lat)."""
    ufs = obter(UFS_URL, "ufs.json")
    out = []
    for f in ufs["features"]:
        if not shape(f["geometry"]).intersects(aoi):
            continue
        uf = f["properties"]["codarea"]
        malha = obter(MUN_URL.format(uf=uf), f"municipios_{uf}.json")
        nomes = {str(m["id"]): (m["nome"], m["microrregiao"]["mesorregiao"]["UF"]["sigla"])
                 for m in obter(NOMES_URL.format(uf=uf), f"nomes_{uf}.json")}
        for m in malha["features"]:
            if shape(m["geometry"]).intersects(aoi):
                cod = str(m["properties"]["codarea"])
                nome, sigla = nomes.get(cod, (cod, ""))
                out.append((cod, nome, sigla, m["geometry"]))
    return out


def populacao(codigos, obter=obter_json):
    if not codigos:
        return {}
    dado = obter(POP_URL.format(ids=",".join(sorted(codigos))))
    out = {}
    for s in dado[0]["resultados"][0]["series"]:
        v = s["serie"].get("2022")
        out[s["localidade"]["id"]] = int(v) if v and v.isdigit() else None
    return out


def contar(classes, munis, xs, ys, epsg, area_px, cheia_cls, veg_cls):
    """km² de cheia e de possível vegetação alagada por município, na grade da análise."""
    linhas = []
    for cod, nome, uf, geo in munis:
        m = mascara_do_poligono(reprojetar_aneis(aneis_do_geojson(geo), 4326, epsg), xs, ys)
        if not m.any():
            continue
        linhas.append({"code": cod, "name": nome, "uf": uf,
                       "flood_km2": round(float((m & (classes == cheia_cls)).sum() * area_px / 1e6), 3),
                       "flooded_vegetation_km2": round(float((m & (classes == veg_cls)).sum() * area_px / 1e6), 3),
                       "km2_in_area": round(float(m.sum() * area_px / 1e6), 2)})
    return linhas


def rodar(ctx, extras, progresso, obter=obter_json):
    from . import cheia
    mc = extras.get("mascaras_cheia")
    if not mc:
        return
    if ctx["spec"].get("exposure") is False:
        extras["municipios"] = {"status": "unavailable", "reason": "cruzamento com municípios desligado no pedido"}
        return
    progresso("exposure", 0.86, "cruzando a cheia com os municípios do IBGE")
    pico = mc["peak"]
    try:
        munis = municipios_na_area(ctx["aoi"], obter)
    except Exception as e:  # noqa: BLE001
        extras["municipios"] = {"status": "unavailable", "reason": f"malhas do IBGE indisponíveis ({type(e).__name__})"}
        return
    if not munis:
        extras["municipios"] = {"status": "unavailable", "reason": "área fora do Brasil: sem malha municipal do IBGE"}
        return
    linhas = contar(mc["classes"][pico], munis, ctx["xs"], ctx["ys"], ctx["epsg"], ctx["area_px"],
                    cheia.CHEIA, cheia.VEGETACAO)
    try:
        pop = populacao([x["code"] for x in linhas], obter)
    except Exception:  # noqa: BLE001
        pop, linhas_nota = {}, "população indisponível agora (API do IBGE)"
    else:
        linhas_nota = None
    for x in linhas:
        x["population_2022"] = pop.get(x["code"])
    linhas.sort(key=lambda x: -(x["flood_km2"] + x["flooded_vegetation_km2"]))
    extras["municipios"] = {"status": "ok", "date": ctx["datas"][pico]["date"], "source": "IBGE (malhas v3, Censo 2022)",
                            "note": NOTA, "municipalities": linhas, **({"warning": linhas_nota} if linhas_nota else {})}
