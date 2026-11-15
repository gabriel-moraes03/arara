"""Vitrine estática (2.6): o exportador copia o mesmo frontend, liga o modo estático e grava as análises."""
import importlib.util
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..")
spec = importlib.util.spec_from_file_location("exportar_vitrine", os.path.join(RAIZ, "scripts", "exportar_vitrine.py"))
vitrine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vitrine)

ID = "0123456789abcdef01234567"
CARD = {"analysis_id": ID, "name": "Área de teste", "status": "completed", "quality": "no_reliable_water",
        "summary": {"quality": "no_reliable_water", "n_dates": 2}, "center": [-40.4, -17.9]}
DETALHE = dict(CARD, quality_reasons=["sem margem"], dates=[{"date": "2026-06-27", "water_km2": None}],
               layers=[{"id": "hh_20260627", "type": "backscatter"}], layers_url=f"/api/arara/analyses/{ID}/layers")
RESPOSTAS = {
    "/api/arara/analyses?status=completed": json.dumps({"count": 1, "analyses": [CARD]}).encode(),
    f"/api/arara/analyses/{ID}": json.dumps(DETALHE).encode(),
    f"/api/arara/analyses/{ID}/sources": b'{"scenes": []}',
    f"/api/arara/analyses/{ID}/metrics": b'{"dates": []}',
    f"/api/arara/analyses/{ID}/metrics?format=csv": b"date,quality\n2026-06-27,no_reliable_water\n",
    f"/api/arara/analyses/{ID}/png/hh_20260627.png": b"\x89PNG",
}


@pytest.fixture
def servidor():
    class Api(BaseHTTPRequestHandler):
        def do_GET(self):
            corpo = RESPOSTAS.get(self.path)
            self.send_response(200 if corpo is not None else 404)
            self.end_headers()
            self.wfile.write(corpo or b"{}")

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


def test_exporta_o_mesmo_frontend_em_modo_estatico(servidor, tmp_path):
    saida = tmp_path / "vitrine"
    vitrine.exportar(servidor, [ID], str(saida))
    for pagina in ("index.html", "estudo/index.html"):
        html = (saida / pagina).read_text(encoding="utf-8")
        assert html.index("window.ARARA_STATIC = true") < html.index("<script src=")
    assert (saida / "furnas" / "index.html").exists() and (saida / "vendor" / "globe.gl" / "globe.gl.min.js").exists()
    lista = json.loads((saida / "data" / "analyses.json").read_text(encoding="utf-8"))
    assert [a["analysis_id"] for a in lista["analyses"]] == [ID]
    base = saida / "data" / "analyses" / ID
    detalhe = json.loads((base / "analysis.json").read_text(encoding="utf-8"))
    assert detalhe["quality"] == "no_reliable_water" and "layers_url" not in detalhe
    assert (base / "png" / "hh_20260627.png").read_bytes() == b"\x89PNG"
    assert (base / "metrics.csv").read_text(encoding="utf-8").startswith("date,quality")
    assert (base / "sources.json").exists() and (base / "metrics.json").exists() and (saida / ".nojekyll").exists()


def test_id_que_nao_existe_no_servidor_aborta(servidor, tmp_path):
    with pytest.raises(SystemExit, match="não encontradas"):
        vitrine.exportar(servidor, ["ffffffffffffffffffffffff"], str(tmp_path / "v"))


def test_vitrine_tem_favicon_e_nao_promete_catalogo_ao_vivo(servidor, tmp_path):
    saida = tmp_path / "vitrine"
    vitrine.exportar(servidor, [ID], str(saida))
    ico = (saida / "favicon.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00"                            # cabeçalho ICO
    assert '<link rel="icon" href="favicon.ico"' in (saida / "index.html").read_text(encoding="utf-8")
    for pagina in ("estudo/index.html", "furnas/index.html"):
        assert '<link rel="icon" href="../favicon.ico"' in (saida / pagina).read_text(encoding="utf-8")
    globo = (saida / "index.html").read_text(encoding="utf-8")
    # em modo estático o cabeçalho do painel e o aviso não falam em consulta ao vivo
    assert "const CATALOG_HEAD = STATIC ? 'Radar NISAR, banda L · vitrine com análises já concluídas'" in globo
    linha = next(l for l in globo.splitlines() if l.startswith("const LIVE_MSG"))
    assert "ao vivo" not in linha and "não consulta o catálogo" in linha
    assert "panelHead(ctx, 'Radar NISAR, banda L · catálogo consultado ao vivo" not in globo
