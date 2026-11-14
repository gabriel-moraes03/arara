"""Catálogo NISAR GCOV (ASF DAAC): busca, normalização das cenas e escolha do grupo de geometria.

A busca é pública (não usa credencial). Uma análise usa UMA coleção e UMA geometria: as cenas são
agrupadas por (coleção, trilha, direção, frame) e nunca se misturam PROVISIONAL, VALIDATED e BETA.
"""
from collections import defaultdict

from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

COBERTURA_MINIMA = 0.95
ASF_URL = "https://api.daac.asf.alaska.edu/services/search/param"


def maturidade(colecao):
    """NISAR_L2_GCOV_BETA_V1 -> BETA; ..._PROVISIONAL_V1 -> PROVISIONAL; NISAR_L2_GCOV_V1 -> VALIDATED."""
    c = (colecao or "").upper()
    if "BETA" in c:
        return "BETA"
    if "PROVISIONAL" in c:
        return "PROVISIONAL"
    return "VALIDATED" if c else "UNKNOWN"


def cena_de_feature(feature):
    """Feature GeoJSON da ASF Search API -> registro de cena do Arara."""
    p = feature["properties"]
    nome = p.get("sceneName") or p.get("fileID")
    campos = nome.split("_")
    arquivo = p.get("fileName") or nome + ".h5"
    tamanho = None
    if isinstance(p.get("bytes"), dict):
        tamanho = (p["bytes"].get(arquivo) or {}).get("bytes")
    elif p.get("bytes") is not None:
        tamanho = int(p["bytes"])
    direcao = (p.get("flightDirection") or "")[:1].upper() or None
    return {
        "granule": nome,
        "collection": p.get("collectionName"),
        "maturity": maturidade(p.get("collectionName")),
        "crid": p.get("crid"),
        "start_time": p.get("startTime"),
        "stop_time": p.get("stopTime"),
        "date": (p.get("startTime") or "")[:10],
        "track": p.get("pathNumber"),
        "direction": direcao,
        "frame": p.get("frameNumber"),
        "mode": campos[8] if len(campos) > 9 else None,          # ex.: 2005
        "pol_code": campos[9] if len(campos) > 9 else None,      # ex.: DHDH (HH+HV), SHSH (só HH)
        "polarizations": p.get("mainBandPolarization") or [],
        "frequency": "A",
        "range_bandwidth": p.get("rangeBandwidth"),
        "frame_coverage": p.get("frameCoverage"),
        "processing_date": p.get("processingDate"),
        "pge_version": p.get("pgeVersion"),
        "footprint": feature.get("geometry"),
        "url": p.get("url"),
        "size_bytes": tamanho,
        "md5": p.get("md5sum"),
        "concept_id": p.get("conceptID"),
    }


def geometria(aoi):
    """Aceita shapely, GeoJSON (geometry/Feature) ou bbox [oeste, sul, leste, norte]."""
    if isinstance(aoi, BaseGeometry):
        return aoi
    if isinstance(aoi, (list, tuple)) and len(aoi) == 4:
        return box(*aoi)
    if aoi.get("type") == "Feature":
        aoi = aoi["geometry"]
    if aoi.get("type") == "FeatureCollection":
        aoi = aoi["features"][0]["geometry"]
    return shape(aoi)


def buscar(aoi, inicio=None, fim=None, maturity=None, max_resultados=1000):
    """Consulta ao vivo (asf_search). Devolve as cenas normalizadas, da mais antiga para a mais nova."""
    import asf_search as asf
    geom = geometria(aoi)
    opcoes = dict(dataset="NISAR", processingLevel="GCOV", intersectsWith=geom.wkt, maxResults=max_resultados)
    if inicio:
        opcoes["start"] = inicio
    if fim:
        opcoes["end"] = fim
    resultados = asf.search(**opcoes)
    cenas = [cena_de_feature(r.geojson()) for r in resultados]
    if maturity:
        cenas = [c for c in cenas if c["maturity"] == maturity.upper()]
    return sorted(cenas, key=lambda c: c["start_time"] or "")


def cobertura(cena, geom):
    """Fração da AOI dentro do footprint da cena (graus; suficiente para uma razão de áreas local)."""
    if not cena.get("footprint") or geom.area == 0:
        return 0.0
    return float(shape(cena["footprint"]).intersection(geom).area / geom.area)


def chave_grupo(cena):
    return (cena["collection"], cena["track"], cena["direction"], cena["frame"])


def agrupar(cenas, aoi):
    """Grupos de geometria (coleção, trilha, direção, frame), do melhor para o pior.
    Em cada grupo fica uma cena por data: a de processamento mais recente."""
    geom = geometria(aoi)
    por_grupo = defaultdict(dict)
    for c in cenas:
        atual = por_grupo[chave_grupo(c)].get(c["date"])
        if atual is None or (c["processing_date"] or "") > (atual["processing_date"] or ""):
            por_grupo[chave_grupo(c)][c["date"]] = c
    grupos = []
    for (colecao, trilha, direcao, frame), por_data in por_grupo.items():
        lista = [por_data[d] for d in sorted(por_data)]
        cob = [cobertura(c, geom) for c in lista]
        grupos.append({
            "id": f"{colecao}|{trilha}|{direcao}|{frame}",
            "collection": colecao, "maturity": maturidade(colecao),
            "track": trilha, "direction": direcao, "frame": frame,
            "n_dates": len(lista), "dates": [c["date"] for c in lista],
            "first_date": lista[0]["date"], "last_date": lista[-1]["date"],
            "aoi_coverage": round(min(cob), 4),
            "crids": sorted({c["crid"] for c in lista if c["crid"]}),
            "modes": sorted({c["mode"] for c in lista if c["mode"]}),
            "polarizations": sorted({p for c in lista for p in c["polarizations"]}),
            "dates_with_hv": sum("HV" in c["polarizations"] for c in lista),
            "eligible": min(cob) >= COBERTURA_MINIMA,
            "scenes": lista,
        })
    return sorted(grupos, key=lambda g: (not g["eligible"], -g["n_dates"], -g["dates_with_hv"], -g["aoi_coverage"], g["id"]))


def escolher(grupos, grupo_id=None):
    """O grupo pedido pelo usuário, ou o elegível (cobertura >= 95%) com mais datas.
    Devolve (grupo ou None, motivo): sem grupo elegível a resposta é 'unavailable', nunca um palpite."""
    if grupo_id:
        g = next((g for g in grupos if g["id"] == grupo_id), None)
        if g is None:
            return None, f"grupo de geometria '{grupo_id}' não existe para esta área e período"
        if not g["eligible"]:
            return None, (f"o grupo {grupo_id} cobre {g['aoi_coverage']:.0%} da área; "
                          f"o mínimo é {COBERTURA_MINIMA:.0%}")
        return g, None
    if not grupos:
        return None, "nenhuma cena NISAR GCOV intersecta a área no período"
    if not grupos[0]["eligible"]:
        melhor = max(g["aoi_coverage"] for g in grupos)
        return None, (f"nenhuma geometria cobre {COBERTURA_MINIMA:.0%} da área "
                      f"(a melhor cobre {melhor:.0%}); reduza ou desloque a área")
    return grupos[0], None


def limitar(cenas, maximo):
    """No máximo `maximo` cenas, mantendo a primeira, a última e as demais bem espaçadas no tempo."""
    if len(cenas) <= maximo:
        return list(cenas)
    idx = sorted({round(i * (len(cenas) - 1) / (maximo - 1)) for i in range(maximo)})
    return [cenas[i] for i in idx]
