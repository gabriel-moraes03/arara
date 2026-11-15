"""
Exporta os dados do método oficial de Furnas para o story map (frontend/furnas/data/).
Linha de comando fina: as funções estão em arara_pipeline (sar, geom, publish, validate_ana).

    python pipeline/scripts/exportar_web.py --poligono <Furnas.gdb | data/ana/furnas_poligono.geojson>

Os .h5 vêm de FURNAS_H5_DIR (ou --h5). Refaz a contagem oficial (HH filtrado < limiar, só dentro do
polígono, sem buffer, sem manchas < 0,1 km²) e confere com regression/furnas/area_agua.csv.
"""
import argparse
import csv
import glob
import json
import os
import sys

import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import binary_erosion, uniform_filter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from arara_pipeline.geom import (caixa_do_poligono, km2, ler_poligono, mascara_do_poligono,  # noqa: E402
                                 tirar_manchas)
from arara_pipeline.publish import (area_anel_km2, escala, grade_mercator, rampa, reamostrar,  # noqa: E402
                                    salvar_mascara, simplificar)
from arara_pipeline.sar import (coordenadas_recorte, data_do_nome, epsg_do_h5, identificacao,  # noqa: E402
                                ler_banda, ler_recorte)
from arara_pipeline.validate_ana import ler_areas, ler_cotas, ler_curva, metricas_ana, serie_ana  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--h5", default=os.environ.get("FURNAS_H5_DIR"), help="pasta dos .h5 (padrão: FURNAS_H5_DIR)")
ap.add_argument("--poligono", required=True, help=".gdb da ANA ou GeoJSON costurado")
ap.add_argument("--oficial", default=os.path.join("regression", "furnas", "area_agua.csv"))
ap.add_argument("--cotas", default=os.path.join("data", "ana", "cota_furnas_ana.csv"))
ap.add_argument("--curva", default=os.path.join("data", "ana", "furnas_cota_area.csv"))
ap.add_argument("--cobertura-funil", type=float, default=None, help="fração do Funil com dado válido (registro)")
ap.add_argument("--saida", default=os.path.join("frontend", "furnas", "data"))
ap.add_argument("--limiar", type=float, default=-15.65)
ap.add_argument("--vento", default="20260907,20261001", help="datas com suspeita de vento (AAAAMMDD)")
ARGS = ap.parse_args()
if not ARGS.h5:
    raise SystemExit("Informe --h5 ou defina FURNAS_H5_DIR.")
PASTA_H5, POLIGONO, SAIDA, LIMIAR_DB = ARGS.h5, ARGS.poligono, ARGS.saida, ARGS.limiar
DATAS_VENTO = set(filter(None, ARGS.vento.split(",")))

LARGURA = 1800              # largura das máscaras (px); todas as camadas têm os mesmos limites
LARGURA_HH = 1400           # HH por data (9 imagens: o que mais pesa)
LARGURA_COR = 1600          # HV e composição
LARGURA_SONDA = 640
ESCALA_HH = (-23.0, -2.0)   # dB -> preto..claro
ESCALA_HV = (-27.0, -9.0)
ESCALA_RAZAO = (3.5, 10.0)  # HH - HV em dB
ESCALA_COR_HH = (-20.0, -3.0)
ESCALA_COR_HV = (-26.0, -9.0)
DB_POR_NIVEL = 0.5          # quantização da sonda
COR_AGUA = (38, 110, 196)
COR_SECOU = (232, 140, 58)
COR_NOVA = (88, 176, 255)
COR_AGUA_FIXA = (24, 52, 92)
HV_VOLUME_DB = -13.0        # HV acima disso: espalhamento de volume forte (copas de árvores, provável)



