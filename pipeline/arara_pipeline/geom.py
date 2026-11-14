"""Polígonos de referência, máscaras e limpeza da água. Migrado de terrapulse/scripts/area_agua.py."""
import json
import os

import numpy as np
from scipy.ndimage import distance_transform_edt, label

FRACAO_DATAS_ZONA = 5 / 9
DILATACAO_ZONA_M = 1000.0
MANCHA_MIN_KM2 = 0.1
SEMENTE_MIN_KM2 = 1.0


def ler_poligono_shp(caminho_shp, epsg_destino):
    """Lê os anéis de um shapefile de polígonos (tipo 5/15/25) e reprojeta para epsg_destino.
    Usa o .prj ao lado do .shp; sem .prj, assume lat/lon (EPSG:4326)."""
    import struct
    from pyproj import CRS, Transformer

    with open(caminho_shp, "rb") as f:
        dados = f.read()
    aneis, pos = [], 100
    while pos + 8 <= len(dados):
        tamanho = struct.unpack(">i", dados[pos + 4:pos + 8])[0] * 2
        reg = dados[pos + 8:pos + 8 + tamanho]
        pos += 8 + tamanho
        tipo = struct.unpack("<i", reg[:4])[0]
        if tipo not in (5, 15, 25):
            continue
        n_partes, n_pontos = struct.unpack("<2i", reg[36:44])
        partes = list(struct.unpack(f"<{n_partes}i", reg[44:44 + 4 * n_partes])) + [n_pontos]
        ini = 44 + 4 * n_partes
        pontos = np.frombuffer(reg[ini:ini + 16 * n_pontos], "<f8").reshape(-1, 2)
        aneis += [pontos[a:b] for a, b in zip(partes[:-1], partes[1:])]

    prj = os.path.splitext(caminho_shp)[0] + ".prj"
    origem = CRS.from_wkt(open(prj).read()) if os.path.exists(prj) else CRS.from_epsg(4326)
    t = Transformer.from_crs(origem, CRS.from_epsg(epsg_destino), always_xy=True)
    return [np.column_stack(t.transform(a[:, 0], a[:, 1])) for a in aneis]


def linhas_do_wkb(wkb):
    """Lista de arrays (n, 2) com as linhas/anéis de um WKB (Multi)LineString/Polygon, Z/M ignorados."""
    import struct
    linhas, pos = [], 0

    def u32(ordem):
        nonlocal pos
        v = struct.unpack(ordem + "I", wkb[pos:pos + 4])[0]
        pos += 4
        return v

    def coords(ordem, dim):
        nonlocal pos
        n = u32(ordem)
        a = np.frombuffer(wkb[pos:pos + 8 * dim * n], ordem + "f8").reshape(n, dim)[:, :2]
        pos += 8 * dim * n
        return a

    def geom():
        nonlocal pos
        ordem = "<" if wkb[pos] == 1 else ">"
        pos += 1
        tipo = u32(ordem)
        z = bool(tipo & 0x80000000) or (tipo % 10000) // 1000 in (1, 3)
        m = bool(tipo & 0x40000000) or (tipo % 10000) // 1000 in (2, 3)
        base, dim = (tipo & 0xFFFF) % 1000, 2 + z + m
        if base == 2:                       # LineString
            linhas.append(coords(ordem, dim))
        elif base == 3:                     # Polygon
            linhas.extend(coords(ordem, dim) for _ in range(u32(ordem)))
        elif base in (5, 6, 7):             # Multi* / GeometryCollection
            for _ in range(u32(ordem)):
                geom()
        else:
            raise ValueError(f"tipo WKB não suportado: {tipo}")

    geom()
    return linhas


def costurar_linhas(linhas, tolerancia_m=500.0):
    """Junta linhas abertas pela ponta mais próxima até fechar anéis (o contorno do reservatório
    da ANA vem em pedaços). Linhas já fechadas passam direto. Devolve (anéis, maior folga em m)."""
    # distância absoluta: np.allclose é relativo e, em UTM (~7e6 m), aceitaria pontas a ~70 m
    fechada = lambda l: np.hypot(*(l[0] - l[-1])) < 0.01
    fechadas = [l if (l[0] == l[-1]).all() else np.vstack([l, l[:1]]) for l in linhas if fechada(l)]
    abertas = [l for l in linhas if not fechada(l)]
    aneis, maior_folga = list(fechadas), 0.0
    while abertas:
        cadeia = [abertas.pop(0)]
        while True:
            fim, ini = cadeia[-1][-1], cadeia[0][0]
            d_fechar = np.hypot(*(fim - ini))
            melhor, i_melhor, inverter = np.inf, None, False
            for i, l in enumerate(abertas):
                for d, inv in ((np.hypot(*(fim - l[0])), False), (np.hypot(*(fim - l[-1])), True)):
                    if d < melhor:
                        melhor, i_melhor, inverter = d, i, inv
            if i_melhor is None or d_fechar <= melhor or melhor > tolerancia_m:
                maior_folga = max(maior_folga, d_fechar)
                break
            maior_folga = max(maior_folga, melhor)
            pedaco = abertas.pop(i_melhor)
            cadeia.append(pedaco[::-1] if inverter else pedaco)
        anel = np.concatenate(cadeia)
        aneis.append(np.vstack([anel, anel[:1]]))
    return aneis, maior_folga


