"""Libera espaço no Storage do Supabase sem perder conteúdo.

Roda no computador do robô, com a chave de serviço (sem o limite de tempo do painel do Supabase).

    python liberar_espaco.py --medir    -> só mede e mostra o que pode sair (não muda nada)
    python liberar_espaco.py --apagar   -> apaga de verdade
    python liberar_espaco.py --diminuir -> refaz menores as figuras pesadas, das maiores para as menores, até o total
                                           ficar abaixo de ALVO_MB (900 MB): primeiro as páginas inteiras usadas como
                                           figura, a partir do PDF no Google Drive (não gasta o tráfego do Supabase);
                                           se ainda faltar, os prints de slides dos vídeos e as figuras mais pesadas
                                           (baixa cada uma uma vez do Supabase, então gasta o tráfego dela)

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
ALVO_MB = float(os.environ.get("ALVO_MB", "900"))


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
    pags = ler("paginas", "id,documento_id,n,imagem,figuras,imagens")
    log(f"{len(pags)} páginas. Lendo as páginas de Word e PowerPoint (imagens dentro do texto)...")
    html = ler("paginas", "id,html", html="like.*data-ref*")
    docs = {d["id"]: d for d in ler("documentos", "id,tipo,drive_id")}
    log("Lendo os estudos, os compartilhamentos e o cache da IA (imagens citadas neles ficam)...")
    outros = ler("meus_estudos", "id,dados") + ler("compartilhados", "*") + ler("cache_ia", "chave,dados", order="chave")
    figura = set()                     # usadas como figura (ou citadas em outro lugar): ficam sempre
    for p in pags:
        figura.update(refs_de(p.get("figuras")))
        figura.update(refs_de(p.get("imagens")))
    intocaveis = set()                 # citadas no texto de Word/PowerPoint, nos estudos, nos compartilhamentos e no cache:
    for p in html:                     # não mudam de nome (o endereço está escrito dentro deles)
        intocaveis.update(refs_de(p.get("html")))
    for x in outros:
        intocaveis.update(refs_de(x))
    figura |= intocaveis
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
    # figuras que dá para refazer menores: a página inteira usada como figura, de um PDF do Drive (a fonte é a página)
    fonte = {}
    for nome, ps in foto_pags.items():
        if nome in figura and nome not in intocaveis and nome in arqs:
            p = next((p for p in ps if refaz(p)), None)
            if p:
                fonte[nome] = (docs[p["documento_id"]]["drive_id"], int(p.get("n") or 0))
    usos = {}                          # imagem -> páginas que apontam para ela (para trocar pelo nome novo)
    for p in pags:
        for r in set(refs_de(p.get("imagem")) + refs_de(p.get("figuras")) + refs_de(p.get("imagens"))):
            usos.setdefault(r, []).append(p["id"])
    return {"arqs": arqs, "lixo": lixo, "fotos": fotos, "fotos_sair": fotos_sair, "total": total, "soma": soma,
            "fonte": fonte, "usos": usos, "intocaveis": intocaveis, "figura": figura}


def apagar_storage(nomes, calado=False):
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
        if not calado and feitos % 1000 < 100:
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


def _webp(img, max_w, q):
    import io
    from PIL import Image
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)), Image.LANCZOS)
    b = io.BytesIO(); img.convert("RGB").save(b, "WEBP", quality=q, method=6)
    return b.getvalue()


def _guardar(dados):
    import hashlib
    nome = "img/" + hashlib.sha256(dados).hexdigest() + ".webp"     # o mesmo jeito de dar nome do site (a "impressão digital")
    for t in range(4):
        try:
            r = requests.post(f"{URL}/storage/v1/object/paginas/{nome}", data=dados, timeout=120,
                              headers={**H, "Content-Type": "image/webp", "x-upsert": "true", "cache-control": "max-age=31536000"})
            if r.status_code < 300:
                return nome
        except requests.RequestException:
            pass
        time.sleep(5 * (t + 1))
    raise RuntimeError(f"o Storage não guardou a figura nova ({r.status_code} {r.text[:200]})")


def _trocar(antigo, novo, ids):
    """Cada página que aponta para a figura antiga passa a apontar para a nova (lida de novo na hora: se o robô mexeu
    na página nesse meio tempo, vale o que está lá agora). Só depois a antiga sai."""
    a, n = "sb:" + antigo, "sb:" + novo
    for i in range(0, len(ids), 50):
        r = requests.get(f"{URL}/rest/v1/paginas", params={"select": "id,imagem,figuras,imagens", "id": "in.(" + ",".join(ids[i:i + 50]) + ")"}, headers=H, timeout=120)
        r.raise_for_status()
        for p in r.json():
            mud = {}
            if p.get("imagem") == a:
                mud["imagem"] = n
            if isinstance(p.get("figuras"), list) and a in p["figuras"]:
                mud["figuras"] = [n if x == a else x for x in p["figuras"]]
            if isinstance(p.get("imagens"), list) and a in p["imagens"]:
                mud["imagens"] = [n if x == a else x for x in p["imagens"]]
            if mud:
                w = requests.patch(f"{URL}/rest/v1/paginas", params={"id": "eq." + p["id"]}, headers={**H, "Prefer": "return=minimal"}, json=mud, timeout=120)
                if w.status_code >= 300:
                    raise RuntimeError(f"o banco não trocou a figura ({w.status_code} {w.text[:200]})")
    apagar_storage([antigo], calado=True)


def _baixar_pdf(drive_id, destino):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from robo_ia import token_drive
    with requests.get(f"https://www.googleapis.com/drive/v3/files/{drive_id}", params={"alt": "media", "supportsAllDrives": "true"},
                      headers={"Authorization": "Bearer " + token_drive()}, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for parte in r.iter_content(1 << 20):
                f.write(parte)


def diminuir():
    import tempfile
    a = analisar()
    total = a["total"]
    alvo = ALVO_MB * MB
    log(f"Arquivos no Storage: {total / MB:.0f} MB. Meta: abaixo de {ALVO_MB:.0f} MB.")
    if total <= alvo:
        log("Já está abaixo da meta: nada para diminuir.")
        return
    arqs, usos = a["arqs"], a["usos"]
    feitas, ganho = 0, 0
    # 1) páginas inteiras usadas como figura: refeitas do PDF no Drive, em 1000 px (não gasta o tráfego do Supabase)
    cand = sorted((n for n in a["fonte"] if arqs[n]["bytes"] > 40_000), key=lambda n: -arqs[n]["bytes"])
    por_pdf = {}
    for n in cand:
        por_pdf.setdefault(a["fonte"][n][0], []).append(n)
    ordem = sorted(por_pdf, key=lambda d: -sum(arqs[n]["bytes"] for n in por_pdf[d]))
    log(f"Etapa 1: {len(cand)} páginas inteiras usadas como figura, de {len(ordem)} PDFs do Drive ({sum(arqs[n]['bytes'] for n in cand) / MB:.0f} MB).")
    import pymupdf
    from PIL import Image
    for k, drive_id in enumerate(ordem):
        if total - ganho <= alvo:
            break
        with tempfile.TemporaryDirectory() as tmp:
            arq = os.path.join(tmp, "a.pdf")
            try:
                _baixar_pdf(drive_id, arq)
                doc = pymupdf.open(arq)
            except Exception as e:  # noqa: BLE001
                log(f"   PDF {drive_id[:8]}... não abriu ({e}); as figuras dele ficam como estão.")
                continue
            try:
                for nome in por_pdf[drive_id]:
                    i = a["fonte"][nome][1] - 1
                    if i < 0 or i >= doc.page_count:
                        continue
                    pg = doc[i]
                    s = min(2.2, 1000 / pg.rect.width)
                    pix = pg.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
                    dados = _webp(Image.frombytes("RGB", (pix.width, pix.height), pix.samples), 1000, 55)
                    if len(dados) > arqs[nome]["bytes"] * 0.8:
                        continue                                  # não ficou bem menor: fica a antiga
                    novo = _guardar(dados)
                    if novo == nome:
                        continue
                    _trocar(nome, novo, usos.get(nome, []))
                    ganho += arqs[nome]["bytes"] - len(dados); feitas += 1
            finally:
                doc.close()
        if (k + 1) % 10 == 0:
            log(f"   {k + 1} de {len(ordem)} PDFs; {feitas} figuras refeitas; {ganho / MB:.0f} MB a menos.")
    log(f"Etapa 1 pronta: {feitas} figuras refeitas, {ganho / MB:.0f} MB a menos. Total agora: cerca de {(total - ganho) / MB:.0f} MB.")
    if total - ganho <= alvo:
        return
    # 2) o que ainda faltar: as imagens mais pesadas (prints de slides dos vídeos, em JPEG, e figuras grandes), baixadas
    # uma vez do Supabase e guardadas em WebP menor (1100 px). Gasta o tráfego do Supabase do tamanho do que baixar.
    import io
    feitos = set(a["fonte"])
    cand2 = sorted((n for n in arqs if n in a["figura"] and n not in a["intocaveis"] and n not in feitos and arqs[n]["bytes"] > 80_000 and n in usos),
                   key=lambda n: -arqs[n]["bytes"])
    log(f"Etapa 2: {len(cand2)} imagens pesadas ({sum(arqs[n]['bytes'] for n in cand2) / MB:.0f} MB); vai até chegar na meta.")
    baixado, n2 = 0, 0
    for nome in cand2:
        if total - ganho <= alvo:
            break
        try:
            r = requests.get(f"{URL}/storage/v1/object/paginas/{nome}", headers=H, timeout=120)
            r.raise_for_status()
            baixado += len(r.content)
            dados = _webp(Image.open(io.BytesIO(r.content)), 1100, 58)
        except Exception as e:  # noqa: BLE001
            log(f"   {nome}: {e}")
            continue
        if len(dados) > arqs[nome]["bytes"] * 0.75:
            continue
        novo = _guardar(dados)
        if novo != nome:
            _trocar(nome, novo, usos.get(nome, []))
            ganho += arqs[nome]["bytes"] - len(dados); n2 += 1
        if n2 and n2 % 200 == 0:
            log(f"   {n2} imagens refeitas; {ganho / MB:.0f} MB a menos no total.")
    log(f"Etapa 2 pronta: {n2} imagens refeitas ({baixado / MB:.0f} MB baixados do Supabase). Total agora: cerca de {(total - ganho) / MB:.0f} MB.")


def principal():
    if not URL or not KEY:
        sys.exit("Faltam as chaves do Supabase (rode pelo LIBERAR-ESPACO.bat).")
    if "--diminuir" in sys.argv:
        return diminuir()
    apagar = "--apagar" in sys.argv
    a = analisar()
    lixo, fotos = a["lixo"], a["fotos"]
    mb_lixo, mb_fotos = a["soma"](lixo) / MB, a["soma"](fotos) / MB
    log("")
    log(f"Arquivos no Storage hoje: {a['total'] / MB:.0f} MB ({len(a['arqs'])} arquivos). Limite do plano grátis: 1024 MB.")
    log(f"  Lixo (nenhuma página usa, mais de 2 dias): {mb_lixo:.0f} MB ({len(lixo)} arquivos)")
    log(f"  Fotos de página que o robô refaz do PDF no Drive: {mb_fotos:.0f} MB ({len(fotos)} arquivos)")
    log(f"  Depois da limpeza: cerca de {(a['total'] / MB) - mb_lixo - mb_fotos:.0f} MB")
    jpg = [n for n in a["arqs"] if n in a["figura"] and not n.startswith("img/")]
    log(f"  (das figuras: {a['soma'](list(a['fonte'])) / MB:.0f} MB são páginas inteiras de PDF do Drive, que dá para refazer menores sem gastar"
        f" tráfego; {a['soma'](jpg) / MB:.0f} MB são prints de slides dos vídeos)")
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
