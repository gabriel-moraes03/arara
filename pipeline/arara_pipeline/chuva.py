"""Chuva antes de cada passagem: GPM IMERG diário (Late Run, V07, 0,1°), NASA GES DISC.

Lê por OPeNDAP só as células de 0,1° que cobrem a área (alguns bytes por dia) com a mesma credencial
Earthdata do radar. A conta precisa ter autorizado o aplicativo "NASA GESDISC DATA ARCHIVE"; sem isso
o GES DISC responde 401/403 e a chuva sai `unavailable` com esse motivo, sem valor substituto.

A chuva é contexto para interpretar a mudança de água; ela não entra na medida da água.
"""
import datetime as dt
import math
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import cache

SHORT_NAME = "GPM_3IMERGDL"
PRODUTO = "GPM IMERG Late Run diário V07 (GPM_3IMERGDL), NASA GES DISC"
OPENDAP = "https://gpm1.gesdisc.eosdis.nasa.gov/opendap/"
DADOS = "https://data.gesdisc.earthdata.nasa.gov/data/"
DIAS_ANTES = 7
CELULA = 0.1
SEM_AUTORIZACAO = ("o GES DISC recusou o acesso: autorize o aplicativo \"NASA GESDISC DATA ARCHIVE\" em "
                   "urs.earthdata.nasa.gov (Applications > Authorized Apps) na conta Earthdata do servidor")


class ChuvaIndisponivel(Exception):
    pass


def indices(oeste, sul, leste, norte):
    """Faixas de índice (lon, lat) da grade IMERG 0,1° (centros em -179,95..179,95 e -89,95..89,95)
    que cobrem a caixa; no mínimo uma célula."""
    i0 = int(math.floor((oeste + 180) / CELULA))
    i1 = max(i0, int(math.ceil((leste + 180) / CELULA)) - 1)
    j0 = int(math.floor((sul + 90) / CELULA))
    j1 = max(j0, int(math.ceil((norte + 90) / CELULA)) - 1)
    return (max(0, i0), min(3599, i1)), (max(0, j0), min(1799, j1))


def ler_ascii(texto):
    """Valores de um recorte OPeNDAP .ascii de precipitation[time][lon][lat]; -9999,9 vira NaN."""
    vals = []
    for linha in texto.splitlines():
        if not linha.startswith("["):
            continue
        for v in linha.split(",")[1:]:
            v = v.strip()
            if v:
                vals.append(float(v))
    a = np.array(vals, float)
    a[a < 0] = np.nan
    return a


def url_opendap(url_dado, i, j):
    if not url_dado.startswith(DADOS):
        raise ChuvaIndisponivel(f"URL IMERG inesperada: {url_dado}")
    return (OPENDAP + url_dado[len(DADOS):] + f".ascii?precipitation[0:0][{i[0]}:{i[1]}][{j[0]}:{j[1]}]")


def dia_do_arquivo(url):
    m = re.search(r"3IMERG\.(\d{8})-", url)
    return f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else None


def granulos(inicio, fim):
    """URLs diárias do IMERG Late entre as datas (CMR, sem credencial)."""
    import earthaccess
    r = earthaccess.search_data(short_name=SHORT_NAME, temporal=(inicio, fim))
    out = {}
    for g in r:
        for u in g.data_links():
            d = dia_do_arquivo(u)
            if d and u.endswith(".nc4"):
                out[d] = u
    return out


def sessao():
    import earthaccess
    from .gcov_read import AcessoIndisponivel, _sessao_earthdata
    try:
        _sessao_earthdata()
    except AcessoIndisponivel as e:
        raise ChuvaIndisponivel(str(e)) from e
    return earthaccess.get_requests_https_session()


