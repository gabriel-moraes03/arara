"""
Estudo Barra Grande + Machadinho (rio Pelotas/Uruguai, RS/SC) com o método validado em Furnas.

    python pipeline/scripts/estudo_uruguai.py --h5 <pasta dos 7 .h5 da trilha 053 D frame 102>

Método (o mesmo de Furnas): HH em potência linear -> dB uma vez -> média 5x5 em dB (pixel de 40 m) ->
UM limiar para a série inteira, no vale água/terra dos blocos de margem de todas as datas e dos dois
reservatórios -> água só dentro do polígono oficial da ANA, sem buffer -> manchas < 0,1 km² fora.
Mask 0 e 255 inválidos. Datas com a água mais clara (suspeita de vento) ficam marcadas, nunca escondidas.

Extra deste estudo (vale encaixado): o GCOV veio sem máscara de sombra, então as encostas com geometria
crítica são estimadas pelo fator RTC gamma0->sigma0 (que depende do ângulo de incidência local) e
mascaradas; a área esperada pela CAV é multiplicada pela fração do polígono que sobra, como em Furnas.

Saídas: regression/barra_machadinho/ (area_agua.csv, cobertura.csv, serie.json, meta.json, metricas.txt)
e frontend/uruguai/data/ (imagens, limites, série e meta da página).
Entradas versionadas: data/ana/{barra_grande,machadinho}_{poligono.geojson,cota_area.csv} e
data/ana/cota_uruguai_ana.csv. Os .h5 não são versionados.
"""
import argparse
import csv
import glob
import json
import os
import sys

import h5py
import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import binary_erosion

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from arara_pipeline.geom import (caixa_do_poligono, km2, ler_poligono_geojson, mascara_do_poligono,  # noqa: E402
                                 tirar_manchas)
from arara_pipeline.publish import (area_anel_km2, escala, grade_mercator, rampa, reamostrar,  # noqa: E402
                                    salvar_mascara, simplificar)
from arara_pipeline.sar import (GRADE, MIN_BLOCOS_MARGEM, PASSO, blocos_de_margem, coordenadas_recorte,  # noqa: E402
                                data_do_nome, epsg_do_h5, identificacao, ler_recorte, otsu, vale)
from arara_pipeline.validate_ana import ler_csv, ler_curva, metricas_ana, serie_ana  # noqa: E402

RESERVATORIOS = {
    "barra_grande": {"nome": "Barra Grande", "ana": "BARRA GRANDE", "codigo_ana": 19067, "rio": "Pelotas",
                     "na_max_normal_m": 647.0, "na_min_normal_m": 617.0, "area_ficha_km2": 90.736,
                     "referencia_cota": "sistema local (coluna A da CAV; a coluna B, SGB, é +0,14 m)",
                     "fonte_poligono": "ANA/SNIRH, Barra Grande.gdb, camada Isóbatas, curva de 647,00 m "
                                       "(a camada Reservatório é a curva de 651,14 m, o máximo maximorum)"},
    "machadinho": {"nome": "Machadinho", "ana": "MACHADINHO", "codigo_ana": 19069, "rio": "Uruguai",
                   "na_max_normal_m": 480.0, "na_min_normal_m": 465.0, "area_ficha_km2": 80.494,
                   "referencia_cota": "cota de operação (coluna A da CAV; a coluna B, SGB, é +0,21 m)",
                   "fonte_poligono": "ANA/SNIRH, Machadinho.gdb, camada Reservatório (linhas a 480,00 m)"},
}
FATOR_RTC_SOMBRA = 0.35     # gamma0->sigma0 abaixo disso: encosta de costas para o radar (perto da sombra)
FATOR_RTC_LAYOVER = 0.93    # acima disso: encosta de frente para o radar (encurtamento/layover)
VENTO_DB = 1.5              # água do núcleo >= 1,5 dB mais clara que a mediana da série: suspeita de vento
LARGURA = 1400              # px das imagens da página (por reservatório)
ESCALA_HH = (-23.0, -2.0)
COR_AGUA = (38, 110, 196)
COR_NOVA = (88, 176, 255)
COR_AGUA_FIXA = (24, 52, 92)
SUBIDA = ("20260629", "20260711")
ERRO_MAX_PCT = 5.0         # acima disso o estudo sai como experimental
COBERTURA_MIN = 0.90


