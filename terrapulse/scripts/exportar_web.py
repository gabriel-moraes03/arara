"""
Exporta os dados do método oficial para o app estático em web/data/.

Refaz, a partir dos .h5, a contagem oficial (HH filtrado < -15,65 dB, só dentro do polígono da ANA,
sem buffer, sem manchas < 0,1 km²), confere as áreas com outputs/furnas_poligono_b0/area_agua.csv e
grava imagens já reamostradas para a grade do Leaflet (Web Mercator, limites em lat/lon).

Rodar (da raiz):
    python scripts/exportar_web.py

Gera, em web/data/:
    serie.json              uma linha por data: cota, área esperada (curva ANA), área NISAR, deltas, flag de vento
    meta.json               cenas, método, métricas (calculadas aqui), cobertura, fontes
    bounds.json             [[lat_sul, lon_oeste], [lat_norte, lon_leste]] e tamanho das imagens
    limite_furnas.geojson   limite oficial da ANA (linhas na cota 768,0 m de operação), simplificado
    hh_AAAAMMDD.jpg         HH em dB (escala fixa), uma por data
    agua_AAAAMMDD.png       máscara de água oficial de cada data (azul, transparente fora)
    hv_20260627.jpg, cor_20260627.jpg   HV e composição (R=HH, G=HV, B=HH-HV) da primeira data
    mudanca.png             27/06 x 13/10: ocre = secou, azul = água nova, azul escuro = água nas duas
    sonda.png               R=HH, G=HV (dB quantizado) e B=classe, para a leitura ao passar o mouse

Libs: h5py numpy pillow pyproj pyogrio scipy
"""
import csv
import glob
import json
import os
import sys

import h5py
import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import binary_erosion, uniform_filter

sys.path.insert(0, os.path.dirname(__file__))
from area_agua import (GRADE, PASSO, caixa_do_poligono, coordenadas_recorte, data_do_nome,  # noqa: E402
                       epsg_do_h5, ler_poligono, ler_recorte, mascara_do_poligono, tirar_manchas,
                       valido_da_mask, km2)

PASTA_H5 = os.path.join("data", "raw", "nisar")
POLIGONO = os.path.join("data", "ana", "furnas", "Furnas.gdb")
OFICIAL = os.path.join("outputs", "furnas_poligono_b0")
COTAS = os.path.join("data", "ana", "cota_furnas_ana.csv")
CURVA = os.path.join("data", "ana", "furnas_cota_area.csv")
COBERTURA_FUNIL = os.path.join("outputs", "funil_poligono_b0", "cobertura.csv")
SAIDA = os.path.join("web", "data")

LIMIAR_DB = -15.65
DATAS_VENTO = {"20260907", "20261001"}
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
TOM_ESCURO = np.array([9, 15, 19], float)      # mesmo tom do fundo do site
TOM_CLARO = np.array([232, 226, 212], float)
COR_AGUA = (38, 110, 196)
COR_SECOU = (232, 140, 58)
COR_NOVA = (88, 176, 255)
COR_AGUA_FIXA = (24, 52, 92)
HV_VOLUME_DB = -13.0        # HV acima disso: espalhamento de volume forte (copas de árvores, provável)


def ler_banda(caminho, caixa, banda, passo=PASSO):
    """Mesmo recorte e filtro de area_agua.ler_recorte, para qualquer banda (ex.: HVHV)."""
    with h5py.File(caminho, "r") as h:
        g = h[GRADE]
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        x0, x1, y0, y1 = caixa
        cols = np.where((x >= min(x0, x1)) & (x <= max(x0, x1)))[0]
        rows = np.where((y >= min(y0, y1)) & (y <= max(y0, y1)))[0]
        r = slice(rows[0], rows[-1] + 1, passo)
        c = slice(cols[0], cols[-1] + 1, passo)
        v = g[banda][r, c].astype("float32")
        valido = np.isfinite(v) & (v > 0) & valido_da_mask(g["mask"][r, c])
    db = 10 * np.log10(np.where(valido, v, 1e-10))
    db = uniform_filter(np.where(valido, db, np.nanmedian(db[valido])), size=5)
    db[~valido] = np.nan
    return db


def identificacao(caminho):
    with h5py.File(caminho, "r") as h:
        i = h["/science/LSAR/identification"]
        ler = lambda k: i[k][()].decode() if isinstance(i[k][()], bytes) else i[k][()].item()
        return {k: ler(k) for k in ("granuleId", "zeroDopplerStartTime", "trackNumber", "frameNumber",
                                    "orbitPassDirection", "compositeReleaseId", "productVersion",
                                    "absoluteOrbitNumber", "processingCenter")}


