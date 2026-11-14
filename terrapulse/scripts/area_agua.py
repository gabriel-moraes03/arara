"""
Passo 2 do TerraPulse: área de água de Furnas em cada data + mapa do que mudou.

Coloque todos os .h5 da MESMA trilha/frame (ex.: *_024_D_099_2005_*) numa pasta e rode (da raiz):
    python scripts/area_agua.py [data/raw/nisar] [--saida outputs]

Gera, em --saida:
    area_agua.csv          -> data, area_km2 (zona do lago, limiar automático), limiar_db,
                              area_bruta_km2 (sem zona/sem limpeza), area_18db_km2 (zona, limiar fixo -18 dB)
    agua_AAAAMMDD.png      -> máscara de água de cada data (azul = água)
    mudanca.png            -> primeira x última data: vermelho = secou, azul = virou água
    series.png             -> as três séries de área lado a lado
    zona_lago.png          -> zona onde a água é contada
    dados_mudanca.npz      -> arrays para o site, se precisar

Libs: h5py numpy matplotlib scipy
"""
import argparse
import glob
import os
import csv
import h5py
import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import uniform_filter, gaussian_filter1d, distance_transform_edt, label
from scipy.signal import find_peaks

GRADE = "/science/LSAR/GCOV/grids/frequencyA"
PASSO = 2  # 1 = resolução cheia (20 m, mais lento); 2 = 40 m, rápido e suficiente

# Recorte do lago, em FRAÇÃO da imagem (0 a 1), medido na trilha 024 D 099: (x_ini, x_fim, y_ini, y_fim).
# Começa na barragem de Furnas (x≈0.43), deixa de fora o lago de Peixoto/M. Moraes a jusante (x<0.35)
# e o Funil a montante (barragem em x≈0.84); y vai até o braço do Sapucaí (Paraguaçu, y≈0.67).
# A faixa ruim da esquerda é removida pela camada mask (valor 0), não pelo recorte.
RECORTE = (0.42, 0.83, 0.28, 0.72)

# Limiar: só nos blocos de margem (com água E terra), porque no recorte inteiro a água é ~3% dos
# pixels e o Otsu "puro" corta dentro da terra (deu -12 dB no real). Nesses blocos o Otsu ainda
# puxa para o lado da terra (classe mais larga), então o corte final é o vale entre os dois picos.
BLOCO = 50                 # lado do bloco em pixels lidos (50 x 40 m = 2 km)
SEMENTE_DB = -20.0         # pixel "certamente água", só para escolher os blocos de margem
FRACAO_SEMENTE = (0.2, 0.8)
LIMIAR_FIXO_DB = -18.0     # série de comparação com limiar fixo

# Zona do lago (provisória, até chegar o polígono oficial da ANA/SNIRH): pixels que são água em
# pelo menos 5 de 9 datas, dilatados ~1 km. Fora dela não se conta água (solo seco/pasto escuro).
FRACAO_DATAS_ZONA = 5 / 9
DILATACAO_ZONA_M = 1000.0
MANCHA_MIN_KM2 = 0.1       # manchas de água menores que isso são descartadas
SEMENTE_MIN_KM2 = 1.0      # pedaços do núcleo com pelo menos isso são "o lago"; a água tem de tocá-los
BUFFER_POLIGONO_M = 500.0  # com o polígono oficial (--poligono): buffer para fora do limite


def data_do_nome(caminho):
    # NISAR_L2_PR_GCOV_024_024_D_099_2005_DHDH_M_20260627T211458_... -> 20260627
    return os.path.basename(caminho).split("_")[11][:8]


