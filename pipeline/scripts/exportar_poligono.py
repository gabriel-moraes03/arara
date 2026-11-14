"""Costura o limite do reservatório (GDB da ANA/SNIRH ou .shp) e grava em GeoJSON lon/lat, sem simplificar.

    python pipeline/scripts/exportar_poligono.py <Furnas.gdb> data/ana/furnas_poligono.geojson [--epsg 32723]

O GeoJSON gerado é o polígono de referência da regressão de Furnas (o .gdb não é versionado).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from arara_pipeline.geom import ler_poligono, salvar_poligono_geojson  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("origem")
ap.add_argument("destino")
ap.add_argument("--epsg", type=int, default=32723, help="EPSG métrico usado na costura (padrão: UTM 23S)")
ap.add_argument("--nome", default="UHE Furnas: limite do reservatório (ANA/SNIRH, cota 768,0 m de operação)")
args = ap.parse_args()
aneis = ler_poligono(args.origem, args.epsg)
salvar_poligono_geojson(aneis, args.epsg, args.destino,
                        {"nome": args.nome, "fonte": os.path.basename(args.origem), "aneis": len(aneis)})
print(f"{len(aneis)} anéis -> {args.destino}")
