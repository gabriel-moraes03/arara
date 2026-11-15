"""
Converte a planilha CAV (cota × área × volume) da ANA/SNIRH para CSV com cota_m,area_km2.

Rodar (da raiz):
    python scripts/converter_cav.py "data/ana/furnas/UHE Furnas CAV SNIRH.xlsx" data/ana/furnas_cota_area.csv
    python scripts/converter_cav.py "data/ana/funil/UHE Funil - CAV SNIRH.xlsx" data/ana/funil_cota_area.csv

Usa a folha "Curvas Atualizadas" e a coluna A como cota_m. Em Furnas a coluna A é a "Cota de
Operação", a mesma referência dos boletins ANA/ONS; a coluna B é a cota SGB (= operação + 0,2 m).
Lê o .xlsx só com a biblioteca padrão (é um zip de XML).
"""
import argparse
import csv
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def ler_xlsx(caminho):
    """{nome_da_folha: [(nº da linha, {coluna: texto})]}"""
    z = zipfile.ZipFile(caminho)
    textos = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            textos.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    alvo = {r.get("Id"): r.get("Target").lstrip("/") for r in rels}
    folhas = {}
    for s in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
        arq = alvo[s.get(f"{{{NS['r']}}}id")]
        arq = arq if arq.startswith("xl/") else "xl/" + arq
        linhas = []
        for row in ET.fromstring(z.read(arq)).iter(f"{{{NS['m']}}}row"):
            celulas = {}
            for c in row.findall("m:c", NS):
                col = re.match(r"[A-Z]+", c.get("r")).group()
                v = c.find("m:v", NS)
                if c.get("t") == "inlineStr":
                    celulas[col] = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
                elif v is not None:
                    celulas[col] = textos[int(v.text)] if c.get("t") == "s" else v.text
            linhas.append((int(row.get("r")), celulas))
        folhas[s.get("name")] = linhas
    return folhas


def curva_cota_area(caminho, folha="Curvas Atualizadas"):
    """[(cota_m, area_km2)] em ordem de cota, só as linhas numéricas das colunas A e C."""
    pares = []
    for _, c in ler_xlsx(caminho)[folha]:
        try:
            pares.append((round(float(c["A"]), 3), float(c["C"])))
        except (KeyError, ValueError):
            continue
    return sorted(set(pares))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsx")
    ap.add_argument("csv")
    args = ap.parse_args()
    pares = curva_cota_area(args.xlsx)
    with open(args.csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cota_m", "area_km2"])
        w.writerows((c, round(a, 4)) for c, a in pares)
    print(f"{len(pares)} pontos, cota {pares[0][0]} a {pares[-1][0]} m -> {args.csv}")


if __name__ == "__main__":
    main()
