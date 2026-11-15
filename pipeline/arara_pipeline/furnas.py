"""Série de área de água com o método validado em Furnas.

Sem polígono, a zona do lago é derivada das próprias datas; com polígono, conta-se só dentro dele.
Nenhum caminho, limiar ou coordenada de Furnas é fixo aqui: tudo entra por argumento.
"""
import csv
import os

import h5py
import numpy as np

from .geom import *  # noqa: F401,F403
from .geom import (FRACAO_DATAS_ZONA, DILATACAO_ZONA_M, MANCHA_MIN_KM2, SEMENTE_MIN_KM2, caixa_do_poligono,
                   km2, ligada_ao_lago, mascara_do_poligono, nucleo_do_lago, tirar_manchas, zona_do_lago)
from .sar import *  # noqa: F401,F403
from .sar import (BLOCO, FRACAO_SEMENTE, GRADE, PASSO, RECORTE, SEMENTE_DB, caixa_do_recorte,
                  coordenadas_recorte, data_do_nome, ler_recorte, limiar_bimodal)

LIMIAR_FIXO_DB = -18.0     # série de comparação com limiar fixo
BUFFER_POLIGONO_M = 500.0  # com polígono: buffer para fora do limite (o método oficial usa 0)


def grafico_series(linhas, caminho):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
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
