"""Orquestrador de uma análise: python -m arara_pipeline.run --spec spec.json --out <dir>

Progresso em JSON Lines no stdout ({"stage","progress","message"}); o resultado fica em
<out>/result.json com status completed | unavailable | failed. Nada é simulado: sem acesso,
cobertura ou cenas válidas, o status é "unavailable" com o motivo.

spec.json: {"analysis_id", "aoi": <GeoJSON>, "start", "end", "group_id"?, "maturity"?,
            "max_scenes"?, "params": {"step"?, "filter"?, "threshold_db"?},
            "local_scenes"?: [caminhos .h5 já no disco, mesma geometria]}
"""
import argparse
import csv
import datetime
import json
import os
import sys
import traceback

import numpy as np

from . import ALGORITHM_VERSION, catalog_nisar, change, gcov_read, publish, water
from .geom import aneis_do_geojson, mascara_do_poligono, reprojetar_aneis
from .sar import db_filtrado

AOI_MAX_KM2 = float(os.environ.get("ARARA_AOI_MAX_KM2", 2500))
MAX_CENAS = int(os.environ.get("ARARA_MAX_SCENES", 12))
VALIDO_MINIMO = 0.95
ETAPAS = ["discover", "select", "acquire", "process", "classify", "compare", "optical_s2",
          "validate_cross", "forecast", "insights", "publish"]


class Indisponivel(Exception):
    """A análise não pode ser feita com dados reais; o motivo vai para o usuário."""


def progresso(etapa, fracao, mensagem):
    print(json.dumps({"stage": etapa, "progress": round(float(fracao), 3), "message": mensagem},
                     ensure_ascii=False), flush=True)


def agora():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def area_km2(geom):
    from pyproj import Geod
    return abs(Geod(ellps="WGS84").geometry_area_perimeter(geom)[0]) / 1e6


def cenas_locais(caminhos):
    """Cenas já no disco (Furnas e testes): metadados lidos do próprio .h5."""
    import h5py
    cenas = []
    for c in sorted(caminhos):
        with h5py.File(c, "r") as h:
            ident = gcov_read.validar_estrutura(h).get("identification", {})
        nome = os.path.basename(c)[:-3]
        campos = nome.split("_")
        inicio = str(ident.get("zeroDopplerStartTime") or "")
        data = inicio[:10] if inicio else f"{campos[11][:4]}-{campos[11][4:6]}-{campos[11][6:8]}"
        cenas.append({"granule": nome, "collection": None, "maturity": "LOCAL",
                      "crid": ident.get("compositeReleaseId") or (campos[13] if len(campos) > 13 else None),
                      "date": data, "start_time": inicio or data, "track": ident.get("trackNumber"),
                      "direction": str(ident.get("orbitPassDirection") or "")[:1].upper() or None,
                      "frame": ident.get("frameNumber"), "url": c, "local": True, "size_bytes": os.path.getsize(c)})
    geometrias = {(c["track"], c["direction"], c["frame"]) for c in cenas}
    if len(geometrias) > 1:
        raise Indisponivel(f"as cenas locais misturam geometrias (trilha, direção, frame): {sorted(map(str, geometrias))}")
    return cenas


