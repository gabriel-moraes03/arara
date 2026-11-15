"""
Checagem da região "Delta do Jacuí e Guaíba" contra a régua oficial da ANA 87450020 (Usina do
Gasômetro, Porto Alegre): nível médio na hora de cada passagem NISAR × água de cheia (flood_km2).

    python pipeline/scripts/validar_regua_guaiba.py [--xml <resposta do ServiceANA>] [--servidor http://localhost:8081]

--xml: resposta de https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos?
       codEstacao=87450020&dataInicio=15/08/2026&dataFim=16/10/2026 ; vira data/ana/guaiba_gasometro_87450020.csv.
       Sem --xml, usa o CSV já salvo.
--servidor: lê o histórico da região (GET /api/arara/regions/guaiba/history?format=csv) e grava um retrato
       em regression/guaiba_regua/historico_guaiba.csv. Sem servidor no ar, usa o retrato salvo.

Fuso: a ANA recebe e publica a telemetria na hora de Brasília sem horário de verão (UTC-3), conforme
"Procedimentos para envio dos dados hidrológicos em tempo real das estações telemétricas" (ANA, rev. mar/2012).
A hora da passagem sai do nome da cena (início do imageamento, UTC). Janela: ±1 h em torno dela.
Saída: regression/guaiba_regua/comparacao.csv e resumo.txt.
"""
import argparse
import csv
import io
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV_REGUA = os.path.join(RAIZ, "data", "ana", "guaiba_gasometro_87450020.csv")
SAIDA = os.path.join(RAIZ, "regression", "guaiba_regua")
UTC_MENOS_3 = timedelta(hours=-3)
JANELA = timedelta(hours=1)


def xml_para_csv(caminho_xml):
    linhas = []
    for e in ET.parse(caminho_xml).getroot().iter("DadosHidrometereologicos"):
        g = lambda k: (e.findtext(k) or "").strip()
        local = datetime.strptime(g("DataHora"), "%Y-%m-%d %H:%M:%S")
        linhas.append([local.strftime("%Y-%m-%d %H:%M"), (local - UTC_MENOS_3).strftime("%Y-%m-%d %H:%M"),
                       g("Nivel"), g("Chuva")])
    linhas.sort()
    with open(CSV_REGUA, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["data_hora_brasilia", "data_hora_utc", "nivel_cm", "chuva_mm"])
        w.writerows(linhas)
    print(f"{len(linhas)} leituras -> {os.path.relpath(CSV_REGUA, RAIZ)}")


def historico(servidor):
    retrato = os.path.join(SAIDA, "historico_guaiba.csv")
    if servidor:
        with urllib.request.urlopen(servidor.rstrip("/") + "/api/arara/regions/guaiba/history?format=csv", timeout=60) as r:
            texto = r.read().decode("utf-8")
        with open(retrato, "w", newline="", encoding="utf-8") as f:
            f.write(texto)
    return list(csv.DictReader(open(retrato, encoding="utf-8")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml")
    ap.add_argument("--servidor")
    a = ap.parse_args()
    os.makedirs(SAIDA, exist_ok=True)
    if a.xml:
        xml_para_csv(a.xml)
    leituras = list(csv.DictReader(open(CSV_REGUA, encoding="utf-8")))
    regua = [(datetime.strptime(l["data_hora_utc"], "%Y-%m-%d %H:%M"), float(l["nivel_cm"])) for l in leituras if l["nivel_cm"]]
    chuva = [(datetime.strptime(l["data_hora_utc"], "%Y-%m-%d %H:%M"), float(l["chuva_mm"] or 0)) for l in leituras]
    soma = lambda hora, dias: round(sum(c for t, c in chuva if hora - timedelta(days=dias) <= t <= hora), 1)
    ini, fim = regua[0][0], regua[-1][0]

    linhas = []
    for h in historico(a.servidor):
        hora = datetime.strptime(h["granule"].split("_")[11], "%Y%m%dT%H%M%S")   # início da cena, UTC
        if not (ini <= hora <= fim):
            continue
        dentro = [n for t, n in regua if abs(t - hora) <= JANELA]
        linhas.append({"data": h["date"], "passagem_utc": hora.strftime("%H:%M"),
                       "passagem_brasilia": (hora + UTC_MENOS_3).strftime("%H:%M"),
                       "nivel_medio_cm": round(float(np.mean(dentro)), 1), "leituras": len(dentro),
                       "chuva_regua_3d_mm": soma(hora, 3), "chuva_regua_7d_mm": soma(hora, 7),
                       "flood_km2": float(h["flood_km2"]), "water_km2": float(h["water_km2"]),
                       "quality": h["quality"], "confidence": h["confidence"]})
    with open(os.path.join(SAIDA, "comparacao.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)

    nivel = np.array([l["nivel_medio_cm"] for l in linhas])
    cheia = np.array([l["flood_km2"] for l in linhas])
    r_todas = np.corrcoef(nivel, cheia)[0, 1]
    # divergência: a passagem cuja retirada mais aumenta o r (deixando as demais)
    sem = {l["data"]: np.corrcoef(np.delete(nivel, i), np.delete(cheia, i))[0, 1] for i, l in enumerate(linhas)}
    pior = max(sem, key=sem.get)
    a_inc, b_inc = np.polyfit(np.delete(nivel, [l["data"] for l in linhas].index(pior)),
                              np.delete(cheia, [l["data"] for l in linhas].index(pior)), 1)
    i_niv, i_che = int(np.argmax(nivel)), int(np.argmax(cheia))
    txt = [f"régua ANA 87450020 (Gasômetro): {ini:%d/%m/%Y %H:%M} a {fim:%d/%m/%Y %H:%M} UTC, {len(regua)} leituras",
           f"passagens no período: {len(linhas)}; janela ±1 h, nível médio da régua × flood_km2",
           f"r (todas as {len(linhas)}): {r_todas:+.2f}",
           f"r sem {pior} ({len(linhas) - 1} passagens): {sem[pior]:+.2f}; inclinação {a_inc:.2f} km²/cm",
           "r tirando cada passagem: " + ", ".join(f"{d} {v:+.2f}" for d, v in sem.items()),
           f"maior nível: {linhas[i_niv]['data']} ({nivel[i_niv]:.0f} cm); maior flood_km2: {linhas[i_che]['data']} ({cheia[i_che]:.1f} km²)"]
    for l in linhas:
        prev = a_inc * l["nivel_medio_cm"] + b_inc
        txt.append(f"{l['data']} {l['passagem_brasilia']} BRT  nível {l['nivel_medio_cm']:6.1f} cm ({l['leituras']} leituras)  "
                   f"flood {l['flood_km2']:6.1f} km²  (reta das outras: {prev:6.1f}; resíduo {l['flood_km2'] - prev:+6.1f})  "
                   f"chuva na régua 3 d {l['chuva_regua_3d_mm']:5.1f} mm")
    open(os.path.join(SAIDA, "resumo.txt"), "w", encoding="utf-8").write("\n".join(txt) + "\n")
    print("\n".join(txt))


if __name__ == "__main__":
    main()
