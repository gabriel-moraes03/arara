"""
Junta a série NISAR (com o polígono oficial) com a cota e a curva cota × área da ANA e gera o
pacote analise/ (substitui se existir).

Rodar (da raiz), depois das rodadas de pipeline/scripts/area_agua.py com --poligono:
    python pipeline/scripts/analise.py --furnas <saida +500 m> --furnas-sem-buffer <saida sem buffer>

Entradas (padrões):
    outputs/furnas_poligono/       Furnas, polígono + 500 m (principal)
    outputs/furnas_poligono_b0/    Furnas, polígono sem buffer (comparação)
    outputs/funil_poligono/        Funil, polígono + 500 m (opcional)
    data/ana/cota_furnas_ana.csv   data, cota_furnas_m, volume_util_pct, boletim_ana
    data/ana/furnas_cota_area.csv  cota_m, area_km2 (scripts/converter_cav.py)

Saída em analise/: serie.csv, grafico_series.png, grafico_deltas.png, dispersao_cota_area.png,
    agua_27jun_vs_13out.png, mudanca_corrigida.png, previa_colorida.png, metricas.txt
"""
import argparse
import csv
import os
import shutil
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATAS_VENTO = {"20260907", "20261001"}  # água mais clara/uniforme (ver investigação de 07/09)

COR_BRUTA, COR_M15, COR_B0, COR_M18, COR_COTA = "#2a78d6", "#1baf7a", "#e87ba4", "#eda100", "#eb6834"
COR_ESP, TINTA, TINTA_2, GRADE = "#444444", "#111111", "#555555", "#e5e5e5"


def ler_csv(caminho):
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def por_data(pasta):
    return {l["data"]: l for l in ler_csv(os.path.join(pasta, "area_agua.csv"))}


def cobertura(pasta):
    return float(ler_csv(os.path.join(pasta, "cobertura.csv"))[0]["frac_com_dado_valido_todas_datas"])


def estilo(ax):
    ax.grid(axis="y", color=GRADE, lw=0.8)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#bbbbbb")
    ax.tick_params(colors=TINTA_2)


