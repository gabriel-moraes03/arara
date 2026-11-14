import numpy as np
import pytest

import area_agua
from conftest import PIXEL_M, nome_nisar

TODO = (0.0, 1.0, 0.0, 1.0)  # recorte = imagem inteira


def disco(n, raio_px, centro=None):
    cy, cx = centro or (n / 2, n / 2)
    yy, xx = np.mgrid[:n, :n]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= raio_px ** 2


# ---------- unidade ----------

def test_data_do_nome():
    assert area_agua.data_do_nome("pasta/" + nome_nisar("20261013")) == "20261013"


def test_otsu_bimodal():
    rng = np.random.default_rng(1)
    v = np.concatenate([rng.normal(-22, 1.5, 5000), rng.normal(-8, 1.5, 5000)])
    assert -18 < area_agua.otsu(v) < -12


def test_vale_desbalanceado_fica_entre_os_picos():
    # 5% água, terra larga: o Otsu puxa para a terra, o vale deve ficar perto do meio
    rng = np.random.default_rng(2)
    v = np.concatenate([rng.normal(-22, 1.5, 5000), rng.normal(-9, 3, 95000)])
    assert -19 < area_agua.vale(v) < -14


def test_valido_da_mask():
    m = np.array([0, 1, 2, 254, 255], "uint8")
    assert area_agua.valido_da_mask(m).tolist() == [False, True, True, True, False]


def test_tirar_manchas():
    agua = np.zeros((100, 100), bool)
    agua[10:20, 10:20] = True   # 100 px x (40 m)² = 0,16 km² -> fica
    agua[50:55, 50:55] = True   # 25 px = 0,04 km² -> sai
    limpa = area_agua.tirar_manchas(agua, 40.0, minimo_km2=0.1)
    assert limpa[10:20, 10:20].all() and not limpa[50:55, 50:55].any()


def test_zona_do_lago_exige_maioria_das_datas_e_dilata():
    n = 200
    lago = disco(n, 30)
    falso = np.zeros((n, n), bool)
    falso[5:10, 5:10] = True                      # aparece só em 2 de 9 datas
    mascaras = [lago | falso if i < 2 else lago for i in range(9)]
    zona = area_agua.zona_do_lago(mascaras, pixel_m=40.0, dilatacao_m=400.0)
    assert zona[lago].all()
    assert not zona[7, 7]
    assert zona[100, 100 + 30 + 9] and not zona[100, 100 + 30 + 12]  # ~10 px (400 m) além da margem


def test_zona_do_lago_descarta_mancha_recorrente_isolada():
    n = 200
    lago = disco(n, 30)
    mancha = np.zeros((n, n), bool)
    mancha[5:12, 5:12] = True                     # escura em todas as datas, mas longe do lago
    zona = area_agua.zona_do_lago([lago | mancha] * 9, pixel_m=40.0, dilatacao_m=200.0)
    assert zona[lago].all() and not zona[8, 8]


def test_ligada_ao_lago():
    agua = np.zeros((50, 50), bool)
    agua[10:20, 10:30] = True    # toca a semente
    agua[40:45, 40:45] = True    # solta
    sementes = np.zeros_like(agua)
    sementes[12:14, 12:14] = True
    ligada = area_agua.ligada_ao_lago(agua, sementes)
    assert ligada[10:20, 10:30].all() and not ligada[40:45, 40:45].any()


def escrever_shp(caminho, aneis, epsg):
    """Shapefile mínimo de 1 polígono (tipo 5) + .prj, só para teste."""
    import struct
    from pyproj import CRS
    pts = np.concatenate(aneis)
    partes = np.cumsum([0] + [len(a) for a in aneis[:-1]])
    corpo = struct.pack("<i4d2i", 5, *pts.min(0), *pts.max(0), len(aneis), len(pts))
    corpo += struct.pack(f"<{len(aneis)}i", *partes) + pts.astype("<f8").tobytes()
    reg = struct.pack(">2i", 1, len(corpo) // 2) + corpo
    cab = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(reg)) // 2)
    cab += struct.pack("<2i4d4d", 1000, 5, *pts.min(0), *pts.max(0), 0, 0, 0, 0)
    with open(caminho, "wb") as f:
        f.write(cab + reg)
    with open(caminho[:-4] + ".prj", "w") as f:
        f.write(CRS.from_epsg(epsg).to_wkt())


def test_poligono_shp_com_buraco_e_buffer(tmp_path):
    fora = np.array([[0, 0], [0, 1000], [1000, 1000], [1000, 0], [0, 0]], float)   # horário
    buraco = np.array([[400, 400], [600, 400], [600, 600], [400, 600], [400, 400]], float)  # anti-horário
    shp = str(tmp_path / "lago.shp")
    escrever_shp(shp, [fora, buraco], 32723)
    aneis = area_agua.ler_poligono_shp(shp, 32723)
    assert len(aneis) == 2 and np.allclose(aneis[0], fora)
    xs = np.arange(-490, 1500, 20.0)
    ys = np.arange(1490, -500, -20.0)
    m = area_agua.mascara_do_poligono(aneis, xs, ys)
    assert m.sum() * 400 == pytest.approx(1000 ** 2 - 200 ** 2, rel=0.02)
    mb = area_agua.mascara_do_poligono(aneis, xs, ys, buffer_m=200)
    col = lambda x: np.argmin(abs(xs - x))
    lin = lambda y: np.argmin(abs(ys - y))
    assert mb[lin(500), col(1150)] and not mb[lin(500), col(1250)]