def alinhar(janelas):
    """Recorta todas as janelas para a grade comum (mesma origem e passo; só desloca inteiros)."""
    ref = janelas[0]
    dx, dy = ref["xs"][1] - ref["xs"][0], ref["ys"][1] - ref["ys"][0]
    x_a = max(j["xs"][0] if dx > 0 else -j["xs"][0] for j in janelas) * (1 if dx > 0 else -1)
    x_b = min(j["xs"][-1] if dx > 0 else -j["xs"][-1] for j in janelas) * (1 if dx > 0 else -1)
    y_a = max(j["ys"][0] if dy > 0 else -j["ys"][0] for j in janelas) * (1 if dy > 0 else -1)
    y_b = min(j["ys"][-1] if dy > 0 else -j["ys"][-1] for j in janelas) * (1 if dy > 0 else -1)
    nx, ny = int(round((x_b - x_a) / dx)) + 1, int(round((y_b - y_a) / dy)) + 1
    if nx < 2 or ny < 2:
        raise Indisponivel("as cenas não têm área em comum sobre a AOI")
    fatias = []
    for j in janelas:
        c0, r0 = (x_a - j["xs"][0]) / dx, (y_a - j["ys"][0]) / dy
        if abs(c0 - round(c0)) > 0.01 or abs(r0 - round(r0)) > 0.01:
            raise Indisponivel("as cenas não estão na mesma grade (frames ou versões diferentes)")
        fatias.append((slice(int(round(r0)), int(round(r0)) + ny), slice(int(round(c0)), int(round(c0)) + nx)))
    return x_a + dx * np.arange(nx), y_a + dy * np.arange(ny), fatias