def linha(ax, x, y, cor, nome, ls="-", marcador="o"):
    ax.plot(x, y, color=cor, lw=2, ls=ls, marker=marcador, ms=6, label=nome,
            markeredgecolor="white", markeredgewidth=1.5)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--furnas", default=os.path.join("outputs", "furnas_poligono"))
    ap.add_argument("--furnas-sem-buffer", default=os.path.join("outputs", "furnas_poligono_b0"))
    ap.add_argument("--funil", default=os.path.join("outputs", "funil_poligono"))
    ap.add_argument("--cota", default=os.path.join("data", "ana", "cota_furnas_ana.csv"))
    ap.add_argument("--tabela", default=os.path.join("data", "ana", "furnas_cota_area.csv"))
    ap.add_argument("--previa", default=None)
    ap.add_argument("--saida", default="analise")
    args = ap.parse_args()

    if os.path.isdir(args.saida):
        shutil.rmtree(args.saida)
    os.makedirs(args.saida)

    furnas, b0 = por_data(args.furnas), por_data(args.furnas_sem_buffer)
    funil = por_data(args.funil) if os.path.isdir(args.funil) else {}
    cota = {l["data"].replace("-", ""): l for l in ler_csv(args.cota)}
    tabela = sorted((float(l["cota_m"]), float(l["area_km2"])) for l in ler_csv(args.tabela))
    tab_c, tab_a = np.array(tabela).T
    datas = sorted(set(furnas) & set(cota))
    if len(datas) != len(furnas):
        print("AVISO: datas NISAR sem cota ANA:", sorted(set(furnas) - set(cota)))

    frac = cobertura(args.furnas)                       # fração do polígono vista pelo NISAR
    cotas = np.array([float(cota[d]["cota_furnas_m"]) for d in datas])
    esperada = np.interp(cotas, tab_c, tab_a) * frac
    bruta = np.array([float(furnas[d]["area_bruta_km2"]) for d in datas])
    m15 = np.array([float(furnas[d]["area_km2"]) for d in datas])
    m18 = np.array([float(furnas[d]["area_18db_km2"]) for d in datas])
    s15 = np.array([float(b0[d]["area_km2"]) for d in datas])
    d_esp, d15, ds15 = esperada - esperada[0], m15 - m15[0], s15 - s15[0]
    frac_funil = cobertura(args.funil) if funil else None

    colunas = ["data", "cota_ana_m", "volume_util_pct", "area_esperada_km2", "delta_esperado_km2",
               "area_nisar_bruta_km2", "area_nisar_poligono_m15_km2", "area_nisar_poligono_m18_km2",
               "delta_nisar_m15_km2", "area_nisar_poligono_sem_buffer_m15_km2", "delta_nisar_sem_buffer_m15_km2"]
    if funil:
        colunas += ["area_funil_m15_km2", "area_funil_m18_km2", "funil_cobertura_frac"]
    with open(os.path.join(args.saida, "serie.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(colunas)
        for i, d in enumerate(datas):
            linha_csv = [f"{d[:4]}-{d[4:6]}-{d[6:]}", cotas[i], cota[d]["volume_util_pct"],
                         round(esperada[i], 1), round(d_esp[i], 1), bruta[i], m15[i], m18[i],
                         round(d15[i], 1), s15[i], round(ds15[i], 1)]
            if funil:
                linha_csv += [funil[d]["area_km2"], funil[d]["area_18db_km2"], frac_funil]
            w.writerow(linha_csv)

    rotulos = [f"{d[6:]}/{d[4:6]}" for d in datas]
    x = np.arange(len(datas))
    vento = np.array([d in DATAS_VENTO for d in datas])

    # --- áreas (esquerda) + cota (direita), a pedido ---
    fig, ax = plt.subplots(figsize=(11, 6))
    linha(ax, x, bruta, COR_BRUTA, "NISAR bruta (sem polígono)")
    linha(ax, x, m15, COR_M15, "NISAR polígono + 500 m, −15,6 dB")
    linha(ax, x, s15, COR_B0, "NISAR polígono sem buffer, −15,6 dB")
    linha(ax, x, m18, COR_M18, "NISAR polígono + 500 m, −18 dB")
    linha(ax, x, esperada, COR_ESP, "área esperada (curva cota×área ANA)", ls="--")
    ax.set_ylabel("área (km²)", color=TINTA)
    ax.set_ylim(0, max(bruta.max(), esperada.max()) * 1.1)
    estilo(ax)
    ax2 = ax.twinx()
    linha(ax2, x, cotas, COR_COTA, "cota ANA (eixo direito)", ls=":", marcador="s")
    ax2.set_ylabel("cota de Furnas, ANA (m)", color=TINTA)
    ax2.set_ylim(cotas.min() - 2.5, cotas.max() + 0.3)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_color("#bbbbbb")
    ax2.tick_params(colors=TINTA_2)
    for i in np.nonzero(vento)[0]:
        ax.annotate("vento?", (i, m18[i]), xytext=(0, -16), textcoords="offset points",
                    ha="center", fontsize=8, color=TINTA_2)
    ax.set_xticks(x, rotulos)
    l1, n1 = ax.get_legend_handles_labels()
    l2, n2 = ax2.get_legend_handles_labels()
    ax.legend(l1 + l2, n1 + n2, frameon=False, loc="lower left", fontsize=9)
    ax.set_title("Furnas 2026: área de água NISAR × área esperada pela cota (ANA)", loc="left", color=TINTA)
    fig.tight_layout()
    fig.savefig(os.path.join(args.saida, "grafico_series.png"), dpi=130)
    plt.close(fig)

    # --- deltas em relação a 27/06, mesmo eixo ---
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.axhline(0, color="#999999", lw=1)
    linha(ax, x, d_esp, COR_ESP, "Δ esperado (curva ANA)", ls="--")
    linha(ax, x, d15, COR_M15, "Δ NISAR polígono + 500 m")
    linha(ax, x, ds15, COR_B0, "Δ NISAR polígono sem buffer")
    for i in np.nonzero(vento)[0]:
        ax.annotate("vento?", (i, min(d15[i], ds15[i])), xytext=(0, -16), textcoords="offset points",
                    ha="center", fontsize=8, color=TINTA_2)
    ax.set_xticks(x, rotulos)
    ax.set_ylabel(f"variação de área desde {rotulos[0]} (km²)", color=TINTA)
    estilo(ax)
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    ax.set_title("Furnas 2026: variação de área, NISAR × esperado pela cota", loc="left", color=TINTA)
    fig.tight_layout()
    fig.savefig(os.path.join(args.saida, "grafico_deltas.png"), dpi=130)
    plt.close(fig)

    # --- dispersão cota × área, r e inclinação vs. curva ANA ---
    faixa = (tab_c >= cotas.min()) & (tab_c <= cotas.max())
    incl_ana = np.polyfit(tab_c[faixa], tab_a[faixa], 1)[0] * frac
    met = {}
    for nome, y in (("m15", m15), ("sem_buffer", s15), ("m18", m18), ("bruta", bruta)):
        for rot, sel in (("todas", np.ones_like(vento)), ("sem_vento", ~vento)):
            met[f"r_{nome}_{rot}"] = np.corrcoef(cotas[sel], y[sel])[0, 1]
            met[f"incl_{nome}_{rot}"] = np.polyfit(cotas[sel], y[sel], 1)[0]
    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    cc = np.linspace(cotas.min() - 0.05, cotas.max() + 0.05, 20)
    ax.plot(cc, np.interp(cc, tab_c, tab_a) * frac, color=COR_ESP, ls="--", lw=1.5,
            label=f"curva ANA ({incl_ana:.0f} km²/m)")
    for y, cor, nome, chave in ((m15, COR_M15, "polígono + 500 m", "m15"), (s15, COR_B0, "sem buffer", "sem_buffer")):
        ax.scatter(cotas[~vento], y[~vento], s=60, color=cor, edgecolor="white", lw=1.5, zorder=3,
                   label=f"NISAR {nome}: r={met[f'r_{chave}_sem_vento']:+.2f}, "
                         f"{met[f'incl_{chave}_sem_vento']:.0f} km²/m (sem vento)")
        ax.scatter(cotas[vento], y[vento], s=60, facecolor="white", edgecolor=cor, lw=2, zorder=3)
        a, b = np.polyfit(cotas[~vento], y[~vento], 1)
        ax.plot(cc, a * cc + b, color=cor, lw=1.2, alpha=0.8)
    for c, a, r in zip(cotas, s15, rotulos):
        ax.annotate(r, (c, a), xytext=(6, -10), textcoords="offset points", fontsize=8, color=TINTA_2)
    ax.scatter([], [], s=60, facecolor="white", edgecolor=TINTA_2, lw=2, label="datas com vento (fora do ajuste)")
    ax.set_xlabel("cota de Furnas, ANA (m)", color=TINTA)
    ax.set_ylabel("área de água (km²)", color=TINTA)
    ax.set_title(f"Cota × área   (com as 9 datas: r = {met['r_m15_todas']:+.2f} / {met['r_sem_buffer_todas']:+.2f})",
                 loc="left", color=TINTA, fontsize=11)
    estilo(ax)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(args.saida, "dispersao_cota_area.png"), dpi=130)
    plt.close(fig)

    # --- mapas: máscaras 27/06 e 13/10 com o polígono oficial por cima ---
    npz = np.load(os.path.join(args.furnas, "dados_mudanca.npz"))
    antes, depois, pol = npz["antes"], npz["depois"], npz["poligono"]
    d0, d1 = (str(d) for d in npz["datas"])
    pixel_km2 = abs(npz["x"][1] - npz["x"][0]) ** 2 / 1e6
    fig, axs = plt.subplots(1, 2, figsize=(14, 7.4))
    for a, m, d in zip(axs, (antes, depois), (d0, d1)):
        a.imshow(np.where(m, 1.0, np.nan), cmap="Blues", vmin=0, vmax=1.2, interpolation="nearest")
        a.contour(pol, levels=[0.5], colors=[COR_COTA], linewidths=0.5)
        a.set_title(f"{d[6:]}/{d[4:6]}/{d[:4]}: {m.sum() * pixel_km2:.0f} km²", color=TINTA)
        a.axis("off")
    fig.suptitle("Água NISAR (azul, −15,6 dB, polígono + 500 m) e limite oficial ANA a 768 m (laranja)",
                 color=TINTA)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(args.saida, "agua_27jun_vs_13out.png"), dpi=110)
    plt.close(fig)

    rgb = np.ones(antes.shape + (3,))
    rgb[antes & depois] = (0.75, 0.85, 0.95)
    rgb[antes & ~depois] = (0.85, 0.20, 0.15)
    rgb[~antes & depois] = (0.10, 0.30, 0.85)
    fig, ax = plt.subplots(figsize=(10, 9.5))
    ax.imshow(rgb, interpolation="nearest")
    ax.contour(pol, levels=[0.5], colors=["#999999"], linewidths=0.4)
    ax.set_title(f"Furnas {d0[6:]}/{d0[4:6]} → {d1[6:]}/{d1[4:6]}: vermelho = secou "
                 f"({(antes & ~depois).sum() * pixel_km2:.0f} km²), azul escuro = virou água "
                 f"({(~antes & depois).sum() * pixel_km2:.0f} km²); cinza = limite ANA",
                 color=TINTA, fontsize=10)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(os.path.join(args.saida, "mudanca_corrigida.png"), dpi=130)
    plt.close(fig)

    if args.previa and os.path.exists(args.previa):
        shutil.copy(args.previa, args.saida)

    # --- métricas para o RESUMO ---
    linhas = [f"cobertura do polígono de Furnas (dado válido em todas as datas): {frac:.1%}",
              f"cobertura do polígono do Funil: {frac_funil:.1%}" if funil else "Funil: sem dados",
              f"inclinação da curva ANA em {cotas.min():.2f}-{cotas.max():.2f} m: {incl_ana:.1f} km²/m"]
    for nome, y, dy in (("polígono + 500 m −15,6", m15, d15), ("sem buffer −15,6", s15, ds15),
                        ("polígono + 500 m −18", m18, m18 - m18[0])):
        for rot, sel in (("9 datas", np.ones_like(vento)), ("sem vento", ~vento)):
            dif = y[sel] - esperada[sel]
            ddif = dy[sel] - d_esp[sel]
            linhas.append(f"{nome} [{rot}]: erro abs médio {abs(dif).mean():.1f} km² "
                          f"({(abs(dif) / esperada[sel]).mean():.1%}), viés {dif.mean():+.1f} km², "
                          f"desvio padrão das diferenças {dif.std(ddof=1):.1f} km²; "
                          f"Δ: erro abs médio {abs(ddif).mean():.1f} km², r(Δ) {np.corrcoef(dy[sel], d_esp[sel])[0, 1]:+.2f}")
    linhas += [f"{k}: {v:+.3f}" for k, v in met.items()]
    linhas.append(f"amplitude: esperada {np.ptp(esperada):.1f} | +500 m {np.ptp(m15):.1f} "
                  f"(sem vento {np.ptp(m15[~vento]):.1f}) | sem buffer {np.ptp(s15):.1f} (sem vento {np.ptp(s15[~vento]):.1f})")
    for i, d in enumerate(datas):
        linhas.append(f"{d} cota {cotas[i]:.2f} esp {esperada[i]:7.1f} Δesp {d_esp[i]:+6.1f} | +500 {m15[i]:7.1f} "
                      f"Δ {d15[i]:+6.1f} | b0 {s15[i]:7.1f} Δ {ds15[i]:+6.1f} | −18 {m18[i]:6.1f}"
                      + (f" | funil {funil[d]['area_km2']}" if funil else ""))
    with open(os.path.join(args.saida, "metricas.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