def main():
    os.makedirs(SAIDA, exist_ok=True)
    arquivos = sorted(glob.glob(os.path.join(PASTA_H5, "*.h5")), key=data_do_nome)
    epsg = epsg_do_h5(arquivos[0])
    aneis = ler_poligono(POLIGONO, epsg)
    caixa = caixa_do_poligono(aneis, 2000)  # igual à rodada oficial com --buffer 0
    oficial = ler_areas(ARGS.oficial)

    xs, ys = coordenadas_recorte(arquivos[0], caixa)
    dentro = mascara_do_poligono(aneis, xs, ys)
    idx, bounds, (w, h) = grade_mercator(xs, ys, epsg, LARGURA)
    idx_hh, _, _ = grade_mercator(xs, ys, epsg, LARGURA_HH)
    idx_cor, _, _ = grade_mercator(xs, ys, epsg, LARGURA_COR)
    idx_sonda, _, (ws, hs) = grade_mercator(xs, ys, epsg, LARGURA_SONDA)
    print(f"recorte {len(xs)} x {len(ys)} px; imagens {w} x {h}; limites {bounds}")

    mascaras, hh_por_data, cenas = {}, {}, []
    for arq in arquivos:
        data = data_do_nome(arq)
        db, valido, pixel_m, _ = ler_recorte(arq, caixa)
        agua = tirar_manchas((db < LIMIAR_DB) & valido & dentro[:db.shape[0], :db.shape[1]], pixel_m)
        area = km2(agua, pixel_m)
        if abs(area - oficial[data]) > 0.05:
            raise SystemExit(f"{data}: área {area} km² difere da oficial {oficial[data]} km²")
        print(f"{data}: {area:8.2f} km² (oficial {oficial[data]:.2f})")
        mascaras[data], hh_por_data[data] = agua, db
        cenas.append({"data": f"{data[:4]}-{data[4:6]}-{data[6:]}", "arquivo": os.path.basename(arq),
                      **identificacao(arq)})
        Image.fromarray(rampa(reamostrar(escala(db, ESCALA_HH), idx_hh, np.nan))).save(
            os.path.join(SAIDA, f"hh_{data}.jpg"), quality=62, optimize=True, progressive=True)
        salvar_mascara(os.path.join(SAIDA, f"agua_{data}.png"), reamostrar(agua, idx, False), COR_AGUA)

    datas = sorted(mascaras)
    d0, d1 = datas[0], datas[-1]

    # HV e composição colorida da primeira data
    hh = hh_por_data[d0]
    hv = ler_banda(arquivos[0], caixa, "HVHV")
    Image.fromarray(rampa(reamostrar(escala(hv, ESCALA_HV), idx_cor, np.nan))).save(
        os.path.join(SAIDA, f"hv_{d0}.jpg"), quality=66, optimize=True, progressive=True)
    cor = np.stack([escala(hh, ESCALA_COR_HH), escala(hv, ESCALA_COR_HV), escala(hh - hv, ESCALA_RAZAO)], -1)
    cor = (np.nan_to_num(cor) ** 0.85 * 255).astype(np.uint8)
    Image.fromarray(reamostrar(cor, idx_cor, 0).astype(np.uint8)).save(
        os.path.join(SAIDA, f"cor_{d0}.jpg"), quality=68, optimize=True, progressive=True)

    # sonda: dB quantizado (DB_POR_NIVEL, a partir de -35 dB) + classe (1 água, 2 HV alto, 3 outra terra)
    q = lambda d: np.clip(np.rint((np.nan_to_num(d, nan=-35.0) + 35.0) / DB_POR_NIVEL), 1, 255).astype(np.uint8)
    classe = np.where(mascaras[d0], 1, np.where(hv > HV_VOLUME_DB, 2, 3)).astype(np.uint8)
    classe[np.isnan(hh)] = 0
    sonda = np.stack([q(hh), q(hv), classe], -1)
    sonda[np.isnan(hh)] = 0
    Image.fromarray(reamostrar(sonda, idx_sonda, 0).astype(np.uint8)).save(os.path.join(SAIDA, "sonda.png"),
                                                                         optimize=True)

    # mudança entre a primeira e a última data
    a, b = mascaras[d0], mascaras[d1]
    rgba = np.zeros(a.shape + (4,), np.uint8)
    rgba[a & b] = (*COR_AGUA_FIXA, 170)
    rgba[a & ~b] = (*COR_SECOU, 255)
    rgba[~a & b] = (*COR_NOVA, 255)
    Image.fromarray(reamostrar(rgba, idx, 0).astype(np.uint8), "RGBA").quantize(
        colors=4, method=Image.Quantize.FASTOCTREE).save(os.path.join(SAIDA, "mudanca.png"), optimize=True)

    # foco da mudança: janela de ~8 km com mais área que deixou de ser água (para o zoom do site)
    dens = uniform_filter((a & ~b).astype(np.float32), size=201)
    fl, fc = np.unravel_index(np.argmax(dens), dens.shape)
    foco_lon, foco_lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(xs[fc], ys[fl])

    # brilho da água: mediana do HH nos pixels que são água em todas as datas calmas (sem as bordas)
    calmas = [d for d in datas if d not in DATAS_VENTO]
    nucleo = binary_erosion(np.logical_and.reduce([mascaras[d] for d in calmas]), iterations=3)
    brilho = {d: round(float(np.nanmedian(hh_por_data[d][nucleo])), 2) for d in datas}

    # limite da ANA em lat/lon, simplificado (tolerância 40 m), sem ilhotas < 0,1 km²
    para_ll = Transformer.from_crs(epsg, 4326, always_xy=True)
    linhas = []
    for anel in aneis:
        if area_anel_km2(anel) < 0.1:
            continue
        s = simplificar(anel, 40.0)
        lon, lat = para_ll.transform(s[:, 0], s[:, 1])
        linhas.append([[round(x, 4), round(y, 4)] for x, y in zip(lon, lat)])
    geo = {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "properties": {"nome": "UHE Furnas: limite do reservatório", "cota_operacao_m": 768.0,
                       "fonte": "ANA/SNIRH, Furnas.gdb, camada Reservatório (linhas)",
                       "area_poligono_km2": km2(dentro, pixel_m)},
        "geometry": {"type": "MultiLineString", "coordinates": linhas}}]}
    with open(os.path.join(SAIDA, "limite_furnas.geojson"), "w", encoding="utf-8") as f:
        json.dump(geo, f, separators=(",", ":"), ensure_ascii=False)

    # série e métricas: cota e curva ANA x NISAR (arara_pipeline.validate_ana)
    curva = ler_curva(ARGS.curva)
    serie = serie_ana(oficial, ler_cotas(ARGS.cotas), curva, DATAS_VENTO, brilho)
    with open(os.path.join(SAIDA, "serie.json"), "w", encoding="utf-8") as f:
        json.dump(serie, f, indent=1, ensure_ascii=False)
    metricas = metricas_ana(serie, curva)
    todas_c = np.array([s["cota_ana_m"] for s in serie])
    m_px = pixel_m
    meta = {
        "projeto": "Arara (caso Furnas)", "licenca": "MIT",
        "colecao": "NISAR_L2_GCOV_PROVISIONAL_V1", "arquivo_daac": "ASF DAAC",
        "trilha": 24, "direcao": "D", "frame": 99, "modo": "2005", "banda": "L", "polarizacoes": ["HH", "HV"],
        "pixel_original_m": 20, "pixel_processado_m": m_px,
        "epsg_original": epsg,
        "metodo": {"canal": "HH", "filtro": "média 5x5 em dB", "limiar_db": LIMIAR_DB,
                   "contagem": "só dentro do polígono oficial da ANA, sem buffer",
                   "mancha_minima_km2": 0.1, "mesmo_limiar_todas_datas": True},
        "poligono": {"fonte": "ANA/SNIRH, Furnas.gdb, camada Reservatório", "cota_operacao_m": 768.0,
                     "area_km2": km2(dentro, pixel_m), "area_ficha_ana_km2": 1332.14},
        "cobertura": {"furnas_frac": 1.0, "funil_frac": ARGS.cobertura_funil},
        "datas_suspeita_vento": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in sorted(DATAS_VENTO)],
        "mudanca": {"antes": serie[0]["data"], "depois": serie[-1]["data"],
                    "secou_km2": km2(a & ~b, pixel_m), "agua_nova_km2": km2(~a & b, pixel_m),
                    "foco_latlon": [round(foco_lat, 4), round(foco_lon, 4)]},
        "metricas": metricas,
        "cota_max_normal_m": 768.0,
        "curva_ana": [[round(float(c), 2), round(float(ar), 1)] for c, ar in curva
                      if todas_c.min() - 0.3 <= c <= todas_c.max() + 0.3 and round(c * 100) % 5 == 0],
        "camadas": {"escala_hh_db": ESCALA_HH, "escala_hv_db": ESCALA_HV, "escala_razao_db": ESCALA_RAZAO,
                    "hv_volume_db": HV_VOLUME_DB, "data_polarizacoes": serie[0]["data"],
                    "sonda": {"largura": ws, "altura": hs, "db_min": -35.0, "db_por_nivel": DB_POR_NIVEL}},
        "cenas": cenas,
        "fontes": {
            "nisar": "https://nisar-docs.asf.alaska.edu/",
            "ana_boletins": "https://www.gov.br/ana/pt-br/sala-de-situacao/sistemas-hidricos-dos-rios-grande-e-paranaiba",
            "ana_cav": "https://metadados.snirh.gov.br/geonetwork/srv/api/records/b8f0487a-df73-4f8d-8b22-bb49cf9f3683",
        },
    }
    with open(os.path.join(SAIDA, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    with open(os.path.join(SAIDA, "bounds.json"), "w", encoding="utf-8") as f:
        json.dump({"bounds": bounds, "largura": w, "altura": h, "grade": "EPSG:3857 (limites em EPSG:4326)"}, f, indent=1)
    print(json.dumps(metricas, indent=1, ensure_ascii=False))
    print("brilho da água:", brilho)


if __name__ == "__main__":
    main()
