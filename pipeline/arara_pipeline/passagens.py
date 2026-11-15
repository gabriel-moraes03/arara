"""Leitura das passagens do radar: cache por passagem e leitura em paralelo.

Cada passagem vira, uma vez, o radar em dB (filtro 5x5) da janela da área + 1 km, gravado no cache com a
chave (cena, CRID, área, passo, filtro). Reanalisar a mesma área com uma passagem nova relê na NASA só a
passagem nova. As que faltam no cache são lidas em paralelo, em processos separados (o h5py não lê em
paralelo dentro de um processo), ARARA_READ_WORKERS por vez (padrão 3).

O filtro é aplicado na janela inteira, antes do recorte para a grade comum: só muda pixels a até 2 px da
borda da janela, que fica 1 km fora da área pedida.
"""
import datetime
import os
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context

import numpy as np
from shapely import wkt as shapely_wkt

from . import cache, gcov_read
from .sar import db_filtrado

LEITORES = int(os.environ.get("ARARA_READ_WORKERS", 3))
BANDAS = ("HHHH", "HVHV")
_FS = None


def chave(cena, aoi_wkt, passo, filtro):
    return cache.chave("sar", cena["granule"], cena.get("crid"), aoi_wkt, passo, filtro)


def _ler(tarefa):
    """Roda num processo leitor: abre a cena, lê a janela, converte para dB e grava a entrada.
    Devolve ("ok", caminho) | ("invalida", motivo) | ("acesso", motivo)."""
    global _FS
    url, local, aoi_wkt, passo, filtro, destino = tarefa
    aoi = shapely_wkt.loads(aoi_wkt)
    try:
        remota = str(url).lower().startswith(("http://", "https://"))
        if remota and _FS is None:
            _FS = gcov_read._sessao_earthdata()
        with gcov_read.abrir(url, _FS if remota else None) as h:
            epsg = gcov_read.validar_estrutura(h)["epsg"]
            j = gcov_read.ler_janela(h, gcov_read.caixa_da_aoi(aoi, epsg), passo)
    except gcov_read.CenaInvalida as e:
        return ("invalida", str(e))
    except gcov_read.AcessoIndisponivel as e:
        return ("acesso", str(e))
    arrays = {"xs": j["xs"], "ys": j["ys"]}
    for b in BANDAS:
        if b in j["bands"]:
            arrays["db_" + b] = db_filtrado(j["bands"][b], j["valid"][b], filtro)
            arrays["valid_" + b] = j["valid"][b]
    remoto = not local
    meta = {"epsg": j["epsg"], "pixel_m": j["pixel_m"], "pixel_area_m2": j["pixel_area_m2"], "window": j["window"],
            "source": {"access": "streaming" if remoto else "local", "block_bytes": gcov_read.BLOCO_BYTES if remoto else None,
                       "checksum": gcov_read.LIMITACAO_CHECKSUM if remoto else "não conferido nesta leitura",
                       "read_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}}
    cache.salvar_npz(destino, meta, **arrays)
    return ("ok", destino)


def carregar(caminho, origem_cache):
    lido = cache.ler_npz(caminho)
    if lido is None:
        return None
    meta, a = lido
    j = {"xs": a["xs"], "ys": a["ys"], "epsg": meta["epsg"], "pixel_m": meta["pixel_m"],
         "pixel_area_m2": meta["pixel_area_m2"], "window": meta["window"],
         "source": {**meta["source"], "cache": origem_cache}, "db": {}, "valid": {}}
    for b in BANDAS:
        if "db_" + b in a:
            j["db"][b] = a["db_" + b]
            j["valid"][b] = a["valid_" + b]
    return j


def ler(cenas, aoi, passo, filtro, progresso, leitores=None):
    """Uma entrada por cena, na mesma ordem: dict da janela ou str com o motivo de ter sido pulada.
    Levanta gcov_read.AcessoIndisponivel se a NASA recusar o acesso (credencial, rede)."""
    leitores = max(1, int(leitores or LEITORES))
    aoi_wkt = shapely_wkt.dumps(aoi, rounding_precision=7)
    temporaria = None
    destinos, saida = [], [None] * len(cenas)
    for c in cenas:
        if c.get("local"):        # cenas do disco (Furnas, testes): sem cache; nomes podem se repetir
            temporaria = temporaria or tempfile.mkdtemp(prefix="arara-janelas-")
            destinos.append(os.path.join(temporaria, f"{len(destinos)}.npz"))
        else:
            destinos.append(cache.caminho("sar", chave(c, aoi_wkt, passo, filtro)))
    faltam = []
    for i, (c, d) in enumerate(zip(cenas, destinos)):
        j = None if c.get("local") else carregar(d, "hit")
        if j is not None:
            saida[i] = j
        else:
            faltam.append(i)
    feitas = len(cenas) - len(faltam)
    if feitas:
        progresso("acquire", 0.08 + 0.42 * feitas / len(cenas), f"{feitas} de {len(cenas)} passagens já estavam no cache")
    tarefas = {i: (cenas[i]["url"], bool(cenas[i].get("local")), aoi_wkt, passo, filtro, destinos[i]) for i in faltam}
    try:
        if len(faltam) <= 1 or leitores == 1 or all(cenas[i].get("local") for i in faltam):
            resultados = ((i, _ler(tarefas[i])) for i in faltam)
            _consumir(resultados, cenas, saida, feitas, progresso)
        else:
            with ProcessPoolExecutor(max_workers=min(leitores, len(faltam)), mp_context=get_context("spawn")) as ex:
                futuros = {ex.submit(_ler, tarefas[i]): i for i in faltam}
                _consumir(((futuros[f], f.result()) for f in as_completed(futuros)), cenas, saida, feitas, progresso)
    finally:
        if temporaria:
            shutil.rmtree(temporaria, ignore_errors=True)
    return saida


def _consumir(resultados, cenas, saida, feitas, progresso):
    n = len(cenas)
    for i, (status, valor) in resultados:
        if status == "acesso":
            raise gcov_read.AcessoIndisponivel(valor)
        if status == "invalida":
            saida[i] = valor
        else:
            j = carregar(valor, "miss" if not cenas[i].get("local") else "local")
            saida[i] = j if j is not None else "entrada do cache ilegível logo após gravar"
        feitas += 1
        progresso("acquire", 0.08 + 0.42 * feitas / n, f"passagem {feitas}/{n} lida ({cenas[i]['date']})")


def tamanho_mb(j):
    return round(sum(np.asarray(v).nbytes for v in list(j["db"].values()) + list(j["valid"].values())) / 2 ** 20, 1)
