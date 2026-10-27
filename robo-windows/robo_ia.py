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
import re
import secrets
import sys
import threading
import time
from urllib.parse import parse_qs, quote, urlparse

import requests

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")   # os processos do leitor de PDF importam este arquivo sem as chaves
APP = os.environ.get("APP_URL", "https://acervodaturma.pages.dev").rstrip("/")
EMAIL = os.environ.get("ROBO_EMAIL", "robo-ia@example.com").strip().lower()
MINUTOS = int(os.environ.get("MINUTOS", "300"))
SIMULTANEOS = int(os.environ.get("SIMULTANEOS", "2"))
# revisão das figuras do acervo antigo pela IA: relê cada PDF antigo e gasta tráfego do Supabase; desligada por padrão
REVISAR_FIGURAS = os.environ.get("REVISAR_FIGURAS", "").strip() == "1"
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


def osce_na_fila():
    """OSCE de alunos com temas ainda sem estações (a pessoa fechou a página): o robô termina (SQL v44)."""
    try:
        desde = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60 * 86400))
        r = requests.get(f"{URL}/rest/v1/meus_estudos", params={"select": "id", "tipo": "eq.osce", "dados->grupos": 'cs.[{"pendente":true}]',
                         "atualizado_em": f"gt.{desde}", "limit": "50"}, headers=H, timeout=60)
        return len(r.json()) if r.ok else 0
    except (requests.RequestException, ValueError):
        return 0


def envios_na_fila():
    """Pastas do Drive que alguém deixou para o robô enviar (SQL v15). Sem o v15, nenhuma."""
    try:
        r = requests.get(f"{URL}/rest/v1/envios_fila", params={"select": "id", "status": "in.(fila,processando)"}, headers=H, timeout=60)
        return len(r.json()) if r.ok else 0
    except requests.RequestException:
        return 0


def imagens_na_fila():
    """PDFs e imagens do Drive que ficaram sem as imagens (SQL v26); os enviados há menos de 3 horas não contam
    (o envio deles ainda pode estar fazendo as imagens). Sem o v26, nenhum."""
    try:
        desde = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3 * 3600))
        r = requests.get(f"{URL}/rest/v1/documentos", params={"select": "id", "imagens_em": "is.null", "tipo": "in.(PDF,Imagem)",
                         "drive_id": "not.is.null", "criado_em": f"lt.{desde}", "limit": "50"}, headers=H, timeout=60)
        return len(r.json()) if r.ok else 0
    except (requests.RequestException, ValueError):
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


EXPORTAVEIS = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               "application/vnd.openxmlformats-officedocument.presentationml.presentation", "text/csv"}
CORS = {"Access-Control-Allow-Origin": APP, "Access-Control-Allow-Headers": "authorization, apikey, content-type",
        "Access-Control-Allow-Methods": "GET, OPTIONS"}


def baixar_do_drive(route):
    """O app do robô baixa os arquivos do Drive pela função "drive" do Supabase, e cada byte contava na cota de tráfego
    (Egress) do plano grátis. Aqui o arquivo vem direto do Google para este computador; o Supabase nem fica sabendo.
    Se algo falhar, deixa o pedido seguir pelo caminho antigo."""
    req = route.request
    if req.method == "OPTIONS":
        return route.fulfill(status=204, headers=CORS)
    try:
        u = urlparse(req.url)
        if u.netloc != urlparse(URL).netloc:                # só os pedidos ao Supabase do site (nenhum outro endereço)
            return route.abort()
        q = parse_qs(u.query)
        fid, exportar = q.get("id", [""])[0], q.get("exportar", [""])[0]
        if not re.fullmatch(r"[\w-]{10,200}", fid) or (exportar and exportar not in EXPORTAVEIS):
            return route.fulfill(status=400, body="pedido inválido", headers=CORS)
        if not os.environ.get("GOOGLE_SA_KEY"):
            return route.continue_()
        base = f"https://www.googleapis.com/drive/v3/files/{quote(fid, safe='')}"
        url = f"{base}/export?mimeType={quote(exportar)}" if exportar else f"{base}?alt=media&supportsAllDrives=true"
        r = requests.get(url, headers={"Authorization": "Bearer " + token_drive()}, timeout=600)
        if r.status_code == 404:                              # o arquivo não existe mais (ou não está compartilhado):
            return route.fulfill(status=404, body="arquivo não encontrado no Drive", headers=CORS)   # o caminho antigo daria o mesmo
        if r.status_code >= 300:
            log(f"Drive direto respondeu {r.status_code}; usando o caminho antigo.")
            return route.continue_()
        tipo_arq = r.headers.get("Content-Type", "application/octet-stream")
        guardado = False
        if LEITOR and not exportar and (tipo_arq.startswith("application/pdf") or tipo_arq.startswith("image/")):
            try:
                LEITOR.guardar(fid, r.content)                    # o leitor rápido usa este mesmo arquivo (não baixa de novo)
                guardado = True
            except OSError:
                pass
        # PDF grande (apostila de centenas de páginas): o navegador do robô não recebe o arquivo, só um aviso pequeno.
        # Quem lê é o leitor rápido, que já tem o arquivo aqui. Antes, PDFs de centenas de MB derrubavam o navegador.
        if guardado and tipo_arq.startswith("application/pdf") and len(r.content) > PDF_GRANDE:
            log(f"PDF grande ({len(r.content) // 1_000_000} MB): só o leitor rápido lê, fora do navegador.")
            return route.fulfill(status=200, body=b"%PDF-LEITOR-NATIVO", headers={**CORS, "Content-Type": tipo_arq})
        route.fulfill(status=200, body=r.content, headers={**CORS, "Content-Type": tipo_arq})
    except Exception as e:  # noqa: BLE001
        log(f"Drive direto falhou ({e}); usando o caminho antigo.")
        route.continue_()


