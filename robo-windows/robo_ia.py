"""Robô da IA do Acervo da Turma.

Roda no GitHub Actions (de graça) e organiza com a IA os temas que estão na fila, sem ninguém com o app aberto.
Ele abre o próprio app num navegador sem tela (endereço com ?robo=1), entra com uma conta só dele e usa o mesmo
código do botão "Organizar ... temas agora". Por isso o resultado é igual ao do app.

A conta do robô é criada sozinha (robo-ia@example.com, só entra na lista "membros", não é administrador).
A senha é sorteada de novo a cada rodada e não fica guardada em lugar nenhum.

Segredos usados (os mesmos do robô de transcrição): SUPABASE_URL e SUPABASE_SERVICE_KEY; GOOGLE_SA_KEY (opcional)
para baixar os arquivos do Drive direto do Google, sem gastar a cota de tráfego do Supabase.
Opcionais: APP_URL (endereço do app), ROBO_EMAIL, MINUTOS (tempo máximo de trabalho), SIMULTANEOS.

    python robo_ia.py --checar   -> só diz se há tema esperando a IA (para o GitHub decidir se liga o navegador)
    python robo_ia.py            -> organiza a fila
"""
import json
import os
import secrets
import sys
import threading
import time
from urllib.parse import parse_qs, quote, urlparse