def grade_mercator(xs, ys, epsg, largura):
    """Grade regular em Web Mercator que cobre o recorte; devolve índices (linha, coluna) no recorte
    para cada pixel de saída (-1 fora) e os limites em lat/lon."""
    para_merc = Transformer.from_crs(epsg, 3857, always_xy=True)
    de_merc = Transformer.from_crs(3857, epsg, always_xy=True)
    para_ll = Transformer.from_crs(3857, 4326, always_xy=True)
    bx = np.concatenate([xs, np.full_like(ys, xs[0]), xs, np.full_like(ys, xs[-1])])
    by = np.concatenate([np.full_like(xs, ys[0]), ys, np.full_like(xs, ys[-1]), ys])
    mx, my = para_merc.transform(bx, by)
    mx0, mx1, my0, my1 = mx.min(), mx.max(), my.min(), my.max()
    altura = int(round(largura * (my1 - my0) / (mx1 - mx0)))
    px = (mx1 - mx0) / largura
    cx = mx0 + (np.arange(largura) + 0.5) * px
    cy = my1 - (np.arange(altura) + 0.5) * (my1 - my0) / altura
    gx, gy = np.meshgrid(cx, cy)
    ux, uy = de_merc.transform(gx, gy)
    col = np.rint((ux - xs[0]) / (xs[1] - xs[0])).astype(np.int64)
    lin = np.rint((uy - ys[0]) / (ys[1] - ys[0])).astype(np.int64)
    fora = (col < 0) | (col >= len(xs)) | (lin < 0) | (lin >= len(ys))
    col[fora] = -1
    lin[fora] = -1
    lon0, lat0 = para_ll.transform(mx0, my0)
    lon1, lat1 = para_ll.transform(mx1, my1)
    return (lin, col), [[round(lat0, 6), round(lon0, 6)], [round(lat1, 6), round(lon1, 6)]], (largura, altura)


def reamostrar(arr, idx, vazio):
    lin, col = idx
    out = arr[lin.clip(0), col.clip(0)]
    out = np.where(lin >= 0, out, vazio) if out.ndim == 2 else np.where((lin >= 0)[..., None], out, vazio)
    return out


def escala(db, faixa):
    a, b = faixa
    return np.clip((db - a) / (b - a), 0, 1)


def rampa(t):
    """0..1 -> do tom do fundo ao off-white (RGB uint8); NaN -> fundo."""
    t = np.nan_to_num(t, nan=0.0)[..., None]
    return (TOM_ESCURO + (TOM_CLARO - TOM_ESCURO) * t ** 1.2).astype(np.uint8)


def salvar_mascara(caminho, mascara, cor, alfa=235):
    rgba = np.zeros(mascara.shape + (4,), np.uint8)
    rgba[mascara] = (*cor, alfa)
    Image.fromarray(rgba, "RGBA").quantize(colors=4, method=Image.Quantize.FASTOCTREE).save(caminho, optimize=True)


def simplificar(pontos, tol):
    """Douglas-Peucker iterativo."""
    manter = np.zeros(len(pontos), bool)
    manter[[0, -1]] = True
    pilha = [(0, len(pontos) - 1)]
    while pilha:
        i, j = pilha.pop()
        if j <= i + 1:
            continue
        a, b = pontos[i], pontos[j]
        seg = b - a
        n = np.hypot(*seg)
        p = pontos[i + 1:j] - a
        d = np.abs(seg[0] * p[:, 1] - seg[1] * p[:, 0]) / n if n > 0 else np.hypot(p[:, 0], p[:, 1])
        k = int(np.argmax(d))
        if d[k] > tol:
            manter[i + 1 + k] = True
            pilha += [(i, i + 1 + k), (i + 1 + k, j)]
    return pontos[manter]


def area_anel_km2(a):
    x, y = a[:, 0], a[:, 1]
    return abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2 / 1e6