def ler_poligono_gdb(caminho_gdb, epsg_destino, camada=None):
    """Anéis do limite do reservatório num File Geodatabase da ANA/SNIRH (camada 'Reservatório',
    linhas na cota máxima normal), costurados e reprojetados para epsg_destino."""
    import warnings
    import pyogrio
    from pyogrio.raw import read
    from pyproj import CRS, Transformer

    if camada is None:
        camada = next(nome for nome, _ in pyogrio.list_layers(caminho_gdb) if nome.startswith("Reserv"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # aviso de geometria com M, irrelevante aqui
        meta, _, geometrias, _ = read(caminho_gdb, layer=camada)
    linhas = [l for g in geometrias for l in linhas_do_wkb(g)]
    aneis, folga = costurar_linhas(linhas)
    print(f"polígono: camada '{camada}', {len(linhas)} linhas -> {len(aneis)} anéis (maior folga costurada {folga:.0f} m)")
    origem = CRS.from_user_input(meta["crs"])
    if origem.is_compound:  # SIRGAS 2000 / UTM 23S + vertical: usa só a parte horizontal
        origem = origem.sub_crs_list[0]
    t = Transformer.from_crs(origem, CRS.from_epsg(epsg_destino), always_xy=True)
    return [np.column_stack(t.transform(a[:, 0], a[:, 1])) for a in aneis]


def aneis_do_geojson(geo):
    """Anéis (lon, lat) de um GeoJSON: Polygon, MultiPolygon, (Multi)LineString fechada, Feature(Collection)."""
    t = geo.get("type")
    if t == "FeatureCollection":
        return [a for f in geo["features"] for a in aneis_do_geojson(f)]
    if t == "Feature":
        return aneis_do_geojson(geo["geometry"])
    c = geo["coordinates"]
    if t == "Polygon":
        return [np.asarray(a, float)[:, :2] for a in c]
    if t == "MultiPolygon":
        return [np.asarray(a, float)[:, :2] for p in c for a in p]
    if t == "LineString":
        return [np.asarray(c, float)[:, :2]]
    if t == "MultiLineString":
        return [np.asarray(a, float)[:, :2] for a in c]
    raise ValueError(f"geometria GeoJSON não suportada: {t}")


def reprojetar_aneis(aneis, epsg_origem, epsg_destino):
    from pyproj import Transformer
    t = Transformer.from_crs(epsg_origem, epsg_destino, always_xy=True)
    return [np.column_stack(t.transform(a[:, 0], a[:, 1])) for a in aneis]


def ler_poligono_geojson(caminho, epsg_destino):
    """GeoJSON em lon/lat (EPSG:4326) -> anéis no EPSG da grade."""
    with open(caminho, encoding="utf-8") as f:
        return reprojetar_aneis(aneis_do_geojson(json.load(f)), 4326, epsg_destino)


def salvar_poligono_geojson(aneis, epsg_origem, caminho, propriedades=None, casas=6):
    """Grava os anéis costurados (sem simplificar) como MultiLineString em lon/lat."""
    ll = reprojetar_aneis(aneis, epsg_origem, 4326)
    geo = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": propriedades or {},
        "geometry": {"type": "MultiLineString",
                     "coordinates": [[[round(float(x), casas), round(float(y), casas)] for x, y in a] for a in ll]}}]}
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(geo, f, separators=(",", ":"), ensure_ascii=False)


def ler_poligono(caminho, epsg_destino):
    """.shp, .geojson/.json ou .gdb (opcionalmente 'arquivo.gdb::camada')."""
    caminho, _, camada = caminho.partition("::")
    baixo = caminho.rstrip("/\\").lower()
    if baixo.endswith(".gdb"):
        return ler_poligono_gdb(caminho, epsg_destino, camada or None)
    if baixo.endswith((".geojson", ".json")):
        return ler_poligono_geojson(caminho, epsg_destino)
    return ler_poligono_shp(caminho, epsg_destino)