def serie_diaria(caixa, inicio, fim, buscar=None, baixar=None):
    """{dia: mm/dia médio na caixa} entre inicio e fim. buscar/baixar trocáveis nos testes."""
    buscar = buscar or granulos
    urls = buscar(inicio, fim)
    if not urls:
        raise ChuvaIndisponivel(f"nenhum arquivo IMERG Late entre {inicio} e {fim} (o produto sai com ~1 dia de atraso)")
    i, j = indices(*caixa)
    usar_cache = baixar is None
    if baixar is None:
        estado = {}

        def baixar(u):
            if "s" not in estado:
                estado["s"] = sessao()
            import requests
            try:
                r = estado["s"].get(u, timeout=(10, 60))
            except requests.ConnectionError as e:
                raise ChuvaIndisponivel("o servidor de chuva do GES DISC (OPeNDAP, gpm1.gesdisc.eosdis.nasa.gov) "
                                        "não responde agora; a próxima atualização tenta de novo") from e
            if r.status_code in (401, 403):
                raise ChuvaIndisponivel(SEM_AUTORIZACAO)
            r.raise_for_status()
            return r.text
    out, faltam = {}, []
    for d in sorted(urls):
        # o dia já lido para estas células não é baixado de novo (o IMERG Late não é reprocessado)
        c = cache.ler_json(cache.caminho("imerg", cache.chave("imerg", urls[d].rsplit("/", 1)[-1], i, j), ".json")) if usar_cache else None
        if c is not None:
            out[d] = c["mm"]
        else:
            faltam.append(d)
    with ThreadPoolExecutor(6) as ex:
        textos = list(ex.map(lambda d: baixar(url_opendap(urls[d], i, j)), faltam))
    for d, t in zip(faltam, textos):
        v = ler_ascii(t)
        out[d] = round(float(np.nanmean(v)), 2) if np.isfinite(v).any() else None
        if usar_cache:
            cache.salvar_json(cache.caminho("imerg", cache.chave("imerg", urls[d].rsplit("/", 1)[-1], i, j), ".json"), {"mm": out[d]})
    return out


def acumulado(diaria, data, dias=DIAS_ANTES):
    """Soma dos dias [data - dias + 1, data]; None se faltar algum dia."""
    d0 = dt.date.fromisoformat(data)
    vals = [diaria.get((d0 - dt.timedelta(days=k)).isoformat()) for k in range(dias)]
    return None if any(v is None for v in vals) else round(sum(vals), 1)


def resumir(diaria, datas):
    por_data = [{"date": d, "rain_3d_mm": acumulado(diaria, d, 3), "rain_7d_mm": acumulado(diaria, d, 7)} for d in datas]
    validos = [v for v in diaria.values() if v is not None]
    return {"status": "ok", "product": PRODUTO, "unit": "mm", "spatial": "média das células de 0,1° que cobrem a área",
            "per_date": por_data, "daily": [{"date": d, "mm": v} for d, v in sorted(diaria.items())],
            "total_mm": round(sum(validos), 1) if validos else None,
            "limitations": ["IMERG Late é estimativa por satélite (sem ajuste de pluviômetro do produto Final)",
                            "célula de ~11 km: chuva local forte pode ficar diluída"]}


def rodar(ctx, extras, progresso, serie=serie_diaria):
    progresso("rain", 0.84, "somando a chuva GPM IMERG antes de cada passagem")
    if ctx["spec"].get("rain") is False:
        extras["chuva"] = {"status": "unavailable", "product": PRODUTO, "reason": "chuva desligada no pedido"}
        return
    datas = [d["date"] for d in ctx["datas"]]
    inicio = (dt.date.fromisoformat(datas[0]) - dt.timedelta(days=DIAS_ANTES)).isoformat()
    try:
        diaria = serie(ctx["aoi"].bounds, inicio, datas[-1])
    except ChuvaIndisponivel as e:
        extras["chuva"] = {"status": "unavailable", "product": PRODUTO, "reason": str(e)}
        return
    except Exception as e:  # noqa: BLE001  (rede/serviço: a análise segue)
        extras["chuva"] = {"status": "unavailable", "product": PRODUTO,
                           "reason": f"GPM IMERG indisponível agora ({type(e).__name__})"}
        return
    extras["chuva"] = resumir(diaria, datas)