# ------------------------------------------------------------------ leitor nativo (PDFs e imagens fora do navegador)
SEGREDOS = ("SUPABASE_SERVICE_KEY", "GOOGLE_SA_KEY", "GROQ_API_KEY")
PDF_GRANDE = 15_000_000          # acima disto, o PDF não vai para o navegador do robô (só o leitor rápido lê)


def _sem_segredos():
    for k in SEGREDOS:
        os.environ.pop(k, None)
    # o OCR embutido escreve um aviso por linha que não consegue ler ("Image too small to scale!!", "Line cannot be
    # recognized!!") direto na saída de erros; nos processos do leitor isso só enchia o registro (os erros de verdade
    # voltam pelo próprio pedido)
    try:
        nulo = os.open(os.devnull, os.O_WRONLY)
        os.dup2(nulo, 2)
    except OSError:
        pass


def _aquecer(_):
    time.sleep(0.5)
    return os.getpid()


class Leitor:
    """O app do robô pede a leitura de um arquivo do Drive em https://leitor.robo/ (endereço que só existe dentro do
    navegador do robô; quem responde é este programa). O trabalho pesado roda em vários processos, cada um com algumas
    páginas, e o app pergunta de tempos em tempos se ficou pronto. Os processos que abrem os arquivos dos alunos não
    recebem as chaves secretas (como o navegador do robô)."""

    def __init__(self):
        import leitor_nativo
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        self.ln = leitor_nativo
        self.rec = leitor_nativo.recursos()
        if not self.rec.get("ok"):
            raise RuntimeError("faltam as bibliotecas do leitor (rode o INSTALAR.bat de novo)")
        if not os.environ.get("GOOGLE_SA_KEY"):
            raise RuntimeError("sem a chave do Google, o robô não baixa direto do Drive")
        self.n = max(1, (os.cpu_count() or 2) - 1)               # um núcleo fica para o navegador do robô
        guardados = {k: os.environ[k] for k in SEGREDOS if k in os.environ}
        _sem_segredos()
        try:                                                      # todos os processos nascem agora, já sem as chaves
            self.pool = ProcessPoolExecutor(self.n, mp_context=multiprocessing.get_context("spawn"), initializer=_sem_segredos)
            list(self.pool.map(_aquecer, range(self.n * 2)))
        finally:
            os.environ.update(guardados)
        self.cache = os.path.join(os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp", "acervo-leitor")
        os.makedirs(self.cache, exist_ok=True)
        self.trabalhos, self.trava = {}, threading.Lock()
        self.limpar(0)

    def arquivo(self, fid):
        return os.path.join(self.cache, fid)

    def guardar(self, fid, dados):
        tmp = self.arquivo(fid) + ".tmp"
        with open(tmp, "wb") as f:
            f.write(dados)
        os.replace(tmp, self.arquivo(fid))

    def limpar(self, idade=3 * 3600):
        """Arquivos baixados e resultados que ninguém buscou, com mais de 'idade' segundos."""
        agora = time.time()
        for nome in os.listdir(self.cache):
            c = os.path.join(self.cache, nome)
            try:
                if agora - os.path.getmtime(c) > idade:
                    os.remove(c)
            except OSError:
                pass
        with self.trava:
            for k in [k for k, t in self.trabalhos.items() if t["pronto"] and agora - t["em"] > 2 * 3600]:
                del self.trabalhos[k]

    def pedir(self, fid, tipo, modo, de=None, n=None):
        """Com 'de' e 'n', devolve as páginas aos poucos (o app pede um lote de cada vez): um arquivo de centenas de
        páginas não chega de uma vez só ao navegador (antes ele ficava sem memória e fechava)."""
        chave = (fid, tipo, modo)
        with self.trava:
            t = self.trabalhos.get(chave)
            if not t:
                t = self.trabalhos[chave] = {"pronto": False, "res": None, "erro": None, "etapa": "na fila", "em": time.time()}
                threading.Thread(target=self._rodar, args=(fid, tipo, modo, t), daemon=True).start()
            if not t["pronto"]:
                return 202, {"espera": True, "etapa": t["etapa"]}
            if t["erro"] or de is None:
                del self.trabalhos[chave]
                return (500, {"erro": t["erro"]}) if t["erro"] else (200, t["res"])
            pags = (t["res"] or {}).get("paginas") or []
            marcadores = (t["res"] or {}).get("marcadores") if de == 0 else None
            fatia = pags[de:de + n]
            if de + n >= len(pags):
                del self.trabalhos[chave]
            else:
                t["em"] = time.time()
        corpo = {"paginas": fatia, "total": len(pags), "de": de}
        if marcadores:
            corpo["marcadores"] = marcadores
        return 200, corpo

    def _baixar(self, fid):
        r = requests.get(f"https://www.googleapis.com/drive/v3/files/{quote(fid, safe='')}?alt=media&supportsAllDrives=true",
                         headers={"Authorization": "Bearer " + token_drive()}, timeout=600)
        if r.status_code >= 300:
            raise RuntimeError(f"o Drive respondeu {r.status_code}")
        self.guardar(fid, r.content)

    def _rodar(self, fid, tipo, modo, t):
        arq = self.arquivo(fid)
        try:
            if not os.path.isfile(arq):
                t["etapa"] = "baixando o arquivo"
                self._baixar(fid)
            ocr = self.rec.get("ocr")
            if tipo == "Imagem":
                t["res"] = {"paginas": [self.pool.submit(self.ln.imagem, arq, ocr).result()]}
            elif modo == "indice":
                t["res"] = {"marcadores": self.pool.submit(self.ln.indice_pdf, arq).result()}
            elif modo.startswith("fotos:"):                          # só a foto de algumas páginas ("Ver página inteira")
                indices = [int(x) for x in modo[6:].split(",") if x.isdigit()][:50]
                t["res"] = {"paginas": self.pool.submit(self.ln.fotos_pdf, arq, indices).result()}
            elif modo == "texto":
                t["res"] = {"paginas": self.pool.submit(self.ln.texto_pdf, arq).result()}
                try:                                              # índice clicável: vai junto, no primeiro lote
                    t["res"]["marcadores"] = self.pool.submit(self.ln.indice_pdf, arq).result()
                except Exception:  # noqa: BLE001
                    pass
                with self.trava:                                  # a etapa das imagens vem logo depois: já começa
                    adiantados = sum(1 for (_, _, m) in self.trabalhos if m == "imagens")
                if adiantados < 2 * self.n:                       # (sem guardar resultados demais na memória)
                    self.pedir(fid, tipo, "imagens")
            else:
                n = self.pool.submit(self.ln.contar_paginas, arq).result()
                lote = max(1, min(4, -(-n // (self.n * 2))))          # páginas por processo (todos os núcleos trabalham)
                futs = [self.pool.submit(self.ln.imagens_pdf, arq, list(range(i, min(n, i + lote))), ocr) for i in range(0, n, lote)]
                paginas = []
                for f in futs:
                    paginas += f.result()
                    t["etapa"] = f"página {len(paginas)} de {n}"
                t["res"] = {"paginas": paginas}
        except Exception as e:  # noqa: BLE001
            t["erro"] = str(e)[:300] or e.__class__.__name__
        finally:
            t["pronto"], t["em"] = True, time.time()
            if modo in ("imagens", "indice") or modo.startswith("fotos:") or tipo == "Imagem":
                try:
                    os.remove(arq)
                except OSError:
                    pass

    def fechar(self):
        self.pool.shutdown(wait=False, cancel_futures=True)


LEITOR = None
CORS_LEITOR = {"Access-Control-Allow-Origin": APP, "Access-Control-Allow-Methods": "GET, OPTIONS", "Cache-Control": "no-store"}


def leitor_rota(route):
    """Pedidos do app do robô ao leitor nativo (https://leitor.robo/...). Responde na hora: o trabalho segue nos processos."""
    req = route.request
    if req.method == "OPTIONS":
        return route.fulfill(status=204, headers=CORS_LEITOR)
    try:
        u = urlparse(req.url)
        q = parse_qs(u.query)
        if u.path == "/saude":
            corpo = {"ok": LEITOR is not None, "ocr": LEITOR.rec.get("ocr") if LEITOR else None, "nucleos": LEITOR.n if LEITOR else 0}
            return route.fulfill(status=200, body=json.dumps(corpo), headers={**CORS_LEITOR, "Content-Type": "application/json"})
        fid, tipo, modo = q.get("id", [""])[0], q.get("tipo", [""])[0], q.get("modo", [""])[0]
        if modo == "fotos":                                          # páginas pedidas: "3,7,12" (até 50)
            p = q.get("p", [""])[0]
            modo = "fotos:" + p if re.fullmatch(r"\d{1,5}(,\d{1,5}){0,49}", p) else "x"
        if u.path != "/ler" or not LEITOR or not re.fullmatch(r"[\w-]{10,200}", fid) or tipo not in ("PDF", "Imagem") or not (modo in ("texto", "imagens", "indice") or modo.startswith("fotos:")):
            return route.fulfill(status=400, body='{"erro": "pedido inválido"}', headers={**CORS_LEITOR, "Content-Type": "application/json"})
        if not LEITOR.trabalhos:
            LEITOR.limpar()
        de, n = q.get("de", [""])[0], q.get("n", [""])[0]
        lote = (int(de), max(1, min(500, int(n)))) if de.isdigit() and n.isdigit() else (None, None)
        st, corpo = LEITOR.pedir(fid, tipo, modo, *lote)
        route.fulfill(status=st, body=json.dumps(corpo), headers={**CORS_LEITOR, "Content-Type": "application/json"})
    except Exception as e:  # noqa: BLE001
        route.fulfill(status=500, body=json.dumps({"erro": str(e)[:200]}), headers={**CORS_LEITOR, "Content-Type": "application/json"})


def avisar_ligado(estado="conferindo a fila"):
    """Conta para o site que o robô está ligado (o aluno vê "o robô conferiu a fila há X min" na fila de envios)."""
    try:
        requests.post(f"{URL}/rest/v1/cache_ia", params={"on_conflict": "chave"},
                      headers={**H, "Prefer": "resolution=merge-duplicates,return=minimal"},
                      json={"chave": "robo:visto", "dados": {"em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "estado": estado},
                            "atualizado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, timeout=30)
    except requests.RequestException:
        pass


def figuras_na_fila():
    """PDFs do Drive que ainda não tiveram as figuras conferidas pela IA (SQL v27). Sem o v27, nenhum."""
    try:
        r = requests.get(f"{URL}/rest/v1/documentos", params={"select": "id", "figuras_rev": "is.null", "imagens_em": "not.is.null", "tipo": "eq.PDF",
                         "drive_id": "not.is.null", "limit": "50"}, headers=H, timeout=60)
        return len(r.json()) if r.ok else 0
    except (requests.RequestException, ValueError):
        return 0


def limpar_orfas():
    """Apaga do Storage as imagens que nenhuma página usa mais (figuras trocadas na revisão, arquivos apagados), com mais
    de 2 dias, no máximo a cada 3 dias. A conta é feita aqui no computador (liberar_espaco.py): antes era uma consulta no
    banco que passava do tempo limite e o lixo ficava acumulando. Apagar arquivos não gasta o tráfego do Supabase."""
    try:
        import liberar_espaco
        return liberar_espaco.limpar_lixo()
    except Exception as e:  # noqa: BLE001
        log(f"Limpeza das imagens: {e}")
        return 0


def organizar():
    from playwright.sync_api import sync_playwright
    global LEITOR
    try:
        LEITOR = Leitor()
        log(f"Leitor rápido de PDF pronto: {LEITOR.n} processos, OCR {LEITOR.rec.get('ocr') or 'no navegador'}.")
    except Exception as e:  # noqa: BLE001
        LEITOR = None
        log(f"Leitor rápido de PDF desligado ({e}); o robô lê os PDFs no navegador, como antes.")

    senha = preparar_conta()
    log(f"Conta do robô pronta ({EMAIL}). Abrindo o app {APP}")
    with sync_playwright() as p:
        # o navegador abre conteúdo enviado por alunos: ele não recebe as chaves secretas (ficam só neste programa)
        segredos = {"SUPABASE_SERVICE_KEY", "GOOGLE_SA_KEY", "GROQ_API_KEY"}
        nav = p.chromium.launch(env={k: v for k, v in os.environ.items() if k not in segredos})
        pag = nav.new_page()

        def no_console(m):
            t = m.text
            if t.startswith("[robo]"):
                log(t[7:])
            elif m.type == "error":
                # "Failed to load resource" não diz qual: vai junto o endereço (sem a parte depois do "?", que pode ter chaves)
                onde = ((m.location or {}).get("url") or "").split("?")[0] if t.startswith("Failed to load resource") else ""
                log("app (erro): " + t[:300] + (f" [{onde[-120:]}]" if onde else ""))
        pag.on("console", no_console)
        pag.on("pageerror", lambda e: log(f"app (erro): {e}"))
        pag.route(lambda u: u.startswith(URL + "/functions/v1/drive?") and "acao=baixar" in u, baixar_do_drive)
        pag.route("https://leitor.robo/**", leitor_rota)
        pag.goto(APP + "/?robo=1" + ("&revisar=1" if REVISAR_FIGURAS else "") + "#/", wait_until="load", timeout=120_000)
        pag.wait_for_function("() => typeof RoboIA !== 'undefined' && !!(App.store && App.store.sb)", timeout=120_000)
        pag.evaluate("([e, s]) => RoboIA.entrar(e, s)", [EMAIL, senha])
        log("Robô entrou no app. Organizando a fila.")
        avisar_ligado("trabalhando")
        pag.evaluate(f"() => {{ RoboIA.rodar({MINUTOS}, {SIMULTANEOS}); }}")
        limite = time.time() + MINUTOS * 60 + 50 * 60   # o tema em andamento termina; depois disso desiste
        ultimo_aviso = time.time()
        while time.time() < limite:
            pag.wait_for_timeout(20_000)        # (e não time.sleep: assim os downloads do Drive continuam sendo atendidos)
            st = pag.evaluate("() => RoboIA.estado")
            if not st["rodando"] and st["fim"]:
                break
            if time.time() - ultimo_aviso > 300:          # a cada 5 minutos, um sinal de vida no registro (e para o site)
                ultimo_aviso = time.time()
                avisar_ligado("trabalhando")
                log(f"(trabalhando: {len(st.get('feitos', []))} publicados até agora; agora: {st.get('msg') or '...'})")
        nav.close()
    if LEITOR:
        LEITOR.fechar()
    feitos, erros = st.get("feitos", []), st.get("erros", [])
    log(f"Fim ({st.get('fim') or 'tempo esgotado'}). Publicados: {len(feitos)}. Com erro: {len(erros)}.")
    for x in feitos:
        log("  publicado: " + x)
    for x in erros:
        log("  erro: " + x)
    if st.get("fim") == "cota":
        log("A cota gratuita das IAs acabou por agora. A próxima rodada continua de onde parou.")
    limpar_orfas()


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
        avisar_ligado()
        fila = temas_na_fila_economico()
        envios = envios_na_fila()
        if envios:
            log(f"Pastas do Drive esperando o robô enviar: {envios}")
        imagens = imagens_na_fila()
        osce = osce_na_fila()
        if osce:
            log(f"OSCE de alunos esperando as estações: {osce}")
        if imagens:
            log(f"Arquivos sem as imagens, para o robô refazer: {imagens}{'+' if imagens >= 50 else ''}")
        figuras = figuras_na_fila() if REVISAR_FIGURAS else 0
        if figuras:
            log(f"Arquivos com figuras para a IA conferir: {figuras}{'+' if figuras >= 50 else ''}")
        # a rodada só é pulada quando não há tema para a IA, NEM pasta para enviar, NEM imagens para refazer ou conferir
        log(f"Temas esperando a IA: {len(fila) + envios + imagens + figuras + osce}")
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