def caixa_do_poligono(aneis, margem_m):
    pts = np.concatenate(aneis)
    (x0, y0), (x1, y1) = pts.min(0) - margem_m, pts.max(0) + margem_m
    return (x0, x1, y1, y0)


def mascara_do_poligono(aneis, xs, ys, buffer_m=0.0):
    """Pixels (grade regular xs × ys) cujo centro está dentro dos anéis, pela regra par-ímpar
    (ilha dentro do contorno vira buraco), dilatados buffer_m para fora.
    Varredura por linha: cada aresta gera um cruzamento por linha da grade que atravessa; um
    pixel está dentro se tem nº ímpar de cruzamentos à esquerda. Custo linear no nº de vértices + pixels."""
    ny, nx = len(ys), len(xs)
    # coordenadas contínuas em índice de linha/coluna (vale para y crescente ou decrescente)
    arestas = np.concatenate([np.column_stack([a[:-1], a[1:]]) for a in aneis if len(a) > 1])
    c0 = (arestas[:, 0] - xs[0]) / (xs[1] - xs[0])
    r0 = (arestas[:, 1] - ys[0]) / (ys[1] - ys[0])
    c1 = (arestas[:, 2] - xs[0]) / (xs[1] - xs[0])
    r1 = (arestas[:, 3] - ys[0]) / (ys[1] - ys[0])
    rmin, rmax = np.minimum(r0, r1), np.maximum(r0, r1)
    i_ini = np.ceil(rmin).astype(np.int64)
    i_fim = np.ceil(rmax).astype(np.int64)            # linhas i com rmin <= i < rmax
    n = np.clip(i_fim, 0, ny) - np.clip(i_ini, 0, ny)
    validas = n > 0
    e = np.repeat(np.nonzero(validas)[0], n[validas])
    i = np.clip(i_ini, 0, ny)[e] + (np.arange(len(e)) - np.repeat(np.cumsum(n[validas]) - n[validas], n[validas]))
    c = c0[e] + (i - r0[e]) / (r1[e] - r0[e]) * (c1[e] - c0[e])
    # cruzamento em c afeta os pixels j >= c; a paridade da soma acumulada dá dentro/fora
    marca = np.zeros((ny, nx + 1), np.int32)
    np.add.at(marca, (i, np.clip(np.ceil(c), 0, nx).astype(np.int64)), 1)
    dentro = np.cumsum(marca, axis=1)[:, :nx] % 2 == 1
    if buffer_m <= 0:
        return dentro
    pixel_m = abs(xs[1] - xs[0])
    return distance_transform_edt(~dentro) * pixel_m <= buffer_m


def nucleo_do_lago(mascaras, fracao=FRACAO_DATAS_ZONA):
    """Pixels que são água em >= fracao das datas."""
    pilha = np.stack([m[:min(a.shape[0] for a in mascaras), :min(a.shape[1] for a in mascaras)]
                      for m in mascaras])
    return pilha.sum(axis=0) >= np.ceil(fracao * len(mascaras) - 1e-9)


def zona_do_lago(mascaras, pixel_m, fracao=FRACAO_DATAS_ZONA, dilatacao_m=DILATACAO_ZONA_M):
    """Núcleo do lago dilatado dilatacao_m, e só o pedaço ligado ao lago principal (o maior):
    manchas de terra escuras recorrentes também passam no critério das datas, mas ficam
    isoladas. Trocar pelo polígono oficial quando houver."""
    nucleo = nucleo_do_lago(mascaras, fracao)
    zona = distance_transform_edt(~nucleo) * pixel_m <= dilatacao_m
    rotulos, n = label(zona, structure=np.ones((3, 3)))
    if n == 0:
        return zona
    return rotulos == np.argmax(np.bincount(rotulos.ravel())[1:]) + 1


def tirar_manchas(agua, pixel_m, minimo_km2=MANCHA_MIN_KM2):
    """Remove componentes de água (vizinhança 8) menores que minimo_km2."""
    rotulos, _ = label(agua, structure=np.ones((3, 3)))
    tamanhos = np.bincount(rotulos.ravel()) * pixel_m ** 2 / 1e6
    manter = tamanhos >= minimo_km2
    manter[0] = False
    return manter[rotulos]


def ligada_ao_lago(agua, sementes):
    """Mantém só os pedaços de água (vizinhança 8) que tocam as sementes do lago."""
    rotulos, _ = label(agua, structure=np.ones((3, 3)))
    ids = np.unique(rotulos[sementes & agua])
    return np.isin(rotulos, ids[ids > 0])


def km2(agua, pixel_m):
    return round(float(agua.sum() * pixel_m ** 2 / 1e6), 2)
