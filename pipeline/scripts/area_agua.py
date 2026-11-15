"""Série de área de água (método de Furnas). Linha de comando fina sobre arara_pipeline.furnas.

    python pipeline/scripts/area_agua.py [pasta_h5] --poligono <.gdb|.shp|.geojson> --buffer 0 --limiar -15.65 --saida <dir>

Sem pasta, usa a variável de ambiente FURNAS_H5_DIR.
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from arara_pipeline.furnas import *  # noqa: E402,F401,F403
from arara_pipeline.furnas import BUFFER_POLIGONO_M, data_do_nome, epsg_do_h5, ler_poligono, processar  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", nargs="?", default=os.environ.get("FURNAS_H5_DIR"),
                    help="pasta com os .h5 (padrão: variável FURNAS_H5_DIR)")
    ap.add_argument("--saida", default="outputs", help="pasta de saída (padrão: outputs)")
    ap.add_argument("--poligono", help="limite de referência: .shp, .geojson ou .gdb ('arquivo.gdb::camada'); "
                                       "sem ele, usa a zona derivada das datas")
    ap.add_argument("--limiar", type=float, help="limiar em dB (padrão: calculado na 1ª data)")
    ap.add_argument("--buffer", type=float, default=BUFFER_POLIGONO_M,
                    help=f"buffer (m) para fora do polígono (padrão: {BUFFER_POLIGONO_M:.0f})")
    args = ap.parse_args()
    if not args.pasta:
        raise SystemExit("Informe a pasta dos .h5 ou defina FURNAS_H5_DIR.")
    arquivos = sorted(glob.glob(os.path.join(args.pasta, "*.h5")), key=data_do_nome)
    if not arquivos:
        raise SystemExit("Nenhum .h5 encontrado na pasta.")
    print(f"{len(arquivos)} arquivos")
    poligono = ler_poligono(args.poligono, epsg_do_h5(arquivos[0])) if args.poligono else None
    processar(arquivos, args.saida, poligono=poligono, limiar=args.limiar, buffer_m=args.buffer)


if __name__ == "__main__":
    main()
