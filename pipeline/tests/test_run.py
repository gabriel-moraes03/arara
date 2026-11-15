"""Pipeline de ponta a ponta com cenas GCOV sintéticas no disco (o mesmo caminho das cenas locais)."""
import json

import numpy as np
import pytest
from shapely.geometry import mapping

from arara_pipeline import run
from gcov_sintetico import aoi_lonlat, disco, escrever, nome

N = 500
DATAS = ["20260627", "20260709", "20260721", "20260802"]
RAIOS = [150, 148, 144, 138]


@pytest.fixture(scope="module")
def analise(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("cenas")
    arquivos = [escrever(pasta / nome(d), disco(N, r), semente=i) for i, (d, r) in enumerate(zip(DATAS, RAIOS))]
    saida = tmp_path_factory.mktemp("saida")
    spec = {"analysis_id": "teste", "aoi": mapping(aoi_lonlat(N, 60)), "local_scenes": arquivos, "optical": False,
            "terrain": False, "rain": False, "exposure": False}
    (saida / "spec.json").write_text(json.dumps(spec))
    return saida, spec


def test_ponta_a_ponta(analise, capsys):
    saida, _ = analise
    assert run.main(["--spec", str(saida / "spec.json"), "--out", str(saida)]) == 0
    linhas = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert {"stage", "progress", "message"} <= set(linhas[0]) and linhas[-1]["progress"] == 1.0
    assert [l["stage"] for l in linhas if l["stage"] in ("acquire", "classify", "compare", "publish")]
    r = json.loads((saida / "result.json").read_text(encoding="utf-8"))
    assert r["status"] == "completed" and not r["experimental"]
    assert [d["date"] for d in r["dates"]] == ["2026-06-27", "2026-07-09", "2026-07-21", "2026-08-02"]
    for d, raio in zip(r["dates"], RAIOS):
        assert d["water_km2"] == pytest.approx(np.pi * raio ** 2 * 400 / 1e6, rel=0.02)
        assert d["crid"] == "P05023" and d["suspeita_vento"] is False
    c = r["comparison"]
    assert c["retraction_ha"] > 0 and c["net_change_ha"] == pytest.approx(
        (r["dates"][-1]["water_km2"] - r["dates"][0]["water_km2"]) * 100, abs=0.5)
    assert r["optical_validation"]["status"] == "not_optically_validated"
    assert r["forecast"]["status"] == "ok" and r["forecast"]["experimental"] and len(r["forecast"]["points"]) == 3
    assert r["insights"]["measured"] and r["insights"]["hypothesis"] and r["insights"]["confidence"] in ("baixa", "média")
    for sub in ("cog/water_20260627.tif", "cog/hh_db_20260802.tif", "cog/change.tif", "png/change.png",
                "metrics.json", "metrics.csv", "sources.json"):
        assert (saida / sub).exists(), sub
    camada = next(l for l in r["layers"] if l["id"] == "change")
    assert camada["bounds"]["west"] < camada["bounds"]["east"] and list((saida / "tiles" / "change").rglob("*.png"))
    fontes = json.loads((saida / "sources.json").read_text(encoding="utf-8"))
    assert len(fontes["scenes"]) == 4 and fontes["scenes"][0]["window"]["row_stop"] <= N
    assert "EARTHDATA" not in (saida / "sources.json").read_text(encoding="utf-8")
    # modo cheia: o disco encolhe, então a passagem mais seca é a última; a primeira tem o anel de 150 a
    # 138 px além dela, menos a tolerância de 2 px na margem da referência
    fl = r["flood"]
    assert fl["status"] == "ok" and fl["reference_date"] == "2026-08-02" and fl["terrain"] is None
    assert fl["per_date"][0]["flood_km2"] == pytest.approx(np.pi * (150 ** 2 - 140 ** 2) * 400 / 1e6, rel=0.1)
    assert fl["per_date"][-1]["flood_km2"] == 0 and fl["peak_date"] == "2026-06-27"
    assert r["dates"][0]["flood_km2"] == fl["per_date"][0]["flood_km2"]
    assert any("HAND desligado" in x for x in fl["limitations"])
    assert r["rain"]["status"] == "unavailable" and r["municipalities"]["status"] == "unavailable"
    assert all(d["confidence"]["level"] in ("média", "baixa") for d in r["dates"])   # sem HAND: nunca alta
    assert "Em 27/06/2026 o radar viu" in r["summary_text"]["text"]
    assert any(l["type"] == "flood" for l in r["layers"])


def test_area_grande_demais_fica_indisponivel(tmp_path):
    spec = {"analysis_id": "x", "aoi": {"type": "Polygon", "coordinates": [[[-58, -19], [-56, -19], [-56, -17], [-58, -17], [-58, -19]]]}}
    (tmp_path / "spec.json").write_text(json.dumps(spec))
    assert run.main(["--spec", str(tmp_path / "spec.json"), "--out", str(tmp_path)]) == 0
    r = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert r["status"] == "unavailable" and "limite" in r["reason"]


def test_area_fora_das_cenas_fica_indisponivel(analise, tmp_path):
    _, spec = analise
    fora = dict(spec, aoi={"type": "Polygon", "coordinates": [[[10, 45], [10.1, 45], [10.1, 45.1], [10, 45.1], [10, 45]]]})
    (tmp_path / "spec.json").write_text(json.dumps(fora))
    run.main(["--spec", str(tmp_path / "spec.json"), "--out", str(tmp_path)])
    r = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert r["status"] == "unavailable" and "fora da grade" in r["reason"]
