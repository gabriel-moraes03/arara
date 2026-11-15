"""Sentinel-2 L2A (Earth Search / AWS, público) como referência óptica independente: MNDWI > 0.

Lê só a janela da grade do radar, direto dos COGs. O Sentinel-2 é referência, não verdade:
nuvem, sombra e data diferente entram como limitação declarada.
"""
import datetime

import numpy as np

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
COLECAO = "sentinel-2-l2a"
JANELA_DIAS = 7
SCL_INVALIDO = (0, 1, 3, 8, 9, 10, 11)   # sem dado, saturado, sombra de nuvem, nuvens, cirrus, neve
CLARO_MINIMO = 0.60                      # fração mínima da AOI sem nuvem para a cena servir
OFFSET_BOA = -1000


def buscar(aoi_geojson, data, janela_dias=JANELA_DIAS, sessao=None):
    """Itens STAC a até ±janela_dias da data (AAAA-MM-DD)."""
    import requests
    d = datetime.date.fromisoformat(data)
    intervalo = (f"{d - datetime.timedelta(days=janela_dias)}T00:00:00Z/"
                 f"{d + datetime.timedelta(days=janela_dias)}T23:59:59Z")
    corpo = {"collections": [COLECAO], "intersects": aoi_geojson, "datetime": intervalo, "limit": 100}
    r = (sessao or requests).post(STAC_URL, json=corpo, timeout=60)
    r.raise_for_status()
    return r.json()["features"]


def candidatos(itens, data):
    """Agrupa os itens por dia (um dia pode ter vários tiles MGRS) e ordena: mais perto da data do
    radar primeiro; no empate, menos nuvem; dias quase todos nublados por último. Devolve [(dia, dias_de_diferenca, [itens])]."""
    alvo = datetime.date.fromisoformat(data)
    por_dia = {}
    for it in itens:
        por_dia.setdefault(it["properties"]["datetime"][:10], []).append(it)
    saida = []
    for dia, lista in por_dia.items():
        nuvem = float(np.mean([i["properties"].get("eo:cloud_cover", 100) for i in lista]))
        saida.append((abs((datetime.date.fromisoformat(dia) - alvo).days), nuvem, dia, lista))
    # dia com o tile quase todo nublado (>= 90%) só é tentado depois dos outros
    saida.sort(key=lambda t: (t[1] >= 90, t[0], t[1], t[2]))
    return [(dia, dias, lista) for dias, _, dia, lista in saida]


def offset_do_item(item):
    """Offset a somar ao número digital. Baseline >= 04.00 tem +1000 embutido, mas os COGs do Earth
    Search já vêm corrigidos quando 'earthsearch:boa_offset_applied' é verdadeiro (conferido nos
    dados: água com B11 ~ 90 DN). Corrigir de novo zeraria a água."""
    p = item["properties"]
    try:
        baseline = float(p.get("s2:processing_baseline") or 0)
    except ValueError:
        baseline = 0.0
    if baseline >= 4.0 and not p.get("earthsearch:boa_offset_applied", False):
        return OFFSET_BOA
    return 0


def agua_mndwi(verde, swir, scl, offset=0):
    """(água, válido): MNDWI = (B03 - B11) / (B03 + B11) > 0, fora das classes SCL inválidas."""
    g = verde.astype("float32") + offset
    s = swir.astype("float32") + offset
    valido = (verde > 0) & (swir > 0) & ~np.isin(scl, SCL_INVALIDO) & (g + s > 0)
    mndwi = np.full(g.shape, np.nan, "float32")
    mndwi[valido] = (g[valido] - s[valido]) / (g[valido] + s[valido])
    return (mndwi > 0) & valido, valido, mndwi


def ler_na_grade(item, xs, ys, epsg):
    """B03, B11 e SCL do item reamostrados para a grade do radar (xs, ys = centros dos pixels)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT
    dx, dy = float(xs[1] - xs[0]), float(ys[1] - ys[0])
    inverter = dy > 0
    y_topo = float(ys[-1] if inverter else ys[0])
    transf = from_origin(float(xs[0]) - dx / 2, y_topo + abs(dy) / 2, dx, abs(dy))
    bandas = {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES",
                      GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2", GDAL_HTTP_TIMEOUT="60"):
        for chave, metodo in (("green", Resampling.average), ("swir16", Resampling.bilinear), ("scl", Resampling.nearest)):
            with rasterio.open(item["assets"][chave]["href"]) as src, \
                    WarpedVRT(src, crs=f"EPSG:{epsg}", transform=transf, width=len(xs), height=len(ys),
                              resampling=metodo) as vrt:
                a = vrt.read(1)
            bandas[chave] = a[::-1] if inverter else a
    return bandas["green"], bandas["swir16"], bandas["scl"]


def agua_do_dia(itens, xs, ys, epsg, ler=ler_na_grade):
    """Mosaico dos tiles do dia na grade do radar -> (água, válido, mndwi)."""
    agua = np.zeros((len(ys), len(xs)), bool)
    valido = np.zeros_like(agua)
    mndwi = np.full(agua.shape, np.nan, "float32")
    for it in itens:
        a, v, m = agua_mndwi(*ler(it, xs, ys, epsg), offset=offset_do_item(it))
        novo = v & ~valido
        agua[novo], mndwi[novo] = a[novo], m[novo]
        valido |= v
    return agua, valido, mndwi


def referencia(aoi_geojson, data, xs, ys, epsg, aoi_mask, max_tentativas=3, itens=None, ler=ler_na_grade):
    """Melhor cena óptica perto da data: a primeira (por proximidade) com >= 60% da AOI sem nuvem.
    Devolve dict com water/valid/metadados, ou {"status": "not_optically_validated", "reason"}."""
    itens = buscar(aoi_geojson, data) if itens is None else itens
    if not itens:
        return {"status": "not_optically_validated", "reason": f"nenhuma cena Sentinel-2 a ±{JANELA_DIAS} dias de {data}"}
    melhor = None
    for dia, dias, lista in candidatos(itens, data)[:max_tentativas]:
        agua, valido, _ = agua_do_dia(lista, xs, ys, epsg, ler)
        claro = float((valido & aoi_mask).sum() / max(1, aoi_mask.sum()))
        atual = {"status": "ok", "water": agua, "valid": valido, "date": dia, "days_apart": dias,
                 "clear_fraction": round(claro, 4), "items": [i["id"] for i in lista],
                 "cloud_cover_pct": [round(float(i["properties"].get("eo:cloud_cover", -1)), 2) for i in lista],
                 "processing_baseline": sorted({str(i["properties"].get("s2:processing_baseline")) for i in lista}),
                 "boa_offset_added": [offset_do_item(i) for i in lista],
                 "assets": {k: lista[0]["assets"][k]["href"] for k in ("green", "swir16", "scl")}}
        if claro >= CLARO_MINIMO:
            return atual
        if melhor is None or claro > melhor["clear_fraction"]:
            melhor = atual
    return {"status": "not_optically_validated", "date": melhor["date"], "clear_fraction": melhor["clear_fraction"],
            "reason": (f"Sentinel-2 com nuvem: a melhor cena a ±{JANELA_DIAS} dias de {data} ({melhor['date']}) "
                       f"tem só {melhor['clear_fraction']:.0%} da área sem nuvem")}