def executar(spec, saida):
    os.makedirs(saida, exist_ok=True)
    from shapely.geometry import mapping
    aoi = catalog_nisar.geometria(spec["aoi"])
    if aoi.is_empty or not aoi.is_valid:
        raise Indisponivel("a geometria da área é inválida")
    km2_aoi = area_km2(aoi)
    if km2_aoi > AOI_MAX_KM2:
        raise Indisponivel(f"área de {km2_aoi:,.0f} km² acima do limite de {AOI_MAX_KM2:,.0f} km²; desenhe uma área menor")
    params = spec.get("params") or {}
    passo = int(params.get("step", 1))
    filtro = params.get("filter", "db")
    maximo = min(int(spec.get("max_scenes") or MAX_CENAS), MAX_CENAS)
    avisos, puladas = [], []

    # ---- discover + select ----
    if spec.get("local_scenes"):
        progresso("discover", 0.02, "cenas locais (sem consulta ao catálogo)")
        cenas = cenas_locais(spec["local_scenes"])
        grupo = {"id": "local", "collection": None, "maturity": "LOCAL", "track": cenas[0]["track"],
                 "direction": cenas[0]["direction"], "frame": cenas[0]["frame"]}
    else:
        progresso("discover", 0.02, "consultando o catálogo NISAR (ASF)")
        try:
            todas = catalog_nisar.buscar(aoi, spec.get("start"), spec.get("end"), spec.get("maturity"))
        except Exception as e:  # noqa: BLE001
            raise Indisponivel(f"catálogo ASF indisponível: {type(e).__name__}: {e}") from e
        progresso("select", 0.05, f"{len(todas)} cenas encontradas; escolhendo uma geometria")
        escolhido, motivo = catalog_nisar.escolher(catalog_nisar.agrupar(todas, aoi), spec.get("group_id"))
        if escolhido is None:
            raise Indisponivel(motivo)
        cenas = escolhido["scenes"]
        grupo = {k: escolhido[k] for k in ("id", "collection", "maturity", "track", "direction", "frame", "aoi_coverage")}
    if len(cenas) > maximo:
        avisos.append(f"{len(cenas)} datas disponíveis; usadas {maximo} (limite por análise), espaçadas no período")
        cenas = catalog_nisar.limitar(cenas, maximo)

    # ---- acquire + validate: só a janela da AOI + 1 km de cada cena ----
    janelas, usadas, caixa, fs = [], [], None, None
    for i, c in enumerate(cenas):
        progresso("acquire", 0.08 + 0.42 * i / len(cenas), f"lendo a janela da cena {i + 1}/{len(cenas)} ({c['date']})")
        try:
            if not c.get("local") and fs is None:
                fs = gcov_read._sessao_earthdata()
            with gcov_read.abrir(c["url"], fs) as h:
                if caixa is None:
                    caixa = gcov_read.caixa_da_aoi(aoi, gcov_read.validar_estrutura(h)["epsg"])
                j = gcov_read.ler_janela(h, caixa, passo)
        except gcov_read.CenaInvalida as e:
            puladas.append({"granule": c["granule"], "date": c["date"], "reason": str(e)})
            continue
        except gcov_read.AcessoIndisponivel as e:
            raise Indisponivel(str(e)) from e
        if janelas and j["epsg"] != janelas[0]["epsg"]:
            puladas.append({"granule": c["granule"], "date": c["date"], "reason": "projeção diferente das demais cenas"})
            continue
        janelas.append(j)
        usadas.append(c)
    if not janelas:
        raise Indisponivel("nenhuma cena válida sobre a área: " + "; ".join(p["reason"] for p in puladas))

    # ---- process: grade comum, máscara da AOI, dB (uma vez) com filtro 5x5 ----
    progresso("process", 0.52, "alinhando as cenas e convertendo para dB")
    xs, ys, fatias = alinhar(janelas)
    epsg, pixel_m, area_px = janelas[0]["epsg"], janelas[0]["pixel_m"], janelas[0]["pixel_area_m2"]
    mascara_aoi = mascara_do_poligono(reprojetar_aneis(aneis_do_geojson(mapping(aoi)), 4326, epsg), xs, ys)
    if not mascara_aoi.any():
        raise Indisponivel("a área não cai sobre a grade das cenas")
    dbs, validos, hvs, manter = [], [], [], []
    for j, c, f in zip(janelas, usadas, fatias):
        valido = j["valid"]["HHHH"][f]
        fracao = float((valido & mascara_aoi).sum() / mascara_aoi.sum())
        c["valid_fraction_aoi"] = round(fracao, 4)
        if fracao < VALIDO_MINIMO:
            puladas.append({"granule": c["granule"], "date": c["date"],
                            "reason": f"só {fracao:.0%} da área com dado válido (mínimo {VALIDO_MINIMO:.0%})"})
            continue
        dbs.append(db_filtrado(j["bands"]["HHHH"][f], valido, filtro))
        validos.append(valido)
        hvs.append(db_filtrado(j["bands"]["HVHV"][f], j["valid"]["HVHV"][f], filtro) if "HVHV" in j["bands"] else None)
        manter.append((j, c))
    janelas.clear()                                  # as janelas brutas só existiram em memória
    if not dbs:
        raise Indisponivel("nenhuma cena com dado válido suficiente na área: " + "; ".join(p["reason"] for p in puladas))
    usadas = [c for _, c in manter]
    if any(h is None for h in hvs):
        avisos.append("HV ausente em parte das datas (modo de polarização simples); a água é classificada só com HH")

    # ---- classify ----
    progresso("classify", 0.62, "classificando água (limiar bimodal nos blocos de margem)")
    cls = water.classificar_serie(dbs, validos, mascara_aoi, pixel_m, params.get("threshold_db"))
    datas = []
    for i, c in enumerate(usadas):
        n = int(cls["water"][i].sum())
        datas.append({
            "date": c["date"], "granule": c["granule"], "crid": c["crid"],
            "water_km2": round(n * area_px / 1e6, 3), "water_pct": round(100 * n / cls["n_common"], 3),
            "threshold_db": cls["threshold_db"], "date_threshold_db": cls["per_date_threshold_db"][i],
            "margin_blocks": cls["margin_blocks"][i],
            "hh_water_median_db": None if np.isnan(cls["hh_water_db"][i]) else round(cls["hh_water_db"][i], 2),
            "suspeita_vento": cls["wind"][i], "valid_fraction_aoi": c["valid_fraction_aoi"],
            "has_hv": hvs[i] is not None,
        })
    if any(cls["wind"]):
        avisos.append("datas com suspeita de vento (água mais clara que o normal da série): "
                      + ", ".join(d["date"] for d in datas if d["suspeita_vento"])
                      + "; a área nessas datas tende a sair subestimada e não foi corrigida")

    # ---- compare: primeira x última data ----
    comparacao, classes = None, None
    if len(datas) >= 2:
        progresso("compare", 0.70, f"comparando {datas[0]['date']} com {datas[-1]['date']}")
        classes, m = change.comparar(cls["water"][0], cls["water"][-1], cls["common_valid"], area_px)
        comparacao = {"before": datas[0]["date"], "after": datas[-1]["date"], **m,
                      "wind_caveat": datas[0]["suspeita_vento"] or datas[-1]["suspeita_vento"]}
    else:
        avisos.append("só uma data válida: sem comparação entre datas")

    contexto = {"spec": spec, "aoi": aoi, "xs": xs, "ys": ys, "epsg": epsg, "pixel_m": pixel_m, "area_px": area_px,
                "cls": cls, "datas": datas, "comparacao": comparacao, "saida": saida, "avisos": avisos}
    extras = etapas_opcionais(contexto)

    # ---- publish ----
    progresso("publish", 0.90, "gravando COGs, PNGs, tiles e métricas")
    camadas, rgba = [], {}
    idx, limites = publish.grade_latlon(xs, ys, epsg)
    for sub in ("cog", "png"):
        os.makedirs(os.path.join(saida, sub), exist_ok=True)

    def camada(ident, tipo, data, img, titulo):
        publish.salvar_png(os.path.join(saida, "png", ident + ".png"), img, idx)
        rgba[ident] = img
        camadas.append({"id": ident, "type": tipo, "date": data, "title": titulo, "png": f"png/{ident}.png",
                        "bounds": limites, "tiles": f"tiles/{ident}/{{z}}/{{x}}/{{y}}.png"})

    for i, d in enumerate(datas):
        s = d["date"].replace("-", "")
        publish.salvar_cog(os.path.join(saida, "cog", f"hh_db_{s}.tif"), dbs[i], xs, ys, epsg, nodata=float("nan"))
        if hvs[i] is not None:
            publish.salvar_cog(os.path.join(saida, "cog", f"hv_db_{s}.tif"), hvs[i], xs, ys, epsg, nodata=float("nan"))
        publish.salvar_cog(os.path.join(saida, "cog", f"water_{s}.tif"),
                           np.where(cls["common_valid"], cls["water"][i], 255).astype("uint8"), xs, ys, epsg, nodata=255)
        camada(f"water_{s}", "water", d["date"], publish.rgba_mascara(cls["water"][i]), f"Água em {d['date']}")
    for i in sorted({0, len(datas) - 1}):
        s = datas[i]["date"].replace("-", "")
        camada(f"hh_{s}", "backscatter", datas[i]["date"], publish.rgba_db(dbs[i]), f"Radar HH (dB) em {datas[i]['date']}")
    if classes is not None:
        publish.salvar_cog(os.path.join(saida, "cog", "change.tif"), classes, xs, ys, epsg, nodata=0)
        camada("change", "change", None, publish.rgba_classes(classes),
               f"Mudança {comparacao['before']} → {comparacao['after']}")
    for ident, (tipo, data, img, titulo) in extras.get("camadas", {}).items():
        camada(ident, tipo, data, img, titulo)
    tiles = publish.gerar_tiles(rgba, xs, ys, epsg, os.path.join(saida, "tiles"))
    for c in camadas:
        c["zooms"] = tiles["zooms"]

    with open(os.path.join(saida, "metrics.csv"), "w", newline="", encoding="utf-8") as f:
        colunas = ["date", "water_km2", "water_pct", "threshold_db", "hh_water_median_db", "suspeita_vento",
                   "valid_fraction_aoi", "crid", "granule"]
        w = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
        w.writeheader()
        w.writerows(datas)
    fontes = {
        "generated_at": agora(), "algorithm_version": ALGORITHM_VERSION, "sensor": "NISAR L-band SAR (GCOV L2)",
        "group": grupo, "aoi_window_m": {"epsg": epsg, "x_min": float(min(xs[0], xs[-1])), "x_max": float(max(xs[0], xs[-1])),
                                         "y_min": float(min(ys[0], ys[-1])), "y_max": float(max(ys[0], ys[-1])), "step": passo},
        "scenes": [{"granule": c["granule"], "collection": c.get("collection"), "maturity": c.get("maturity"),
                    "crid": c.get("crid"), "date": c["date"], "start_time": c.get("start_time"),
                    "track": c.get("track"), "direction": c.get("direction"), "frame": c.get("frame"),
                    "url": None if c.get("local") else c.get("url"), "size_bytes": c.get("size_bytes"),
                    "access": j["source"]["access"] if "source" in j else ("local" if c.get("local") else "streaming"),
                    "checksum": "arquivo local, não conferido" if c.get("local") else gcov_read.LIMITACAO_CHECKSUM,
                    "window": j["window"]} for j, c in manter],
        "skipped_scenes": puladas, "optical": extras.get("fontes_opticas"),
        "raw_data_policy": "janelas brutas lidas em memória e descartadas ao fim do job; ficam só os derivados",
    }
    with open(os.path.join(saida, "sources.json"), "w", encoding="utf-8") as f:
        json.dump(fontes, f, ensure_ascii=False, indent=1)
    oeste, sul, leste, norte = aoi.bounds
    resultado = {
        "status": "completed", "analysis_id": spec.get("analysis_id"), "generated_at": agora(),
        "algorithm_version": ALGORITHM_VERSION, "method": "limiar_bimodal", "sensor": "NISAR L-band SAR (GCOV L2), HH",
        "params": {"step": passo, "filter": filtro, "threshold_db": cls["threshold_db"], "threshold": cls["threshold"]},
        "aoi": {"geometry": mapping(aoi), "area_km2": round(km2_aoi, 2), "bbox": [oeste, sul, leste, norte]},
        "group": grupo, "pixel_m": pixel_m, "pixel_area_m2": area_px,
        "experimental": cls["experimental"], "experimental_reasons": cls["experimental_reasons"],
        "dates": datas, "comparison": comparacao, "layers": camadas, "warnings": avisos, "skipped_scenes": puladas,
        "optical_validation": extras.get("validacao", {"status": "not_optically_validated",
                                                       "reason": "validação óptica não executada nesta versão"}),
        "forecast": extras.get("previsao"), "insights": extras.get("insights"),
    }
    with open(os.path.join(saida, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump({k: resultado[k] for k in ("analysis_id", "algorithm_version", "method", "sensor", "params", "group",
                                              "experimental", "experimental_reasons", "dates", "comparison",
                                              "optical_validation", "forecast", "warnings")}, f, ensure_ascii=False, indent=1)
    return resultado


def etapas_opcionais(ctx):
    """Validação óptica, previsão e interpretação: entram quando os módulos existirem; uma falha
    aqui nunca derruba a análise de radar, só é registrada."""
    extras = {}
    for nome in ("optical_stage", "forecast_stage", "insights_stage"):
        try:
            modulo = __import__(f"arara_pipeline.{nome}", fromlist=["rodar"])
        except ImportError:
            continue
        try:
            modulo.rodar(ctx, extras, progresso)
        except Exception as e:  # noqa: BLE001
            ctx["avisos"].append(f"etapa {nome} falhou e foi ignorada: {type(e).__name__}: {e}")
    return extras


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    os.makedirs(a.out, exist_ok=True)
    codigo = 0
    try:
        resultado = executar(spec, a.out)
        progresso("publish", 1.0, "análise concluída")
    except Indisponivel as e:
        resultado = {"status": "unavailable", "analysis_id": spec.get("analysis_id"), "reason": str(e), "generated_at": agora()}
        progresso("unavailable", 1.0, str(e))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        resultado = {"status": "failed", "analysis_id": spec.get("analysis_id"),
                     "reason": f"{type(e).__name__}: {e}", "generated_at": agora()}
        progresso("failed", 1.0, resultado["reason"])
        codigo = 1
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