def fator_rtc(arquivo, caixa, passo=PASSO):
    """rtcGammaToSigmaFactor na mesma grade de ler_recorte (depende só da geometria e do DEM)."""
    with h5py.File(arquivo, "r") as h:
        g = h[GRADE]
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        x0, x1, y0, y1 = caixa
        cols = np.where((x >= min(x0, x1)) & (x <= max(x0, x1)))[0]
        rows = np.where((y >= min(y0, y1)) & (y <= max(y0, y1)))[0]
        sombra = h["/science/LSAR/GCOV/metadata/processingInformation/parameters/shadowMaskingApplied"][()]
        return g["rtcGammaToSigmaFactor"][rows[0]:rows[-1] + 1:passo, cols[0]:cols[-1] + 1:passo], sombra.decode()


def r(a, b):
    return round(float(np.corrcoef(a, b)[0, 1]), 2)


def metricas_variante(serie, curva, sel):
    """Erro, ruído, r(cota, área), inclinação e r das variações entre datas consecutivas, nas datas sel."""
    s = [x for x, k in zip(serie, sel) if k]
    dif = np.array([x["diferenca_km2"] for x in s])
    cc = np.array([x["cota_ana_m"] for x in s])
    aa = np.array([x["area_nisar_km2"] for x in s])
    ee = np.array([x["area_esperada_km2"] for x in s])
    faixa = (curva[:, 0] >= cc.min()) & (curva[:, 0] <= cc.max())
    return {"n": len(s), "erro_abs_medio_km2": round(float(np.abs(dif).mean()), 1),
            "erro_abs_medio_pct": round(float(np.mean([abs(x["diferenca_pct"]) for x in s])), 1),
            "vies_km2": round(float(dif.mean()), 1), "ruido_dp_km2": round(float(dif.std(ddof=1)), 1),
            "r_cota_area": r(cc, aa), "inclinacao_nisar_km2_por_m": round(float(np.polyfit(cc, aa, 1)[0]), 2),
            "inclinacao_cav_km2_por_m": round(float(np.polyfit(curva[faixa, 0], curva[faixa, 1], 1)[0]), 2),
            "inclinacao_cav_nas_datas_km2_por_m": round(float(np.polyfit(cc, ee, 1)[0]), 2),
            "r_variacoes": r(np.diff(aa), np.diff(ee)),
            "razao_variacoes": round(float(np.polyfit(np.diff(ee), np.diff(aa), 1)[0]), 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--h5", required=True, help="pasta com os 7 .h5 (053 D 102, modo 2005)")
    ap.add_argument("--ana", default=os.path.join("data", "ana"))
    ap.add_argument("--regressao", default=os.path.join("regression", "barra_machadinho"))
    ap.add_argument("--web", default=os.path.join("frontend", "uruguai", "data"))
    args = ap.parse_args()
    os.makedirs(args.regressao, exist_ok=True)
    os.makedirs(args.web, exist_ok=True)

    arquivos = sorted(glob.glob(os.path.join(args.h5, "*.h5")), key=data_do_nome)
    cenas = [{"data": f"{d[:4]}-{d[4:6]}-{d[6:]}", "arquivo": os.path.basename(a), **identificacao(a)}
             for a, d in ((a, data_do_nome(a)) for a in arquivos)]
    geometria = {(c["trackNumber"], c["orbitPassDirection"], c["frameNumber"]) for c in cenas}
    crids = {c["compositeReleaseId"] for c in cenas}
    if len(geometria) != 1:
        raise SystemExit(f"mais de uma geometria na pasta: {geometria}")
    epsg = epsg_do_h5(arquivos[0])
    datas = [data_do_nome(a) for a in arquivos]
    print(f"{len(arquivos)} cenas, geometria {geometria}, CRID {crids}, EPSG {epsg}")

    # 1ª passada: dB filtrado de cada reservatório e data; blocos de margem de toda a série
    res = {}
    margens = []
    for chave, info in RESERVATORIOS.items():
        aneis = ler_poligono_geojson(os.path.join(args.ana, f"{chave}_poligono.geojson"), epsg)
        caixa = caixa_do_poligono(aneis, 2000)
        xs, ys = coordenadas_recorte(arquivos[0], caixa)
        dentro = mascara_do_poligono(aneis, xs, ys)
        dbs, validos = {}, {}
        for a, d in zip(arquivos, datas):
            db, valido, pixel_m, _ = ler_recorte(a, caixa)
            dbs[d], validos[d] = db, valido
            margens.append(blocos_de_margem(db, valido))
        fator, sombra_aplicada = fator_rtc(arquivos[0], caixa)
        res[chave] = {"aneis": aneis, "caixa": caixa, "xs": xs, "ys": ys, "dentro": dentro, "dbs": dbs,
                      "validos": validos, "pixel_m": pixel_m, "fator": fator}
    margens = np.concatenate([m for m in margens if len(m)])

    # UM limiar para a série inteira: vale dos blocos de margem de todas as datas e dos dois lagos.
    # Conferência registrada: vale e Otsu dos pixels dentro dos polígonos.
    limiar = float(vale(margens.ravel()))
    dentro_todos = np.concatenate([v["dbs"][d][v["validos"][d] & v["dentro"]] for v in res.values() for d in datas])
    conferencia = {"n_blocos_margem": len(margens), "minimo_blocos_metodo": MIN_BLOCOS_MARGEM,
                   "vale_dentro_poligonos_db": round(float(vale(dentro_todos)), 2),
                   "otsu_dentro_poligonos_db": round(float(otsu(dentro_todos)), 2)}
    print(f"limiar da série: {limiar:.2f} dB ({len(margens)} blocos de margem; conferência {conferencia})")

    curvas, series, metricas, cobertura, imagens = {}, {}, {}, {}, {}
    cotas_csv = ler_csv(os.path.join(args.ana, "cota_uruguai_ana.csv"))
    linhas_area = []
    para_ll = Transformer.from_crs(epsg, 4326, always_xy=True)
    for chave, info in RESERVATORIOS.items():
        v = res[chave]
        dentro, px = v["dentro"], v["pixel_m"]
        valido_sempre = np.logical_and.reduce([v["validos"][d] for d in datas])
        encosta = (v["fator"] < FATOR_RTC_SOMBRA) | (v["fator"] > FATOR_RTC_LAYOVER)
        zona = dentro & valido_sempre & ~encosta
        frac_valido = {d: round(float((v["validos"][d] & dentro).sum() / dentro.sum()), 4) for d in datas}
        cob = {"area_poligono_km2": km2(dentro, px),
               "frac_valido_por_data": frac_valido,
               "frac_valido_todas_datas": round(float((dentro & valido_sempre).sum() / dentro.sum()), 4),
               "frac_fora_da_passagem": round(float((dentro & ~valido_sempre).sum() / dentro.sum()), 4),
               "frac_encosta_sombra": round(float((dentro & valido_sempre & (v["fator"] < FATOR_RTC_SOMBRA)).sum()
                                                  / dentro.sum()), 4),
               "frac_encosta_layover": round(float((dentro & valido_sempre & (v["fator"] > FATOR_RTC_LAYOVER)).sum()
                                                   / dentro.sum()), 4),
               "frac_usada": round(float(zona.sum() / dentro.sum()), 4),
               "area_usada_km2": km2(zona, px), "shadow_masking_no_produto": sombra_aplicada}
        cobertura[chave] = cob
        frac = cob["frac_usada"]

        mascaras, sem_encosta = {}, {}
        for d in datas:
            agua_poligono = tirar_manchas((v["dbs"][d] < limiar) & v["validos"][d] & dentro, px)
            mascaras[d] = agua_poligono & zona
            sem_encosta[d] = km2(agua_poligono, px)
        nucleo = binary_erosion(np.logical_and.reduce([mascaras[d] for d in datas]), iterations=3)
        brilho = {d: round(float(np.nanmedian(v["dbs"][d][nucleo])), 2) for d in datas}
        mediana = float(np.median(list(brilho.values())))
        vento = {d for d in datas if brilho[d] >= mediana + VENTO_DB}

        curva = ler_curva(os.path.join(args.ana, f"{chave}_cota_area.csv"))
        curvas[chave] = curva
        cotas = {l["data"].replace("-", ""): {"cota_furnas_m": l["cota_m"], "volume_util_pct": l["volume_util_pct"],
                                              "boletim_ana": l["fonte"]}
                 for l in cotas_csv if l["reservatorio"] == info["ana"]}
        areas = {d: km2(mascaras[d], px) for d in datas}
        # a área esperada é a da CAV na fração do polígono que o radar mede (como em Furnas)
        curva_frac = np.column_stack([curva[:, 0], curva[:, 1] * frac])
        serie = serie_ana(areas, cotas, curva_frac, vento, brilho)
        for s in serie:
            d = s["data"].replace("-", "")
            s["area_cav_poligono_inteiro_km2"] = round(float(np.interp(s["cota_ana_m"], curva[:, 0], curva[:, 1])), 2)
            s["area_nisar_com_encostas_km2"] = sem_encosta[d]
            s["fonte_cota"] = s.pop("boletim_ana")
            s["cobertura_valida_frac"] = frac_valido[d]
        series[chave] = serie
        todas = np.ones(len(serie), bool)
        calmas = np.array([not s["suspeita_vento"] for s in serie])
        metricas[chave] = {"todas": metricas_variante(serie, curva_frac, todas),
                           "sem_vento": metricas_variante(serie, curva_frac, calmas) if calmas.sum() >= 3 else None,
                           "datas_vento": sorted(f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in vento),
                           "resumo_validate_ana": metricas_ana(serie, curva_frac)}
        a0, a1 = mascaras[SUBIDA[0]], mascaras[SUBIDA[1]]
        metricas[chave]["subida"] = {"de": SUBIDA[0], "para": SUBIDA[1],
                                     "agua_nova_km2": km2(a1 & ~a0, px), "agua_perdida_km2": km2(a0 & ~a1, px),
                                     "delta_nisar_km2": round(areas[SUBIDA[1]] - areas[SUBIDA[0]], 2),
                                     "delta_cav_km2": round(float(
                                         np.interp(float(cotas[SUBIDA[1]]["cota_furnas_m"]), curva[:, 0], curva[:, 1] * frac)
                                         - np.interp(float(cotas[SUBIDA[0]]["cota_furnas_m"]), curva[:, 0], curva[:, 1] * frac)), 2)}
        for d in datas:
            linhas_area.append([chave, d, areas[d], sem_encosta[d], round(limiar, 2), brilho[d], d in vento])
        print(f"{info['nome']}: cobertura {cob} | vento {sorted(vento)} | brilho {brilho}")
        for s in serie:
            print(f"  {s['data']} cota {s['cota_ana_m']:.2f} esp {s['area_esperada_km2']:6.1f} "
                  f"nisar {s['area_nisar_km2']:6.2f} Δ {s['diferenca_km2']:+6.1f} ({s['diferenca_pct']:+.1f}%)")

        # imagens da página: HH e água por data, subida 29/06 -> 11/07, limite simplificado
        xs, ys = v["xs"], v["ys"]
        idx, bounds, (w, h) = grade_mercator(xs, ys, epsg, LARGURA)
        imagens[chave] = {"bounds": bounds, "largura": w, "altura": h}
        for d in datas:
            Image.fromarray(rampa(reamostrar(escala(v["dbs"][d], ESCALA_HH), idx, np.nan))).save(
                os.path.join(args.web, f"hh_{chave}_{d}.jpg"), quality=62, optimize=True, progressive=True)
            salvar_mascara(os.path.join(args.web, f"agua_{chave}_{d}.png"), reamostrar(mascaras[d], idx, False), COR_AGUA)
        rgba = np.zeros(a0.shape + (4,), np.uint8)
        rgba[a0 & a1] = (*COR_AGUA_FIXA, 170)
        rgba[~a0 & a1] = (*COR_NOVA, 255)
        Image.fromarray(reamostrar(rgba, idx, 0).astype(np.uint8), "RGBA").quantize(
            colors=4, method=Image.Quantize.FASTOCTREE).save(os.path.join(args.web, f"subida_{chave}.png"), optimize=True)
        linhas = []
        for anel in v["aneis"]:
            if area_anel_km2(anel) < 0.1:
                continue
            s = simplificar(anel, 30.0)
            lon, lat = para_ll.transform(s[:, 0], s[:, 1])
            linhas.append([[round(x, 4), round(y, 4)] for x, y in zip(lon, lat)])
        geo = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {"nome": f"UHE {info['nome']}: limite do reservatório",
                                              "na_max_normal_m": info["na_max_normal_m"], "fonte": info["fonte_poligono"],
                                              "area_poligono_km2": km2(dentro, px)},
            "geometry": {"type": "MultiLineString", "coordinates": linhas}}]}
        with open(os.path.join(args.web, f"limite_{chave}.geojson"), "w", encoding="utf-8") as f:
            json.dump(geo, f, separators=(",", ":"), ensure_ascii=False)

    with open(os.path.join(args.regressao, "area_agua.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["reservatorio", "data", "area_km2", "area_com_encostas_km2", "limiar_db", "brilho_agua_hh_db",
                    "suspeita_vento"])
        w.writerows(linhas_area)

    meta = {
        "projeto": "Arara (caso Barra Grande + Machadinho)", "licenca": "MIT",
        "colecao": "NISAR_L2_GCOV_PROVISIONAL_V1", "arquivo_daac": "ASF DAAC",
        "trilha": cenas[0]["trackNumber"], "direcao": "D", "frame": cenas[0]["frameNumber"], "modo": "2005",
        "banda": "L", "polarizacoes": ["HH", "HV"], "crid": sorted(crids),
        "pixel_original_m": 20, "pixel_processado_m": res["barra_grande"]["pixel_m"], "epsg_original": epsg,
        "datas": [c["data"] for c in cenas],
        "metodo": {"canal": "HH", "filtro": "média 5x5 em dB", "limiar_db": round(limiar, 2),
                   "limiar_origem": "vale água/terra dos blocos de margem das 7 datas e dos 2 reservatórios",
                   "limiar_conferencia": conferencia, "mesmo_limiar_todas_datas": True,
                   "contagem": "só dentro do polígono oficial da ANA, sem buffer", "mancha_minima_km2": 0.1,
                   "encostas": {"criterio": "fator RTC gamma0->sigma0 fora de "
                                            f"[{FATOR_RTC_SOMBRA}, {FATOR_RTC_LAYOVER}]", "mascaradas": True},
                   "vento": f"mediana do HH no núcleo de água >= {VENTO_DB} dB acima da mediana da série"},
        "reservatorios": {k: {**RESERVATORIOS[k], "cobertura": cobertura[k], "imagem": imagens[k],
                              "datas_suspeita_vento": metricas[k]["datas_vento"],
                              "curva_cav": [[round(float(c), 2), round(float(a), 2)] for c, a in curvas[k]
                                            if RESERVATORIOS[k]["na_min_normal_m"] + 8 <= c <= RESERVATORIOS[k]["na_max_normal_m"]
                                            and round(c * 100) % 50 == 0]}
                          for k in RESERVATORIOS},
        "cenas": cenas,
        "fontes": {"nisar": "https://nisar-docs.asf.alaska.edu/",
                   "ana_sar": "https://www.ana.gov.br/sar/sin/ (MedicaoSin, reservatórios 19067 e 19069)",
                   "ana_cav": "ANA/SNIRH, pacotes 'Cota x Área x Volume dos Reservatórios de UHEs' (Barra Grande, Machadinho)"},
    }
    with open(os.path.join(args.regressao, "cobertura.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["reservatorio", "area_poligono_km2", "frac_valido_todas_datas", "frac_fora_da_passagem",
                    "frac_encosta_sombra", "frac_encosta_layover", "frac_usada", "area_usada_km2"])
        for k, c in cobertura.items():
            w.writerow([k, c["area_poligono_km2"], c["frac_valido_todas_datas"], c["frac_fora_da_passagem"],
                        c["frac_encosta_sombra"], c["frac_encosta_layover"], c["frac_usada"], c["area_usada_km2"]])
    # rótulo honesto: erro médio > 5% ou cobertura válida < 90% em qualquer reservatório = experimental
    motivos = []
    for k, m in metricas.items():
        v = m["sem_vento"] or m["todas"]
        if v["erro_abs_medio_pct"] > ERRO_MAX_PCT:
            motivos.append(f"{RESERVATORIOS[k]['nome']}: erro absoluto médio de {v['erro_abs_medio_pct']}% "
                           f"(viés {v['vies_km2']:+} km², NISAR abaixo da CAV em todas as datas)")
        if cobertura[k]["frac_valido_todas_datas"] < COBERTURA_MIN:
            motivos.append(f"{RESERVATORIOS[k]['nome']}: cobertura válida de {cobertura[k]['frac_valido_todas_datas']:.0%}")
    meta["rotulo"] = {"status": "experimental" if motivos else "validado", "motivos": motivos,
                      "criterio": f"erro absoluto médio <= {ERRO_MAX_PCT}% e cobertura válida >= {COBERTURA_MIN:.0%}"}
    for pasta in (args.regressao, args.web):
        with open(os.path.join(pasta, "serie.json"), "w", encoding="utf-8") as f:
            json.dump(series, f, indent=1, ensure_ascii=False)
        with open(os.path.join(pasta, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({**meta, "metricas": metricas}, f, indent=1, ensure_ascii=False)
    print(json.dumps(metricas, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