def test_costurar_linhas_fecha_contorno_em_pedacos():
    # quadrado de 1 km em 3 pedaços, um invertido e com folga de 30 m, + uma ilha já fechada
    pedacos = [np.array([[0, 0], [0, 1000]], float),
               np.array([[1000, 0], [1000, 1000], [30, 1000]], float),   # invertido
               np.array([[1000, 0], [0, 0]], float)]
    ilha = np.array([[400, 400], [600, 400], [600, 600], [400, 600], [400, 400]], float)
    aneis, folga = area_agua.costurar_linhas(pedacos + [ilha])
    assert len(aneis) == 2 and folga == pytest.approx(30)
    xs = np.arange(-490, 1500, 20.0)
    ys = np.arange(1490, -500, -20.0)
    m = area_agua.mascara_do_poligono(aneis, xs, ys)
    assert m.sum() * 400 == pytest.approx(1000 ** 2 - 200 ** 2, rel=0.03)


def test_linhas_do_wkb_multilinestring_z():
    import struct
    pts = [(0, 0, 5), (10, 0, 5), (10, 10, 5)]
    linha = struct.pack("<BIi", 1, 1002, len(pts)) + b"".join(struct.pack("<3d", *p) for p in pts)
    wkb = struct.pack("<BIi", 1, 1005, 1) + linha                       # MultiLineString Z (ISO)
    (a,) = area_agua.linhas_do_wkb(wkb)
    assert a.shape == (3, 2) and a[-1].tolist() == [10, 10]


def test_processar_com_poligono_ignora_agua_fora(gcov, tmp_path):
    n = 600
    lago = disco(n, 100)
    falso = np.zeros((n, n), bool)
    falso[20:60, 20:60] = True                   # "pasto escuro" longe do lago
    arq = gcov("20260627", lago | falso)
    x0, y0 = 400000.0, 7700000.0                 # mesma origem do conftest
    t = np.linspace(0, 2 * np.pi, 200)
    anel = np.column_stack([x0 + PIXEL_M * (300 + 100 * np.cos(t)), y0 - PIXEL_M * (300 + 100 * np.sin(t))])
    (_, area, *_), = area_agua.processar([arq], str(tmp_path / "out"), recorte=TODO, passo=1, poligono=[anel])
    assert area == pytest.approx(np.pi * (100 * PIXEL_M) ** 2 / 1e6, rel=0.02)


def test_recorte_por_coordenadas_em_grades_diferentes(gcov):
    # duas grades de tamanhos e origens diferentes: a caixa em metros tem de pegar a mesma área
    a = gcov("20260627", np.zeros((300, 400), bool), x0=400000.0, y0=7700000.0)
    b = gcov("20260709", np.zeros((360, 440), bool), x0=399000.0, y0=7701000.0)
    db_a, _, px, caixa = area_agua.ler_recorte(a, recorte=(0.25, 0.75, 0.25, 0.75), passo=1)
    db_b, _, _, _ = area_agua.ler_recorte(b, caixa=caixa, passo=1)
    assert db_a.shape == db_b.shape == (150, 200)
    assert px == PIXEL_M


# ---------- ponta a ponta sintético ----------

@pytest.mark.parametrize("passo", [1, 2])
def test_lago_circular_area_conhecida(gcov, tmp_path, passo):
    n = 1000
    raios = {"20260627": 150, "20261013": 110}  # px de 20 m -> 28,27 e 15,21 km²
    arqs = [gcov(d, disco(n, r), semente=i) for i, (d, r) in enumerate(raios.items())]
    linhas = area_agua.processar(arqs, str(tmp_path / "out"), recorte=TODO, passo=passo)
    for (data, area, *_), r in zip(linhas, raios.values()):
        esperado = np.pi * (r * PIXEL_M) ** 2 / 1e6
        assert area == pytest.approx(esperado, rel=0.02), data
    assert (tmp_path / "out" / "mudanca.png").exists()
    assert (tmp_path / "out" / "area_agua.csv").exists()


def test_faixa_escura_com_mask_zero_nao_conta(gcov, tmp_path):
    # imita a borda esquerda da passagem: faixa escura que a mask marca como 0
    n = 600
    agua = disco(n, 100)
    agua[:, :40] = True
    mask = np.ones((n, n), "uint8")
    mask[:, :40] = 0
    arq = gcov("20260627", agua, mask=mask)
    (_, area, *_), = area_agua.processar([arq], str(tmp_path / "out"), recorte=TODO, passo=1)
    assert area == pytest.approx(np.pi * (100 * PIXEL_M) ** 2 / 1e6, rel=0.02)


@pytest.mark.parametrize("largura", [3, 4, 5])
def test_braco_fino_nao_some(gcov, tmp_path, largura):
    n = 600
    agua = disco(n, 80, centro=(300, 150))
    linha0 = 300 - largura // 2
    agua[linha0:linha0 + largura, 150:560] = True  # braço de 3-5 px saindo do lago
    arq = gcov("20260627", agua)
    area_agua.processar([arq], str(tmp_path / "out"), recorte=TODO, passo=1)
    mascara = np.load(tmp_path / "out" / "dados_mudanca.npz")["antes"]
    # trecho do braço longe do lago e da ponta (evita o efeito de borda do filtro 5x5)
    trecho = mascara[linha0:linha0 + largura, 260:540]
    colunas_com_agua = trecho.any(axis=0).mean()
    assert colunas_com_agua > 0.9, f"braço de {largura} px detectado em só {colunas_com_agua:.0%} do comprimento"
