"""Libera espaço no Storage do Supabase sem perder conteúdo.

Roda no computador do robô, com a chave de serviço (sem o limite de tempo do painel do Supabase).

    python liberar_espaco.py --medir    -> só mede e mostra o que pode sair (não muda nada)
    python liberar_espaco.py --apagar   -> apaga de verdade

O que sai:
  1. Imagens que nenhuma página usa (lixo), com mais de 2 dias (um envio em andamento pode estar gravando as dele).
  2. Fotos de página inteira que só aparecem no botão "Ver página inteira" e cujo arquivo é um PDF do Google Drive:
     quando alguém tocar no botão, o robô refaz a foto a partir do PDF (isso já funciona: "Página inteira" no robô).
O que fica: as figuras das apostilas, as fotos que são usadas como figura, e qualquer imagem citada nos estudos
(OSCE, material), nos compartilhamentos e no cache da IA. Nada do texto, das apostilas ou das questões muda.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
H = {"apikey": KEY, "Content-Type": "application/json"} if KEY.startswith("sb_secret_") else {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
REGISTRO = os.environ.get("LOG_ARQUIVO")
REF = re.compile(r'sb:([^"\'\s\)\]\\]+)')
MB = 1024 * 1024


def log(msg):
    linha = time.strftime("%H:%M:%S") + " " + str(msg)
    print(linha, flush=True)
    if REGISTRO:
        try:
            with open(REGISTRO, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except OSError:
            pass


def ler(tabela, select, **filtros):
    """Lê a tabela inteira, de 1000 em 1000 linhas (em ordem, para não pular nem repetir linha)."""
    out, ini = [], 0
    params = {"select": select, **filtros}
    if "order" not in params:
        params["order"] = "id"
    while True:
        r = None
        for t in range(4):
            try:
                r = requests.get(f"{URL}/rest/v1/{tabela}", params=params, headers={**H, "Range": f"{ini}-{ini + 999}"}, timeout=120)
                if r.status_code < 300 or r.status_code in (400, 404, 416):
                    break
            except requests.RequestException:
                pass
            time.sleep(5 * (t + 1))
        if r is None:
            raise RuntimeError(f"o banco não respondeu ao ler {tabela}")
        if r.status_code == 404:                 # tabela que este banco não tem (SQL antigo): nada a proteger nela
            return out
        if r.status_code == 416:
            return out
        if r.status_code >= 300:                 # qualquer outro erro: para tudo (sem a lista completa, nada é apagado)
            raise RuntimeError(f"não consegui ler {tabela} ({r.status_code} {r.text[:200]})")
        lote = r.json()
        out += lote
        if len(lote) < 1000:
            return out
        ini += 1000


def listar_storage():
    """Todos os arquivos da pasta "paginas" do Storage, com o tamanho e a data (só a lista, nenhum arquivo é baixado)."""
    def lista(prefixo):
        out, off = [], 0
        while True:
            r = requests.post(f"{URL}/storage/v1/object/list/paginas", headers=H, timeout=120,
                              json={"prefix": prefixo, "limit": 1000, "offset": off, "sortBy": {"column": "name", "order": "asc"}})
            r.raise_for_status()
            lote = r.json()
            out += lote
            if len(lote) < 1000:
                return out
            off += 1000
    arquivos = {}
    pastas = [x["name"] for x in lista("") if x.get("id") is None]
    for p in pastas:
        for x in lista(p + "/"):
            if x.get("id") is None:
                continue
            md = x.get("metadata") or {}
            arquivos[f"{p}/{x['name']}"] = {"bytes": int(md.get("size") or 0), "em": x.get("created_at") or ""}
    return arquivos


def refs_de(valor):
    return REF.findall(json.dumps(valor, ensure_ascii=False)) if valor else []


def analisar():
    log("Lendo as páginas (só as referências das imagens, não o texto)...")
    pags = ler("paginas", "id,documento_id,imagem,figuras,imagens")
    log(f"{len(pags)} páginas. Lendo as páginas de Word e PowerPoint (imagens dentro do texto)...")
    html = ler("paginas", "id,html", html="like.*data-ref*")
    docs = {d["id"]: d for d in ler("documentos", "id,tipo,drive_id")}
    log("Lendo os estudos, os compartilhamentos e o cache da IA (imagens citadas neles ficam)...")
    outros = ler("meus_estudos", "id,dados") + ler("compartilhados", "*") + ler("cache_ia", "chave,dados", order="chave")
    figura = set()                     # usadas como figura (ou citadas em outro lugar): ficam sempre
    for p in pags:
        figura.update(refs_de(p.get("figuras")))
        figura.update(refs_de(p.get("imagens")))
    for p in html:
        figura.update(refs_de(p.get("html")))
    for x in outros:
        figura.update(refs_de(x))
    foto_pags = {}                     # foto de página -> páginas que a usam
    for p in pags:
        im = p.get("imagem") or ""
        if im.startswith("sb:"):
            foto_pags.setdefault(im[3:], []).append(p)
    refaz = lambda p: (docs.get(p.get("documento_id")) or {}).get("tipo") == "PDF" and bool((docs.get(p.get("documento_id")) or {}).get("drive_id"))
    fotos_sair = {nome: ps for nome, ps in foto_pags.items() if nome not in figura and all(refaz(p) for p in ps)}
    log("Listando os arquivos do Storage (só a lista)...")
    arqs = listar_storage()
    limite = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    usadas = figura | set(foto_pags)
    lixo = [n for n, a in arqs.items() if n not in usadas and a["em"] and a["em"] < limite]
    fotos = [n for n in fotos_sair if n in arqs]
    soma = lambda ns: sum(arqs[n]["bytes"] for n in ns)
    total = sum(a["bytes"] for a in arqs.values())
    return {"arqs": arqs, "lixo": lixo, "fotos": fotos, "fotos_sair": fotos_sair, "total": total, "soma": soma}


def apagar_storage(nomes):
    feitos = 0
    for i in range(0, len(nomes), 100):
        lote = nomes[i:i + 100]
        for t in range(4):
            try:
                r = requests.delete(f"{URL}/storage/v1/object/paginas", headers=H, json={"prefixes": lote}, timeout=120)
                if r.status_code < 300:
                    break
            except requests.RequestException:
                pass
            time.sleep(5 * (t + 1))
        else:
            raise RuntimeError(f"o Storage não apagou ({r.status_code} {r.text[:200]})")
        feitos += len(lote)
        if feitos % 1000 < 100:
            log(f"   {feitos} de {len(nomes)} apagadas...")
    return feitos


def tirar_fotos(fotos, fotos_sair):
    """A página deixa de apontar para a foto (o "Ver página inteira" passa a pedir ao robô) e só depois a foto sai."""
    ids = [p["id"] for n in fotos for p in fotos_sair[n]]
    for i in range(0, len(ids), 100):
        lote = ids[i:i + 100]
        r = requests.patch(f"{URL}/rest/v1/paginas", params={"id": "in.(" + ",".join(lote) + ")"}, headers={**H, "Prefer": "return=minimal"},
                           json={"imagem": None}, timeout=120)
        if r.status_code >= 300:
            raise RuntimeError(f"o banco não mudou as páginas ({r.status_code} {r.text[:200]})")
    log(f"   {len(ids)} páginas passaram a pedir a foto ao robô quando alguém quiser ver a página inteira.")
    return apagar_storage(fotos)


def limpar_lixo():
    """Usado pelo robô no fim de cada rodada (no máximo a cada 3 dias): só o lixo."""
    marca = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ultima-limpeza.txt")
    try:
        if time.time() - os.path.getmtime(marca) < 3 * 86400:
            return 0
    except OSError:
        pass
    try:
        a = analisar()
        n = apagar_storage(a["lixo"]) if a["lixo"] else 0
        with open(marca, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M"))
        if n:
            log(f"Limpeza: {n} imagens que nenhuma página usava foram apagadas do Storage ({a['soma'](a['lixo']) / MB:.0f} MB).")
        return n
    except Exception as e:  # noqa: BLE001
        log(f"Limpeza das imagens: {e}")
        return 0


def principal():
    if not URL or not KEY:
        sys.exit("Faltam as chaves do Supabase (rode pelo LIBERAR-ESPACO.bat).")
    apagar = "--apagar" in sys.argv
    a = analisar()
    lixo, fotos = a["lixo"], a["fotos"]
    mb_lixo, mb_fotos = a["soma"](lixo) / MB, a["soma"](fotos) / MB
    log("")
    log(f"Arquivos no Storage hoje: {a['total'] / MB:.0f} MB ({len(a['arqs'])} arquivos). Limite do plano grátis: 1024 MB.")
    log(f"  Lixo (nenhuma página usa, mais de 2 dias): {mb_lixo:.0f} MB ({len(lixo)} arquivos)")
    log(f"  Fotos de página que o robô refaz do PDF no Drive: {mb_fotos:.0f} MB ({len(fotos)} arquivos)")
    log(f"  Depois da limpeza: cerca de {(a['total'] / MB) - mb_lixo - mb_fotos:.0f} MB")
    if not apagar:
        log("Nada foi mudado (só medi).")
        return
    if lixo:
        log("Apagando o lixo...")
        apagar_storage(lixo)
    if fotos:
        log("Tirando as fotos de página que o robô refaz...")
        tirar_fotos(fotos, a["fotos_sair"])
    log(f"Pronto: {mb_lixo + mb_fotos:.0f} MB liberados. O painel do Supabase pode levar algumas horas para mostrar o número novo.")


if __name__ == "__main__":
    try:
        principal()
    except SystemExit:
        raise
    except BaseException as e:
        import traceback
        log(f"ERRO: {e}")
        log(traceback.format_exc())
        raise
