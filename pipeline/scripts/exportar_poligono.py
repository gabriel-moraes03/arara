"""Costura o limite do reservatório (GDB da ANA/SNIRH ou .shp) e grava em GeoJSON lon/lat, sem simplificar.

    python pipeline/scripts/exportar_poligono.py <Furnas.gdb> data/ana/furnas_poligono.geojson [--epsg 32723]

Quando a camada 'Reservatório' não está no nível máximo normal (Barra Grande: é a curva de 651,14 m,
o máximo maximorum), use a isóbata do mesmo GDB nessa cota:

    python pipeline/scripts/exportar_poligono.py "Barra Grande.gdb::Isóbatas" saida.geojson --cota 647 --epsg 32722

O GeoJSON gerado é o polígono de referência da regressão (o .gdb não é versionado).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from arara_pipeline.geom import costurar_linhas, linhas_do_wkb, ler_poligono, salvar_poligono_geojson  # noqa: E402


def isobata(origem, cota, epsg_destino):
    """Anéis da isóbata `cota` (campo Contour/CONTOUR) de uma camada de linhas do GDB."""
    import warnings
    import numpy as np
    from pyogrio.raw import read
    from pyproj import CRS, Transformer

    caminho, _, camada = origem.partition("::")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        meta, _, geometrias, campos = read(caminho, layer=camada)
    nomes = [n.lower() for n in meta["fields"]]
    cotas = np.asarray(campos[nomes.index("contour")], float)
    linhas = [l for g, c in zip(geometrias, cotas) if abs(c - cota) < 0.01 for l in linhas_do_wkb(g)]
    aneis, folga = costurar_linhas(linhas)
    print(f"isóbata {cota} m: {len(linhas)} linhas -> {len(aneis)} anéis (maior folga costurada {folga:.0f} m)")
    origem_crs = CRS.from_user_input(meta["crs"])
    if origem_crs.is_compound:
        origem_crs = origem_crs.sub_crs_list[0]
    t = Transformer.from_crs(origem_crs, CRS.from_epsg(epsg_destino), always_xy=True)
    return [np.column_stack(t.transform(a[:, 0], a[:, 1])) for a in aneis]


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("origem")
ap.add_argument("destino")
ap.add_argument("--epsg", type=int, default=32723, help="EPSG métrico usado na costura (padrão: UTM 23S)")
ap.add_argument("--cota", type=float, help="usa a isóbata nessa cota (camada de linhas com campo Contour)")
ap.add_argument("--nome", default="UHE Furnas: limite do reservatório (ANA/SNIRH, cota 768,0 m de operação)")
args = ap.parse_args()
aneis = isobata(args.origem, args.cota, args.epsg) if args.cota is not None else ler_poligono(args.origem, args.epsg)
salvar_poligono_geojson(aneis, args.epsg, args.destino,
                        {"nome": args.nome, "fonte": os.path.basename(args.origem.split("::")[0]), "aneis": len(aneis)})
print(f"{len(aneis)} anéis -> {args.destino}")
