"""Estado de qualidade (2.1) e validação óptica robusta (2.2)."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest
from shapely.geometry import box, mapping

from arara_pipeline import optical_stage, quality, run
from gcov_sintetico import aoi_lonlat, disco, escrever, nome

N = 500
DATAS = ["20260627", "20260709", "20260721", "20260802"]


def faixas(n, semente):
    """Pasto/eucalipto: metade da área mais lisa (-12,5 dB) e metade mais rugosa, sem lago nenhum."""
    rng = np.random.default_rng(semente)
    yy, xx = np.mgrid[:n, :n]
    return ((xx // 40 + yy // 50 + rng.integers(0, 2)) % 2).astype(bool)


def rodar(tmp_path, arquivos):
    spec = {"analysis_id": "q", "aoi": mapping(aoi_lonlat(N, 60)), "local_scenes": arquivos, "optical": False}
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    assert run.main(["--spec", str(tmp_path / "spec.json"), "--out", str(tmp_path)]) == 0
    return json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))


def test_area_sem_margem_agua_terra_nao_publica_agua(tmp_path):
    cenas = tmp_path / "cenas"
    cenas.mkdir()
    arquivos = [escrever(cenas / nome(d), faixas(N, i), agua_db=-12.5, semente=i) for i, d in enumerate(DATAS)]
    (tmp_path / "saida").mkdir()
    r = rodar(tmp_path / "saida", arquivos)
    assert r["status"] == "completed"
    assert r["quality"] == "no_reliable_water" and r["quality_reasons"] and r["what_to_try"]
    assert any("margem" in m for m in r["quality_reasons"])
    for d in r["dates"]:
        assert d["water_km2"] is None and d["water_pct"] is None and d["suspeita_vento"] is None
        assert d["granule"] and d["crid"]
    assert r["comparison"] is None and r["patterns"] is None and r["forecast"] is None and r["insights"] is None
    assert not any("vento" in w for w in r["warnings"])
    tipos = {l["type"] for l in r["layers"]}
    assert tipos == {"backscatter"}
    saida = tmp_path / "saida"
    assert not list((saida / "cog").glob("water_*.tif")) and list((saida / "cog").glob("hh_db_*.tif"))
    m = json.loads((saida / "metrics.json").read_text(encoding="utf-8"))
    assert m["quality"] == "no_reliable_water" and all(d["water_km2"] is None for d in m["dates"])


def test_lago_nitido_sai_confiavel(tmp_path):
    cenas = tmp_path / "cenas"
    cenas.mkdir()
    arquivos = [escrever(cenas / nome(d), disco(N, r), semente=i) for i, (d, r) in enumerate(zip(DATAS, [150, 148, 144, 138]))]
    (tmp_path / "saida").mkdir()
    r = rodar(tmp_path / "saida", arquivos)
    assert r["quality"] == "reliable" and r["quality_reasons"] == [] and not r["experimental"]
    assert r["dates"][-1]["water_km2"] > 0 and r["forecast"]["status"] == "ok" and r["patterns"]["trend"]["status"] == "ok"


def cls_falso(n=4, margem=12, limiar=-16.0, fracao=0.2):
    return {"threshold": {"source": "limiar_bimodal", "date_index": 0}, "margin_blocks": [margem] * n,
            "threshold_db": limiar, "water_fraction": [fracao] * n, "experimental_reasons": []}


def test_regras_de_qualidade():
    assert quality.avaliar(cls_falso())["quality"] == "reliable"
    assert quality.avaliar(cls_falso(margem=0))["quality"] == "no_reliable_water"
    assert quality.avaliar(cls_falso(limiar=-11.2))["quality"] == "no_reliable_water"
    assert quality.avaliar(cls_falso(fracao=0.95))["quality"] == "no_reliable_water"
    c = cls_falso()
    c["water_fraction"] = [0.2, 0.2, 0.2, 0.95]
    assert quality.avaliar(c)["quality"] == "experimental"
    forte = {"mean_iou": 0.0, "divergence": {"level": "strong", "n_strong": 3, "n_moderate": 0, "n_dates": 4}}
    assert quality.avaliar(cls_falso(), forte)["quality"] == "no_reliable_water"
    # data com vento (marcada) não rebaixa a análise: a água dela já é sabidamente subestimada
    c = cls_falso()
    c["water_fraction"], c["wind"] = [0.2, 0.004, 0.2, 0.2], [False, True, False, False]
    assert quality.avaliar(c)["quality"] == "reliable"
    linhas = quality.divergencia([
        {"date": "a", "status": "validated", "compared_km2": 100, "sar_water_km2": 20, "optical_water_km2": 19, "iou": 0.9},
        {"date": "b", "status": "validated", "compared_km2": 100, "sar_water_km2": 1, "optical_water_km2": 19, "iou": 0.0, "suspeita_vento": True},
        {"date": "c", "status": "validated", "compared_km2": 100, "sar_water_km2": 21, "optical_water_km2": 19, "iou": 0.9},
        {"date": "d", "status": "validated", "compared_km2": 100, "sar_water_km2": 19, "optical_water_km2": 19, "iou": 0.9}])
    assert [x["level"] for x in linhas] == ["none", "wind", "none", "none"]
    assert quality.resumo_divergencia(linhas, 0.9) == {"level": "none", "n_dates": 3, "n_strong": 0, "n_moderate": 0, "per_date": linhas}
    moderada = {"mean_iou": 0.62, "divergence": {"level": "moderate", "n_strong": 0, "n_moderate": 3, "n_dates": 4}}
    q = quality.avaliar(cls_falso(), moderada)
    assert q["quality"] == "experimental" and "Sentinel-2" in q["reasons"][0]


# ---------- 2.2: validação óptica ----------

def contexto(agua_radar, n_datas=3):
    m = np.zeros((60, 60), bool)
    m[10:50, 10:50] = True
    aguas = [agua_radar.copy() for _ in range(n_datas)]
    datas = [{"date": f"2026-07-{10 + 12 * i:02d}", "suspeita_vento": False} for i in range(n_datas)]
    return {"spec": {}, "aoi": box(-40.5, -17.9, -40.4, -17.8), "xs": np.arange(60) * 20.0, "ys": -np.arange(60) * 20.0,
            "epsg": 32724, "pixel_m": 20.0, "area_px": 400.0, "datas": datas,
            "cls": {"water": aguas, "common_valid": m}}


def referencia_falsa(agua_optica):
    def ref(geo, data, xs, ys, epsg, aoi_mask):
        return {"status": "ok", "water": agua_optica, "valid": np.ones_like(agua_optica), "date": data, "days_apart": 1,
                "clear_fraction": 1.0, "items": ["s2"], "cloud_cover_pct": [0.0], "processing_baseline": ["05.11"],
                "boa_offset_added": [0], "assets": {}}
    return ref


def test_optico_sem_agua_e_radar_com_agua_e_divergencia_forte():
    radar = np.zeros((60, 60), bool)
    radar[10:40, 10:50] = True                       # 75% da área "água" no radar
    ctx, extras = contexto(radar), {}
    optical_stage.rodar(ctx, extras, lambda *a: None, referencia=referencia_falsa(np.zeros((60, 60), bool)))
    v = extras["validacao"]
    assert v["status"] == "validated" and v["mean_recall"] is None and v["n_dates_per_metric"]["recall"] == 0
    assert v["mean_precision"] == 0.0 and v["divergence"]["level"] == "strong" and v["divergence"]["n_strong"] == 3
    linha = v["divergence"]["per_date"][0]
    assert linha["optical_water_fraction"] == 0.0 and linha["sar_water_fraction"] == pytest.approx(0.75)


def test_sem_agua_nos_dois_sensores_nao_divide_por_zero():
    vazio = np.zeros((60, 60), bool)
    ctx, extras = contexto(vazio), {}
    optical_stage.rodar(ctx, extras, lambda *a: None, referencia=referencia_falsa(vazio))
    v = extras["validacao"]
    assert v["status"] == "validated" and v["mean_iou"] is None and v["mean_precision"] is None
    assert v["divergence"]["level"] == "none"


def test_media_ignora_none():
    assert optical_stage.media([{"x": 0.5}, {"x": None}, {"x": 1.0}], "x") == (0.75, 2)
    assert optical_stage.media([{"x": None}], "x") == (None, 0)


def test_falha_na_etapa_optica_nao_mostra_traceback(monkeypatch, capsys):
    def explode(*a, **k):
        raise TypeError("unsupported operand type(s) for +: 'float' and 'NoneType'")
    monkeypatch.setattr(optical_stage, "rodar", explode)
    ctx = {"avisos": []}
    extras = run.etapas_opcionais(ctx, ("optical_stage",))
    assert extras["validacao"]["status"] == "not_optically_validated"
    assert ctx["avisos"] == ["validação óptica indisponível nesta análise (erro ao comparar com o Sentinel-2)"]
    assert "TypeError" not in json.dumps(extras, ensure_ascii=False) + " ".join(ctx["avisos"])
    assert "TypeError" in capsys.readouterr().err          # o detalhe fica no log do servidor


# ---------- 2.4: progresso em UTF-8 mesmo com stdout em pipe no Windows ----------

def test_progresso_sai_em_utf8(tmp_path):
    spec = {"analysis_id": "x", "aoi": {"type": "Polygon", "coordinates": [[[-58, -19], [-56, -19], [-56, -17], [-58, -17], [-58, -19]]]}}
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..")
    p = subprocess.run([sys.executable, "-m", "arara_pipeline.run", "--spec", str(tmp_path / "spec.json"), "--out", str(tmp_path)],
                       capture_output=True, env=env, timeout=120)
    texto = p.stdout.decode("utf-8")                   # estrito: falha se vier em cp1252
    assert "área de" in texto and "km²" in texto


# ---------- rodada 2: rótulo da tabela radar x Sentinel-2 ----------

def test_concordam_so_com_diferenca_pequena():
    def linha(sar, opt, vento=False):
        return {"date": "d", "status": "validated", "compared_km2": 100.0, "sar_water_km2": sar, "optical_water_km2": opt,
                "iou": 0.5, "suspeita_vento": vento}
    l = quality.divergencia([linha(24.7, 0.0, vento=True),     # Nanuque 21/07: era "concordam"
                             linha(20.0, 19.0), linha(22.0, 17.0), linha(19.6, 6.0), linha(1.0, 0.0)])
    assert [x["agreement"] for x in l] == ["optical_no_water", "agree", "diverge", "diverge", "agree"]
    assert l[0]["level"] == "wind" and l[0]["difference_pp"] == 24.7
    assert l[2]["level"] == "none" and l[2]["difference_pp"] == 5.0          # dentro dos 30%, mas 5 pontos: diverge