def otsu(valores, bins=256):
    """Acha o melhor corte entre os dois 'morros' do histograma (água x terra)."""
    hist, bordas = np.histogram(valores, bins=bins)
    centros = (bordas[:-1] + bordas[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centros) / np.maximum(w0, 1)
    m1 = (np.sum(hist * centros) - np.cumsum(hist * centros)) / np.maximum(w1, 1)
    entre = w0 * w1 * (m0 - m1) ** 2
    return centros[np.argmax(entre)]


def vale(valores, bins=120, suavizar=3):
    """Mínimo do histograma (suavizado) entre os dois picos mais proeminentes (água e terra).
    Se não houver dois picos, usa o Otsu."""
    hist, bordas = np.histogram(valores, bins=bins)
    centros = (bordas[:-1] + bordas[1:]) / 2
    hist = gaussian_filter1d(hist.astype(float), suavizar)
    picos, props = find_peaks(np.concatenate([[0], hist, [0]]), prominence=0)
    if len(picos) < 2:
        return otsu(valores)
    i_agua, i_terra = np.sort(picos[np.argsort(props["prominences"])[-2:]] - 1)
    return centros[i_agua + np.argmin(hist[i_agua:i_terra + 1])]


def limiar_bimodal(db, valido, bloco=BLOCO, semente=SEMENTE_DB, fracao=FRACAO_SEMENTE):
    """Vale água/terra nos blocos de margem (20-80% de pixels < semente), não na imagem toda."""
    ny, nx = (db.shape[0] // bloco) * bloco, (db.shape[1] // bloco) * bloco
    blocos = db[:ny, :nx].reshape(ny // bloco, bloco, nx // bloco, bloco).swapaxes(1, 2).reshape(-1, bloco * bloco)
    cheios = valido[:ny, :nx].reshape(ny // bloco, bloco, nx // bloco, bloco).swapaxes(1, 2).reshape(-1, bloco * bloco).all(1)
    escuro = (blocos < semente).mean(1)
    margem = cheios & (escuro > fracao[0]) & (escuro < fracao[1])
    if margem.sum() < 5:  # sem blocos de margem suficientes: cai no Otsu da imagem toda
        return otsu(db[valido])
    return vale(blocos[margem].ravel())


def valido_da_mask(mask):
    """mask do GCOV: 1..254 = número da subfaixa (válido), 0 = amostra inválida, 255 = fora da passagem."""
    return (mask >= 1) & (mask < 255)


def caixa_do_recorte(x, y, recorte=RECORTE):
    """Converte o recorte em frações da imagem numa caixa em METROS (x0, x1, y0, y1)."""
    xa, xb, ya, yb = recorte
    return (
        x[int(xa * len(x))], x[int(xb * len(x)) - 1],
        y[int(ya * len(y))], y[int(yb * len(y)) - 1],
    )


def ler_recorte(caminho, caixa=None, recorte=RECORTE, passo=PASSO):
    with h5py.File(caminho, "r") as h:
        g = h[GRADE]
        x = g["xCoordinates"][:]
        y = g["yCoordinates"][:]
        if caixa is None:  # primeira imagem: define a caixa do lago em METROS
            caixa = caixa_do_recorte(x, y, recorte)
        x0, x1, y0, y1 = caixa
        cols = np.where((x >= min(x0, x1)) & (x <= max(x0, x1)))[0]
        rows = np.where((y >= min(y0, y1)) & (y <= max(y0, y1)))[0]
        r = slice(rows[0], rows[-1] + 1, passo)
        c = slice(cols[0], cols[-1] + 1, passo)
        hh = g["HHHH"][r, c].astype("float32")
        pixel_m = abs(x[1] - x[0]) * passo
        valido = np.isfinite(hh) & (hh > 0)
        if "mask" in g:
            valido &= valido_da_mask(g["mask"][r, c])
    db = 10 * np.log10(np.where(valido, hh, 1e-10))
    # tira o granulado: média 5x5 feita em dB, para não "comer" as margens finas do lago
    db = uniform_filter(np.where(valido, db, np.nanmedian(db[valido])), size=5)
    db[~valido] = np.nan
    return db, valido, pixel_m, caixa


def coordenadas_recorte(caminho, caixa, passo=PASSO):
    """Coordenadas (m) dos centros de coluna e linha do recorte, na mesma grade de ler_recorte."""
    with h5py.File(caminho, "r") as h:
        x = h[GRADE]["xCoordinates"][:]
        y = h[GRADE]["yCoordinates"][:]
    x0, x1, y0, y1 = caixa
    cols = np.where((x >= min(x0, x1)) & (x <= max(x0, x1)))[0]
    rows = np.where((y >= min(y0, y1)) & (y <= max(y0, y1)))[0]
    return x[cols[0]:cols[-1] + 1:passo], y[rows[0]:rows[-1] + 1:passo]


def epsg_do_h5(caminho):
    with h5py.File(caminho, "r") as h:
        proj = h[GRADE]["projection"]
        return int(proj.attrs.get("epsg_code", proj[()]))


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


def ler_poligono(caminho, epsg_destino):
    """.shp ou .gdb (opcionalmente 'arquivo.gdb::camada')."""
    caminho, _, camada = caminho.partition("::")
    if caminho.rstrip("/\\").lower().endswith(".gdb"):
        return ler_poligono_gdb(caminho, epsg_destino, camada or None)
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


def grafico_series(linhas, caminho):
    """Séries no mesmo eixo (mesma unidade): bruta, só zona, zona + ligada ao lago, idem com -18 dB."""
    datas = [f"{d[6:8]}/{d[4:6]}" for d in (l[0] for l in linhas)]
    series = [  # (nome, coluna, cor) - paleta categórica validada, ordem fixa
        ("bruta (limiar automático, sem zona)", 3, "#2a78d6"),
        ("só zona do lago (limiar automático)", 4, "#eb6834"),
        ("zona + ligada ao lago (limiar automático)", 1, "#1baf7a"),
        (f"zona + ligada ao lago ({LIMIAR_FIXO_DB:.0f} dB fixo)", 5, "#eda100"),
    ]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for nome, col, cor in series:
        y = [l[col] for l in linhas]
        ax.plot(datas, y, color=cor, lw=2, marker="o", ms=6, label=nome,
                markeredgecolor="white", markeredgewidth=1.5)
    # rótulo do último valor de cada série, afastando os que ficariam encostados
    finais = sorted(linhas[-1][col] for _, col, _ in series)
    folga = 0.035 * max(max(l[col] for l in linhas) for _, col, _ in series)
    posicoes = []
    for v in finais:
        posicoes.append(max(v, posicoes[-1] + folga) if posicoes else v)
    for v, p in zip(finais, posicoes):
        ax.annotate(f"{v:.0f}", (len(datas) - 1, v), xytext=(len(datas) - 1 + 0.12, p),
                    va="center", fontsize=9, color="#333333")
    ax.set_ylabel("área de água (km²)", color="#333333")
    ax.set_title("Furnas: área de água por data (NISAR GCOV HH, trilha 024 D)", loc="left", color="#111111")
    ax.grid(axis="y", color="#e5e5e5", lw=0.8)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#bbbbbb")
    ax.tick_params(colors="#555555")
    ax.set_ylim(0, None)
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout()
    fig.savefig(caminho, dpi=130)
    plt.close(fig)


def processar(arquivos, saida, recorte=RECORTE, passo=PASSO, poligono=None, limiar=None,
              buffer_m=BUFFER_POLIGONO_M):
    """Roda a série toda; devolve a lista de
    (data, area_km2, limiar_db, area_bruta_km2, area_so_zona_km2, area_18db_km2).
    poligono: anéis do limite oficial do reservatório, já no EPSG do .h5 (ver ler_poligono_shp);
    sem ele, a zona do lago é derivada das próprias datas. Com ele, o recorte passa a ser a caixa
    do polígono e grava-se cobertura.csv.
    limiar: em dB; se None, calculado na 1ª data (vale nos blocos de margem)."""
    os.makedirs(saida, exist_ok=True)
    # com polígono, o recorte é a caixa do polígono + buffer + 2 km (cobre o lago inteiro)
    caixa = caixa_do_poligono(poligono, buffer_m + 2000) if poligono is not None else None
    datas, brutas, brutas_18 = [], [], []
    valido_sempre = None

    # 1ª passada: água bruta de cada data, nos dois limiares
    for arq in arquivos:
        data = data_do_nome(arq)
        db, valido, pixel_m, caixa = ler_recorte(arq, caixa, recorte, passo)
        if limiar is None:  # o MESMO limiar para todas as datas, calculado na primeira
            limiar = limiar_bimodal(db, valido)
            print(f"limiar de água (vale nos blocos de margem): {limiar:.1f} dB")
        datas.append(data)
        brutas.append((db < limiar) & valido)
        brutas_18.append((db < LIMIAR_FIXO_DB) & valido)
        valido_sempre = valido if valido_sempre is None else valido_sempre & valido

    # 2ª passada: só dentro da zona do lago, sem manchas pequenas
    xs, ys = coordenadas_recorte(arquivos[0], caixa, passo)
    if poligono is not None:
        # polígono oficial + buffer: ele já delimita o lago, não precisa ligar ao núcleo
        dentro = mascara_do_poligono(poligono, xs, ys)
        zona = mascara_do_poligono(poligono, xs, ys, buffer_m)
        sementes = zona
        with h5py.File(arquivos[0], "r") as h:
            x_todo, y_todo = h[GRADE]["xCoordinates"][:], h[GRADE]["yCoordinates"][:]
        xa, xb, ya, yb = caixa_do_recorte(x_todo, y_todo, RECORTE)
        no_recorte_antigo = (((xs >= min(xa, xb)) & (xs <= max(xa, xb)))[None, :]
                             & ((ys >= min(ya, yb)) & (ys <= max(ya, yb)))[:, None])
        cobertura = {
            "area_poligono_km2": km2(dentro, pixel_m),
            "frac_no_recorte_antigo": round(float((dentro & no_recorte_antigo).sum() / dentro.sum()), 4),
            "frac_com_dado_valido_todas_datas": round(float((dentro & valido_sempre).sum() / dentro.sum()), 4),
        }
        with open(os.path.join(saida, "cobertura.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cobertura.keys())
            w.writerow(cobertura.values())
        print(f"polígono: {cobertura['area_poligono_km2']:.1f} km² | no recorte antigo "
              f"{cobertura['frac_no_recorte_antigo']:.1%} | com dado válido em todas as datas "
              f"{cobertura['frac_com_dado_valido_todas_datas']:.1%}")
        print(f"zona do lago (polígono + {buffer_m:.0f} m): {km2(zona, pixel_m):.0f} km²")
    else:
        # zona derivada das datas, e a água tem de estar ligada ao núcleo do lago
        zona = zona_do_lago(brutas, pixel_m)
        sementes = tirar_manchas(nucleo_do_lago(brutas), pixel_m, SEMENTE_MIN_KM2) & zona
        print(f"zona do lago: {km2(zona, pixel_m):.0f} km² | sementes do lago: {km2(sementes, pixel_m):.0f} km²")
    plt.imsave(os.path.join(saida, "zona_lago.png"), zona, cmap="Greys")

    def limpar(bruta):
        h, w = min(bruta.shape[0], zona.shape[0]), min(bruta.shape[1], zona.shape[1])
        so_zona = tirar_manchas(bruta[:h, :w] & zona[:h, :w], pixel_m)
        if poligono is not None:
            return so_zona, so_zona
        return so_zona, ligada_ao_lago(so_zona, sementes[:h, :w])

    mascaras = {}
    linhas = []
    for data, bruta, bruta_18 in zip(datas, brutas, brutas_18):
        so_zona, agua = limpar(bruta)
        _, agua_18 = limpar(bruta_18)
        mascaras[data] = agua
        linhas.append((data, km2(agua, pixel_m), round(float(limiar), 2),
                       km2(bruta, pixel_m), km2(so_zona, pixel_m), km2(agua_18, pixel_m)))
        print(f"{data}: {linhas[-1][1]:8.2f} km² (bruta {linhas[-1][3]:8.2f} | só zona {linhas[-1][4]:8.2f}"
              f" | {LIMIAR_FIXO_DB:.0f} dB {linhas[-1][5]:8.2f})")
        plt.imsave(os.path.join(saida, f"agua_{data}.png"), agua, cmap="Blues")

    with open(os.path.join(saida, "area_agua.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["data", "area_km2", "limiar_db", "area_bruta_km2", "area_so_zona_km2", "area_18db_km2"])
        w.writerows(linhas)
    print("salvo:", os.path.join(saida, "area_agua.csv"))
    grafico_series(linhas, os.path.join(saida, "series.png"))
    print("salvo:", os.path.join(saida, "series.png"))

    # Mapa de mudança: primeira x última data
    d0, d1 = linhas[0][0], linhas[-1][0]
    a, b = mascaras[d0], mascaras[d1]
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    a, b = a[:h, :w], b[:h, :w]
    rgb = np.ones((h, w, 3))
    rgb[a & b] = (0.55, 0.75, 0.95)    # água nas duas datas
    rgb[a & ~b] = (0.85, 0.20, 0.15)   # era água, secou
    rgb[~a & b] = (0.10, 0.30, 0.85)   # virou água
    plt.figure(figsize=(10, 8))
    plt.imshow(rgb)
    plt.title(f"Furnas: {d0} → {d1}  (vermelho = secou, azul escuro = virou água)")
    plt.axis("off")
    plt.savefig(os.path.join(saida, "mudanca.png"), dpi=130, bbox_inches="tight")
    plt.close()
    extra = {"poligono": dentro[:h, :w]} if poligono is not None else {}
    np.savez_compressed(os.path.join(saida, "dados_mudanca.npz"), antes=a, depois=b,
                        zona=zona[:h, :w], x=xs[:w], y=ys[:h], datas=np.array([d0, d1]), **extra)
    print("salvo:", os.path.join(saida, "mudanca.png"))
    print(f"secou: {(a & ~b).sum() * pixel_m**2 / 1e6:.2f} km² | virou água: {(~a & b).sum() * pixel_m**2 / 1e6:.2f} km²")
    return linhas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", nargs="?", default=os.path.join("data", "raw", "nisar"),
                    help="pasta com os .h5 (padrão: data/raw/nisar)")
    ap.add_argument("--saida", default="outputs", help="pasta de saída (padrão: outputs)")
    ap.add_argument("--poligono", help="limite oficial do reservatório: .shp, ou .gdb da ANA "
                                       "(opcional 'arquivo.gdb::camada'); sem ele, usa a zona derivada das datas")
    ap.add_argument("--limiar", type=float, help="limiar em dB (padrão: calculado na 1ª data)")
    ap.add_argument("--buffer", type=float, default=BUFFER_POLIGONO_M,
                    help=f"buffer (m) para fora do polígono (padrão: {BUFFER_POLIGONO_M:.0f})")
    args = ap.parse_args()

    arquivos = sorted(glob.glob(os.path.join(args.pasta, "*.h5")), key=data_do_nome)
    if not arquivos:
        raise SystemExit("Nenhum .h5 encontrado na pasta.")
    print(f"{len(arquivos)} arquivos")
    poligono = ler_poligono(args.poligono, epsg_do_h5(arquivos[0])) if args.poligono else None
    processar(arquivos, args.saida, poligono=poligono, limiar=args.limiar, buffer_m=args.buffer)


if __name__ == "__main__":
    main()