def ler_csv(caminho):
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    os.makedirs(SAIDA, exist_ok=True)
    arquivos = sorted(glob.glob(os.path.join(PASTA_H5, "*_024_D_099_2005_*.h5")), key=data_do_nome)
    epsg = epsg_do_h5(arquivos[0])
    aneis = ler_poligono(POLIGONO, epsg)
    caixa = caixa_do_poligono(aneis, 2000)  # igual à rodada oficial com --buffer 0
    oficial = {l["data"]: float(l["area_km2"]) for l in ler_csv(os.path.join(OFICIAL, "area_agua.csv"))}

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

    # série: cota e curva ANA x NISAR
    cotas = {l["data"].replace("-", ""): l for l in ler_csv(COTAS)}
    curva = np.array([[float(l["cota_m"]), float(l["area_km2"])] for l in ler_csv(CURVA)])
    serie = []
    for d in datas:
        c = float(cotas[d]["cota_furnas_m"])
        esp = float(np.interp(c, curva[:, 0], curva[:, 1]))
        serie.append({"data": f"{d[:4]}-{d[4:6]}-{d[6:]}", "cota_ana_m": c,
                      "volume_util_pct": float(cotas[d]["volume_util_pct"]),
                      "boletim_ana": cotas[d]["boletim_ana"],
                      "area_esperada_km2": round(esp, 1), "area_nisar_km2": oficial[d],
                      "suspeita_vento": d in DATAS_VENTO, "brilho_agua_hh_db": brilho[d]})
    for s in serie:
        s["delta_esperado_km2"] = round(s["area_esperada_km2"] - serie[0]["area_esperada_km2"], 1)
        s["delta_nisar_km2"] = round(s["area_nisar_km2"] - serie[0]["area_nisar_km2"], 1)
        s["diferenca_km2"] = round(s["area_nisar_km2"] - s["area_esperada_km2"], 1)
        s["diferenca_pct"] = round(100 * s["diferenca_km2"] / s["area_esperada_km2"], 2)
    with open(os.path.join(SAIDA, "serie.json"), "w", encoding="utf-8") as f:
        json.dump(serie, f, indent=1, ensure_ascii=False)

    # métricas (só datas calmas, salvo indicação)
    cal = [s for s in serie if not s["suspeita_vento"]]
    dif = np.array([s["diferenca_km2"] for s in cal])
    cc = np.array([s["cota_ana_m"] for s in cal])
    aa = np.array([s["area_nisar_km2"] for s in cal])
    todas_c = np.array([s["cota_ana_m"] for s in serie])
    faixa = (curva[:, 0] >= todas_c.min() - 1e-9) & (curva[:, 0] <= todas_c.max() + 1e-9)
    i_max, i_min = int(np.argmax(todas_c)), int(np.argmin(todas_c))
    vento = [s for s in serie if s["suspeita_vento"]]
    with open(COBERTURA_FUNIL, newline="") as f:
        funil = next(csv.DictReader(f))
    metricas = {
        "n_datas": len(serie), "n_datas_calmas": len(cal),
        "erro_abs_medio_km2": round(float(np.mean(np.abs(dif))), 1),
        "erro_abs_medio_pct": round(float(np.mean([abs(s["diferenca_pct"]) for s in cal])), 1),
        "vies_km2": round(float(np.mean(dif)), 1),
        "ruido_dp_km2": round(float(np.std(dif, ddof=1)), 1),
        "inclinacao_nisar_km2_por_m": round(float(np.polyfit(cc, aa, 1)[0]), 1),
        "intercepto_nisar_km2": round(float(np.polyfit(cc, aa, 1)[1]), 1),
        "inclinacao_ana_km2_por_m": round(float(np.polyfit(curva[faixa, 0], curva[faixa, 1], 1)[0]), 1),
        "r_cota_area": round(float(np.corrcoef(cc, aa)[0, 1]), 2),
        "cota_max_m": float(todas_c[i_max]), "cota_max_data": serie[i_max]["data"],
        "cota_min_m": float(todas_c[i_min]), "cota_min_data": serie[i_min]["data"],
        "queda_cota_m": round(float(todas_c[i_max] - todas_c[i_min]), 2),
        "variacao_area_esperada_km2": round(serie[i_max]["area_esperada_km2"] - serie[i_min]["area_esperada_km2"], 1),
        "erro_abs_medio_todas_km2": round(float(np.mean([abs(s["diferenca_km2"]) for s in serie])), 1),
        "pior_diferenca_vento_km2": min(s["diferenca_km2"] for s in vento),
        "brilho_agua_calmas_db": round(float(np.mean([s["brilho_agua_hh_db"] for s in cal])), 1),
        "brilho_agua_vento_db": [s["brilho_agua_hh_db"] for s in vento],
        "area_esperada_faixa_km2": [min(s["area_esperada_km2"] for s in serie), max(s["area_esperada_km2"] for s in serie)],
        "area_nisar_calmas_faixa_km2": [float(aa.min()), float(aa.max())],
    }
    m_px = pixel_m
    meta = {
        "projeto": "TerraPulse", "licenca": "MIT",
        "colecao": "NISAR_L2_GCOV_PROVISIONAL_V1", "arquivo_daac": "ASF DAAC",
        "trilha": 24, "direcao": "D", "frame": 99, "modo": "2005", "banda": "L", "polarizacoes": ["HH", "HV"],
        "pixel_original_m": 20, "pixel_processado_m": m_px,
        "epsg_original": epsg,
        "metodo": {"canal": "HH", "filtro": "média 5x5 em dB", "limiar_db": LIMIAR_DB,
                   "contagem": "só dentro do polígono oficial da ANA, sem buffer",
                   "mancha_minima_km2": 0.1, "mesmo_limiar_todas_datas": True},
        "poligono": {"fonte": "ANA/SNIRH, Furnas.gdb, camada Reservatório", "cota_operacao_m": 768.0,
                     "area_km2": km2(dentro, pixel_m), "area_ficha_ana_km2": 1332.14},
        "cobertura": {"furnas_frac": 1.0, "funil_frac": round(float(funil["frac_com_dado_valido_todas_datas"]), 3)},
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
