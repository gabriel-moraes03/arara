"""Cache local em disco, para não reler na NASA, no Sentinel-2 ou no GPM o que já foi lido.

Pasta: ARARA_CACHE_DIR (o backend passa data/cache) ou ~/.cache/arara. Cada entrada é um arquivo com
nome = hash da chave. A chave tem tudo o que muda o conteúdo (cena, CRID, área, passo, filtro, versão
do cache). Escrita atômica (arquivo temporário + rename), então dois processos lendo e gravando ao
mesmo tempo nunca veem um arquivo pela metade. Acima de ARARA_CACHE_MAX_MB (padrão 8192), as entradas
usadas há mais tempo saem primeiro.

O que fica guardado é derivado (radar em dB já filtrado, máscaras de água do Sentinel-2, HAND na grade,
chuva diária), nunca o arquivo GCOV em potência linear.
"""
import hashlib
import json
import os
import tempfile
import time

import numpy as np

VERSAO = 1


def base():
    p = os.environ.get("ARARA_CACHE_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "arara")
    os.makedirs(p, exist_ok=True)
    return p


def pasta(sub):
    p = os.path.join(base(), sub)
    os.makedirs(p, exist_ok=True)
    return p


def chave(*partes):
    return hashlib.sha256("|".join(str(p) for p in (VERSAO,) + partes).encode()).hexdigest()[:32]


def caminho(sub, k, ext=".npz"):
    return os.path.join(pasta(sub), k + ext)


def _atomico(destino, escrever):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(destino), suffix=".tmp")
    os.close(fd)
    try:
        escrever(tmp)
        os.replace(tmp, destino)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def salvar_npz(destino, meta, **arrays):
    """Arrays + um dict de metadados JSON numa entrada .npz comprimida."""
    def escrever(tmp):
        with open(tmp, "wb") as f:
            np.savez_compressed(f, __meta__=np.frombuffer(json.dumps(meta).encode(), np.uint8), **arrays)
    _atomico(destino, escrever)
    return destino


def ler_npz(origem):
    """(meta, {nome: array}) ou None se não existe ou está corrompido. Marca o uso (LRU)."""
    if not os.path.exists(origem):
        return None
    try:
        with np.load(origem) as z:
            meta = json.loads(bytes(z["__meta__"]).decode())
            arrays = {k: z[k] for k in z.files if k != "__meta__"}
    except Exception:  # noqa: BLE001  (entrada quebrada: relê da fonte)
        return None
    try:
        os.utime(origem)
    except OSError:
        pass
    return meta, arrays


def salvar_json(destino, dado):
    def escrever(tmp):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dado, f, ensure_ascii=False)
    _atomico(destino, escrever)


def ler_json(origem):
    if not os.path.exists(origem):
        return None
    try:
        with open(origem, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def limitar(maximo_mb=None):
    """Apaga as entradas menos usadas até caber no limite. Devolve (MB antes, MB depois)."""
    maximo_mb = float(maximo_mb if maximo_mb is not None else os.environ.get("ARARA_CACHE_MAX_MB", 8192))
    arquivos = []
    for raiz, _, nomes in os.walk(base()):
        for n in nomes:
            p = os.path.join(raiz, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if n.endswith(".tmp") and time.time() - st.st_mtime > 3600:
                os.remove(p)                    # sobra de processo morto no meio da escrita
                continue
            arquivos.append((st.st_atime if st.st_atime > st.st_mtime else st.st_mtime, st.st_size, p))
    total = sum(a[1] for a in arquivos)
    antes = total
    for _, tam, p in sorted(arquivos):
        if total <= maximo_mb * 1024 * 1024:
            break
        try:
            os.remove(p)
            total -= tam
        except OSError:
            pass
    return round(antes / 2 ** 20, 1), round(total / 2 ** 20, 1)