import requests

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]
APP = os.environ.get("APP_URL", "https://acervodaturma.pages.dev").rstrip("/")
EMAIL = os.environ.get("ROBO_EMAIL", "robo-ia@example.com").strip().lower()
MINUTOS = int(os.environ.get("MINUTOS", "300"))
SIMULTANEOS = int(os.environ.get("SIMULTANEOS", "2"))
QVERSAO = 2  # igual à QVERSAO do app
# chave nova do Supabase (sb_secret_...) vai só no "apikey"; a antiga (service_role, eyJ...) também no "Authorization"
H = {"apikey": KEY, "Content-Type": "application/json"} if KEY.startswith("sb_secret_") else {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"}


REGISTRO = os.environ.get("LOG_ARQUIVO")   # no computador: cada linha vai na hora para o arquivo de registro (UTF-8)


def log(msg):
    linha = time.strftime("%H:%M:%S") + " " + str(msg)
    print(linha, flush=True)
    if REGISTRO:
        try:
            with open(REGISTRO, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except OSError:
            pass


def tudo(tabela, select):
    """Lê a tabela inteira, de 1000 em 1000 linhas."""
    out, ini = [], 0
    while True:
        r = requests.get(f"{URL}/rest/v1/{tabela}", params={"select": select},
                         headers={**H, "Range": f"{ini}-{ini + 999}"}, timeout=60)
        r.raise_for_status()
        lote = r.json()
        out += lote
        if len(lote) < 1000:
            return out
        ini += 1000


def temas_na_fila():
    """Mesma regra da fila do app: tema com arquivos, sem a versão da IA (ou com arquivo novo, ou sem as questões novas),
    e sem áudio/vídeo ainda na transcrição."""
    docs = tudo("documentos", "id,materia_id,criado_em")
    try:   # SQL v14: colunas pequenas (não lê o conteúdo inteiro dos temas)
        res = {r["materia_id"]: r for r in tudo("resumos", "materia_id,versao:st_versao,qversao:st_qversao,docs:st_docs,geradoEm:st_gerado_em")}
    except requests.HTTPError:
        res = {r["materia_id"]: r for r in tudo("resumos", "materia_id,versao:dados->versao,qversao:dados->qversao,docs:dados->docs,geradoEm:dados->>geradoEm")}
    carregando = {m["materia_id"] for m in tudo("midias", "materia_id,status") if m["status"] in ("fila", "processando")}
    por_tema = {}
    for d in docs:
        por_tema.setdefault(d["materia_id"], []).append(d)
    fila = []
    for mid, ds in por_tema.items():
        if mid in carregando:
            continue
        r = res.get(mid) or {}
        pronto = str(r.get("versao")) == "4"
        if not pronto:
            fila.append(mid)
            continue
        if isinstance(r.get("docs"), list):
            novos = [d for d in ds if d["id"] not in r["docs"]]
        else:
            novos = [d for d in ds if not (r.get("geradoEm") and d["criado_em"] <= r["geradoEm"])]
        if novos or int(r.get("qversao") or 0) < QVERSAO:
            fila.append(mid)
    return fila


def _total(tabela, filtros=None):
    """Quantas linhas a tabela tem (o Supabase manda só o número, sem as linhas)."""
    r = requests.head(f"{URL}/rest/v1/{tabela}", params={"select": "*", **(filtros or {})},
                      headers={**H, "Prefer": "count=exact", "Range": "0-0"}, timeout=60)
    r.raise_for_status()
    return r.headers.get("Content-Range", "*/0").split("/")[-1]


def _mais_novo(tabela, coluna):
    r = requests.get(f"{URL}/rest/v1/{tabela}", params={"select": coluna, "order": f"{coluna}.desc.nullslast", "limit": "1"}, headers=H, timeout=60)
    r.raise_for_status()
    lote = r.json()
    return (lote[0] or {}).get(coluna) if lote else None


ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ultima-checagem.json")


def assinatura():
    """Um resumo minúsculo do banco: quantos arquivos e temas, a mudança mais nova e os áudios/vídeos na transcrição.
    Se nada disso mudou desde a última checagem (que achou a fila vazia), não precisa ler as tabelas inteiras."""
    return "|".join(str(x) for x in (QVERSAO, _total("documentos"), _mais_novo("documentos", "criado_em"),
                                         _total("resumos"), _mais_novo("resumos", "atualizado_em"),
                                         _total("midias", {"status": "in.(fila,processando)"})))


def temas_na_fila_economico():
    """A cada 15 minutos o Windows pergunta se há trabalho. Ler as tabelas inteiras toda vez gastava a cota de tráfego
    do Supabase à toa; agora só lê tudo quando algo mudou (e, por garantia, pelo menos a cada 6 horas)."""
    try:
        sig = assinatura()
    except requests.RequestException:
        return temas_na_fila()
    try:
        with open(ESTADO, encoding="utf-8") as f:
            antes = json.load(f)
    except (OSError, ValueError):
        antes = {}
    if antes.get("sig") == sig and antes.get("fila") == 0 and time.time() - antes.get("em", 0) < 6 * 3600:
        return []
    fila = temas_na_fila()
    try:
        with open(ESTADO, "w", encoding="utf-8") as f:
            json.dump({"sig": sig, "fila": len(fila), "em": time.time()}, f)
    except OSError:
        pass
    return fila


def envios_na_fila():
    """Pastas do Drive que alguém deixou para o robô enviar (SQL v15). Sem o v15, nenhuma."""
    try:
        r = requests.get(f"{URL}/rest/v1/envios_fila", params={"select": "id", "status": "in.(fila,processando)"}, headers=H, timeout=60)
        return len(r.json()) if r.ok else 0
    except requests.RequestException:
        return 0


def preparar_conta():
    """Garante a conta do robô na turma e troca a senha por uma nova, sorteada agora."""
    r = requests.post(f"{URL}/rest/v1/membros", json={"email": EMAIL},
                      headers={**H, "Prefer": "resolution=ignore-duplicates,return=minimal"}, timeout=30)
    if r.status_code >= 300 and r.status_code != 409:
        raise RuntimeError(f"Não consegui pôr o robô na lista de membros: {r.status_code} {r.text[:200]}")
    senha = secrets.token_urlsafe(32)
    r = requests.post(f"{URL}/auth/v1/admin/users", json={"email": EMAIL, "password": senha, "email_confirm": True,
                      "user_metadata": {"full_name": "Robô da IA"}}, headers=H, timeout=30)
    if r.ok:
        return senha
    # a conta já existe: acha e troca a senha
    pagina = 1
    while True:
        lr = requests.get(f"{URL}/auth/v1/admin/users", params={"page": pagina, "per_page": 200}, headers=H, timeout=30)
        lr.raise_for_status()
        users = lr.json().get("users", [])
        u = next((x for x in users if (x.get("email") or "").lower() == EMAIL), None)
        if u:
            pr = requests.put(f"{URL}/auth/v1/admin/users/{u['id']}", json={"password": senha, "email_confirm": True}, headers=H, timeout=30)
            if not pr.ok:
                raise RuntimeError(f"Não consegui trocar a senha do robô: {pr.status_code} {pr.text[:200]}")
            return senha
        if len(users) < 200:
            raise RuntimeError(f"Não consegui criar a conta do robô: {r.status_code} {r.text[:200]}")
        pagina += 1


_token = {"valor": None, "ate": 0}
_token_trava = threading.Lock()


def token_drive():
    """Acesso de leitura ao Drive com a conta de serviço guardada neste computador (vale ~1 hora)."""
    with _token_trava:
        if not _token["valor"] or time.time() > _token["ate"]:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
            cred = service_account.Credentials.from_service_account_info(
                json.loads(os.environ["GOOGLE_SA_KEY"]), scopes=["https://www.googleapis.com/auth/drive.readonly"])
            cred.refresh(Request())
            _token.update(valor=cred.token, ate=time.time() + 45 * 60)
        return _token["valor"]


CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type",
        "Access-Control-Allow-Methods": "GET, OPTIONS"}


def baixar_do_drive(route):
    """O app do robô baixa os arquivos do Drive pela função "drive" do Supabase, e cada byte contava na cota de tráfego
    (Egress) do plano grátis. Aqui o arquivo vem direto do Google para este computador; o Supabase nem fica sabendo.
    Se algo falhar, deixa o pedido seguir pelo caminho antigo."""
    req = route.request
    if req.method == "OPTIONS":
        return route.fulfill(status=204, headers=CORS)
    try:
        q = parse_qs(urlparse(req.url).query)
        fid, exportar = q.get("id", [""])[0], q.get("exportar", [""])[0]
        if not fid or not os.environ.get("GOOGLE_SA_KEY"):
            return route.continue_()
        base = f"https://www.googleapis.com/drive/v3/files/{quote(fid)}"
        url = f"{base}/export?mimeType={quote(exportar)}" if exportar else f"{base}?alt=media&supportsAllDrives=true"
        r = requests.get(url, headers={"Authorization": "Bearer " + token_drive()}, timeout=600)
        if r.status_code >= 300:
            log(f"Drive direto respondeu {r.status_code}; usando o caminho antigo.")
            return route.continue_()
        route.fulfill(status=200, body=r.content,
                      headers={**CORS, "Content-Type": r.headers.get("Content-Type", "application/octet-stream")})
    except Exception as e:  # noqa: BLE001
        log(f"Drive direto falhou ({e}); usando o caminho antigo.")
        route.continue_()


def organizar():
    from playwright.sync_api import sync_playwright

    senha = preparar_conta()
    log(f"Conta do robô pronta ({EMAIL}). Abrindo o app {APP}")
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page()

        def no_console(m):
            t = m.text
            if t.startswith("[robo]"):
                log(t[7:])
            elif m.type == "error":
                log("app (erro): " + t[:300])
        pag.on("console", no_console)
        pag.on("pageerror", lambda e: log(f"app (erro): {e}"))
        pag.route(lambda u: "/functions/v1/drive" in u and "acao=baixar" in u, baixar_do_drive)
        pag.goto(APP + "/?robo=1#/", wait_until="load", timeout=120_000)
        pag.wait_for_function("() => typeof RoboIA !== 'undefined' && !!(App.store && App.store.sb)", timeout=120_000)
        pag.evaluate("([e, s]) => RoboIA.entrar(e, s)", [EMAIL, senha])
        log("Robô entrou no app. Organizando a fila.")
        pag.evaluate(f"() => {{ RoboIA.rodar({MINUTOS}, {SIMULTANEOS}); }}")
        limite = time.time() + MINUTOS * 60 + 50 * 60   # o tema em andamento termina; depois disso desiste
        ultimo_aviso = time.time()
        while time.time() < limite:
            pag.wait_for_timeout(20_000)        # (e não time.sleep: assim os downloads do Drive continuam sendo atendidos)
            st = pag.evaluate("() => RoboIA.estado")
            if not st["rodando"] and st["fim"]:
                break
            if time.time() - ultimo_aviso > 300:          # a cada 5 minutos, um sinal de vida no registro
                ultimo_aviso = time.time()
                log(f"(trabalhando: {len(st.get('feitos', []))} publicados até agora; agora: {st.get('msg') or '...'})")
        nav.close()
    feitos, erros = st.get("feitos", []), st.get("erros", [])
    log(f"Fim ({st.get('fim') or 'tempo esgotado'}). Publicados: {len(feitos)}. Com erro: {len(erros)}.")
    for x in feitos:
        log("  publicado: " + x)
    for x in erros:
        log("  erro: " + x)
    if st.get("fim") == "cota":
        log("A cota gratuita das IAs acabou por agora. A próxima rodada continua de onde parou.")


def manter_acordado():
    """No Windows, o computador não dorme enquanto o robô trabalha (a tela pode apagar). Volta ao normal quando ele termina."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        except Exception:
            pass


def principal():
    manter_acordado()
    if "--checar" in sys.argv:
        fila = temas_na_fila_economico()
        envios = envios_na_fila()
        if envios:
            log(f"Pastas do Drive esperando o robô enviar: {envios}")
        # a rodada só é pulada quando não há tema para a IA NEM pasta para enviar
        log(f"Temas esperando a IA: {len(fila) + envios}")
        saida = os.environ.get("GITHUB_OUTPUT")
        if saida:
            with open(saida, "a") as f:
                f.write(f"temas={len(fila)}\n")
    else:
        organizar()


if __name__ == "__main__":
    try:
        principal()
    except SystemExit:
        raise
    except BaseException as e:                         # qualquer falha fica no registro
        import traceback
        log(f"ERRO inesperado: {e}")
        log(traceback.format_exc())
        raise
