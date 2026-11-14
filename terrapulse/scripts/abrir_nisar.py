"""
Abre um arquivo NISAR GCOV (.h5), mostra o que tem dentro e gera imagens de pré-visualização.

Rodar (da raiz do projeto):
    python scripts/abrir_nisar.py data/raw/nisar/NISAR_L2_PR_GCOV_....h5 [--saida outputs]

Saída:
    - lista dos arrays do arquivo (nome, tamanho, tipo)
    - códigos da camada mask (np.unique numa janela central)
    - previa_HH.png, previa_HV.png e previa_colorida.png em --saida
"""
import argparse
import os
import h5py
import numpy as np
import matplotlib.pyplot as plt

PASSO = 10  # lê 1 a cada 10 pixels: imagem leve, bom para olhar rápido
GRADE = "/science/LSAR/GCOV/grids/frequencyA"
JANELA_MASK = 2000  # lado (px) da janela onde se lê a mask com passo 1

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("arquivo", help="arquivo .h5 NISAR GCOV")
ap.add_argument("--saida", default="outputs", help="pasta onde salvar as prévias (padrão: outputs)")
args = ap.parse_args()
os.makedirs(args.saida, exist_ok=True)

with h5py.File(args.arquivo, "r") as h:
    # 1) O que tem dentro do arquivo
    print("=== Arrays em", GRADE, "===")
    for nome, obj in h[GRADE].items():
        if isinstance(obj, h5py.Dataset):
            print(f"  {nome:28s} shape={obj.shape}  dtype={obj.dtype}")

    g = h[GRADE]

    # 2) Onde fica no mapa (coordenadas da grade, em metros, na projeção do arquivo)
    x = g["xCoordinates"][:]
    y = g["yCoordinates"][:]
    proj = g["projection"]
    epsg = proj.attrs.get("epsg_code", proj[()])
    print(f"\nProjeção (EPSG): {epsg}")
    print(f"x: {x.min():.0f} a {x.max():.0f} m | y: {y.min():.0f} a {y.max():.0f} m")
    print(f"Tamanho do pixel: {abs(x[1] - x[0]):.1f} m")

    # 3) Códigos de validade da mask: resolução cheia numa janela central + imagem toda com passo
    if "mask" in g:
        m = g["mask"]
        print(f"\nmask: shape={m.shape} dtype={m.dtype} attrs={dict(m.attrs)}")
        r0, c0 = (m.shape[0] - JANELA_MASK) // 2, (m.shape[1] - JANELA_MASK) // 2
        jan = m[r0:r0 + JANELA_MASK, c0:c0 + JANELA_MASK]
        cod, n = np.unique(jan, return_counts=True)
        print(f"np.unique(mask) janela central {JANELA_MASK}x{JANELA_MASK}:", dict(zip(cod.tolist(), n.tolist())))
        cod, n = np.unique(m[::PASSO, ::PASSO], return_counts=True)
        print(f"np.unique(mask) imagem toda (passo {PASSO}):", dict(zip(cod.tolist(), n.tolist())))

    # 4) Ler os canais com passo (não carrega os GB inteiros na memória)
    def ler_db(canal):
        if canal not in g:
            return None
        valor = g[canal][::PASSO, ::PASSO].astype("float32")  # gama-zero, potência linear
        valor[valor <= 0] = np.nan
        return 10 * np.log10(valor)  # para dB

    hh = ler_db("HHHH")
    hv = ler_db("HVHV")


def salvar(img, nome, titulo, vmin, vmax):
    nome = os.path.join(args.saida, nome)
    plt.figure(figsize=(10, 10))
    plt.imshow(img, cmap="gray", vmin=vmin, vmax=vmax)
    plt.colorbar(label="dB")
    plt.title(titulo)
    plt.axis("off")
    plt.savefig(nome, dpi=120, bbox_inches="tight")
    plt.close()
    print("salvo:", nome)


def esticar(a, vmin, vmax):
    return np.clip((a - vmin) / (vmax - vmin), 0, 1)


if hh is not None:
    salvar(hh, "previa_HH.png", "HH em dB (água = escuro)", -25, 0)
if hv is not None:
    salvar(hv, "previa_HV.png", "HV em dB (vegetação = mais claro)", -30, -5)
if hh is not None and hv is not None:
    # vermelho = HH, verde = HV, azul = HH - HV (razão em dB)
    rgb = np.dstack([
        esticar(hh, -25, 0),
        esticar(hv, -30, -5),
        esticar(hh - hv, 0, 15),
    ])
    rgb = np.nan_to_num(rgb)
    nome = os.path.join(args.saida, "previa_colorida.png")
    plt.figure(figsize=(10, 10))
    plt.imshow(rgb)
    plt.title("Composição colorida: R=HH, G=HV, B=HH/HV")
    plt.axis("off")
    plt.savefig(nome, dpi=120, bbox_inches="tight")
    plt.close()
    print("salvo:", nome)
