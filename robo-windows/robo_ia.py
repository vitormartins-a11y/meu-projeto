"""Robô da IA do Acervo da Turma.

Roda no GitHub Actions (de graça) e organiza com a IA os temas que estão na fila, sem ninguém com o app aberto.
Ele abre o próprio app num navegador sem tela (endereço com ?robo=1), entra com uma conta só dele e usa o mesmo
código do botão "Organizar ... temas agora". Por isso o resultado é igual ao do app.

A conta do robô é criada sozinha (robo-ia@example.com, só entra na lista "membros", não é administrador).
A senha é sorteada de novo a cada rodada e não fica guardada em lugar nenhum.

Segredos usados (os mesmos do robô de transcrição): SUPABASE_URL e SUPABASE_SERVICE_KEY.
Opcionais: APP_URL (endereço do app), ROBO_EMAIL, MINUTOS (tempo máximo de trabalho), SIMULTANEOS.

    python robo_ia.py --checar   -> só diz se há tema esperando a IA (para o GitHub decidir se liga o navegador)
    python robo_ia.py            -> organiza a fila
"""
import os
import secrets
import sys
import time

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
        pag.goto(APP + "/?robo=1#/", wait_until="load", timeout=120_000)
        pag.wait_for_function("() => typeof RoboIA !== 'undefined' && !!(App.store && App.store.sb)", timeout=120_000)
        pag.evaluate("([e, s]) => RoboIA.entrar(e, s)", [EMAIL, senha])
        log("Robô entrou no app. Organizando a fila.")
        pag.evaluate(f"() => {{ RoboIA.rodar({MINUTOS}, {SIMULTANEOS}); }}")
        limite = time.time() + MINUTOS * 60 + 50 * 60   # o tema em andamento termina; depois disso desiste
        ultimo_aviso = time.time()
        while time.time() < limite:
            time.sleep(20)
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


def principal():
    if "--checar" in sys.argv:
        fila = temas_na_fila()
        log(f"Temas esperando a IA: {len(fila)}")
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
