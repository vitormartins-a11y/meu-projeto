"""
Transcritor do Acervo da Turma. Roda no computador de quem administra a turma (Windows: o instalador agenda uma
rodada a cada 15 minutos) ou em qualquer máquina com Python e ffmpeg.

Se mais de um computador rodar ao mesmo tempo, cada um pega um item diferente da fila.
Ordem da fila: primeiro os ÁUDIOS, depois os VÍDEOS. Para cada item:
  1. baixa do Google Drive com o e-mail robô (conta de serviço);
  2. separa o áudio (ffmpeg), divide em partes de 10 minutos e transcreve várias partes ao mesmo tempo:
     primeiro no Groq (Whisper large-v3; quando a cota dele acaba, Whisper large-v3-turbo, que tem cota própria);
     quando as duas cotas acabam, transcreve no próprio robô (Whisper aberto, sem cota, só mais lento);
  3. nos vídeos, ao mesmo tempo que a transcrição: um print a cada mudança de tela (slides), descartando quadros
     que mostram só o professor e borrando rostos pequenos (ex.: janelinha da câmera);
  4. grava no Supabase um documento com páginas de ~5 minutos, com marcação de tempo e as figuras
     no ponto certo da fala. Depois a IA do app organiza o tema.

Chaves (variáveis de ambiente; no Windows o instalador guarda cifradas): SUPABASE_URL, SUPABASE_SERVICE_KEY, GOOGLE_SA_KEY, GROQ_API_KEY.
Opcionais: GROQ_MODELOS (padrão "whisper-large-v3,whisper-large-v3-turbo"), GROQ_PARALELO (partes ao mesmo tempo, padrão 3),
WHISPER_LOCAL (modelo do robô, padrão "large-v3-turbo"; "nao" desliga), ROBO (número do robô, só para os registros).
Teste sem rede: SIMULAR=1 python transcritor.py arquivo.mp4
Conferir as chaves: python transcritor.py --testar
"""
import json, math, os, re, shutil, subprocess, sys, tempfile, threading, time, unicodedata, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import cv2
import numpy as np
import requests

SIMULAR = os.environ.get('SIMULAR') == '1'
INICIO = time.time()
ORCAMENTO = int(os.environ.get('TEMPO_MAX', str(5 * 3600)))          # tempo máximo de uma rodada
BLOCO_PAGINA = 300                                                     # segundos de fala por página
PARTE_AUDIO = 600                                                      # segundos por arquivo enviado ao Groq
ROBO = os.environ.get('ROBO', '1')
GROQ_MODELOS = [m.strip() for m in os.environ.get('GROQ_MODELOS', os.environ.get('GROQ_MODEL', 'whisper-large-v3') + ',whisper-large-v3-turbo').split(',') if m.strip()]
GROQ_PARALELO = max(1, int(os.environ.get('GROQ_PARALELO', '3')))
WHISPER_LOCAL = os.environ.get('WHISPER_LOCAL', 'large-v3-turbo')

def agora(): return datetime.now(timezone.utc).isoformat()
def resta(): return ORCAMENTO - (time.time() - INICIO)
_trava_log = threading.Lock()
def log(*a):
    with _trava_log: print(time.strftime('%H:%M:%S'), f'[robô {ROBO}]', *a, flush=True)
def norm(s): return ''.join(c for c in unicodedata.normalize('NFD', (s or '').lower()) if unicodedata.category(c) != 'Mn')
def hms(s): s = int(s); return f'{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}' if s >= 3600 else f'{s // 60:02d}:{s % 60:02d}'

# ----------------------------- Supabase -----------------------------
if not SIMULAR:
    SB = os.environ['SUPABASE_URL'].rstrip('/'); SK = os.environ['SUPABASE_SERVICE_KEY']
    H = {'apikey': SK, 'Authorization': f'Bearer {SK}', 'Content-Type': 'application/json'}
def sb(method, path, **kw):
    hdr = {**H, **kw.pop('headers', {})}
    for t in range(4):
        r = requests.request(method, f'{SB}/rest/v1/{path}', headers=hdr, timeout=90, **kw)
        if r.status_code < 500: break
        time.sleep(5 * (t + 1))
    if r.status_code >= 300: raise RuntimeError(f'Supabase {r.status_code}: {r.text[:300]}')
    return r.json() if r.text else None
def enviar_imagem(dono, caminho_local):
    nome = f'{dono}/{uuid.uuid4()}.jpg'
    with open(caminho_local, 'rb') as f: dados = f.read()
    for t in range(4):
        r = requests.post(f'{SB}/storage/v1/object/paginas/{nome}', data=dados, timeout=120,
                          headers={'apikey': SK, 'Authorization': f'Bearer {SK}', 'Content-Type': 'image/jpeg', 'x-upsert': 'true'})
        if r.status_code < 300: return 'sb:' + nome
        time.sleep(5 * (t + 1))
    raise RuntimeError(f'Falha ao enviar imagem: {r.status_code} {r.text[:200]}')

def pegar_item():
    """Reserva o próximo item: áudios antes de vídeos, mais antigos primeiro. Só um robô consegue reservar cada item."""
    for it in sb('GET', 'midias?select=*&status=in.(fila,erro)&tentativas=lt.3&order=tipo.asc,criado_em.asc&limit=10'):
        r = sb('PATCH', f'midias?id=eq.{it["id"]}&status=in.(fila,erro)', json={'status': 'processando', 'tentativas': it['tentativas'] + 1, 'atualizado_em': agora()},
               headers={'Prefer': 'return=representation'})
        if r: return r[0]
    return None

# ----------------------------- Google Drive -----------------------------
def token_drive():
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    cred = service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_KEY']), scopes=['https://www.googleapis.com/auth/drive.readonly'])
    cred.refresh(Request()); return cred.token
def baixar(drive_id, destino):
    tok = token_drive()
    with requests.get(f'https://www.googleapis.com/drive/v3/files/{drive_id}?alt=media&supportsAllDrives=true', headers={'Authorization': f'Bearer {tok}'}, stream=True, timeout=300) as r:
        if r.status_code >= 300: raise RuntimeError(f'Drive {r.status_code}: {r.text[:200]}')
        with open(destino, 'wb') as f:
            for bloco in r.iter_content(1 << 20): f.write(bloco)

# ----------------------------- Áudio e transcrição -----------------------------
def duracao(arquivo):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', arquivo], capture_output=True, text=True)
    return float(json.loads(out.stdout or '{}').get('format', {}).get('duration') or 0)
def preparar_audio(origem, pasta):
    audio = os.path.join(pasta, 'audio.mp3')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', origem, '-vn', '-ac', '1', '-ar', '16000', '-b:a', '32k', audio], check=True)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', audio, '-f', 'segment', '-segment_time', str(PARTE_AUDIO), '-c', 'copy', os.path.join(pasta, 'parte_%03d.mp3')], check=True)
    return sorted(os.path.join(pasta, f) for f in os.listdir(pasta) if f.startswith('parte_'))
class PausaCota(Exception): pass

# Cota do Groq: quando um modelo responde "limite" com espera longa, ele fica de lado até liberar e o próximo é usado.
_esgotado_ate = {}
_trava_cota = threading.Lock()
def groq_disponivel():
    if SIMULAR or not os.environ.get('GROQ_API_KEY'): return []
    with _trava_cota: return [m for m in GROQ_MODELOS if _esgotado_ate.get(m, 0) <= time.time()]
def transcrever_groq(arquivo):
    """Tenta os modelos do Groq em ordem. Devolve None quando todos estão sem cota."""
    for modelo in GROQ_MODELOS:
        for t in range(4):
            with _trava_cota:
                if _esgotado_ate.get(modelo, 0) > time.time(): break
            with open(arquivo, 'rb') as f:
                r = requests.post('https://api.groq.com/openai/v1/audio/transcriptions', timeout=300, headers={'Authorization': f'Bearer {os.environ["GROQ_API_KEY"]}'},
                                  files={'file': (os.path.basename(arquivo), f, 'audio/mpeg')},
                                  data={'model': modelo, 'language': 'pt', 'response_format': 'verbose_json', 'temperature': '0'})
            if r.status_code == 200: return r.json().get('segments') or [{'start': 0, 'end': duracao(arquivo), 'text': r.json().get('text', '')}]
            if r.status_code == 429:
                espera = float(r.headers.get('retry-after') or 60)
                if espera <= 20: time.sleep(espera + 1); continue                     # limite por minuto: espera um pouco
                with _trava_cota: _esgotado_ate[modelo] = time.time() + espera            # cota da hora ou do dia: passa adiante
                log(f'Cota do Groq ({modelo}) acabou por {int(espera)} s; usando a próxima opção.')
                break
            if r.status_code >= 500: time.sleep(15 * (t + 1)); continue
            raise RuntimeError(f'Groq {r.status_code}: {r.text[:300]}')
    return None

# Whisper no próprio robô: sem cota, mais lento. Uma parte por vez (usa todos os núcleos do processador).
_modelo_local = None
_trava_local = threading.Lock()
def transcrever_local(arquivo):
    global _modelo_local
    with _trava_local:
        if _modelo_local is None:
            from faster_whisper import WhisperModel
            log(f'Carregando o Whisper do robô ({WHISPER_LOCAL})…')
            nucleos = int(os.environ.get('WHISPER_NUCLEOS') or max(1, (os.cpu_count() or 4) - 1))   # deixa um núcleo livre para usar o computador
            _modelo_local = WhisperModel(WHISPER_LOCAL, device='cpu', compute_type='int8', cpu_threads=nucleos)
        segs, _info = _modelo_local.transcribe(arquivo, language='pt', beam_size=int(os.environ.get('WHISPER_BEAM', '1')),
                                               vad_filter=True, condition_on_previous_text=False, temperature=0)
        return [{'start': s.start, 'end': s.end, 'text': s.text} for s in segs]
def local_ligado(): return WHISPER_LOCAL.lower() not in ('', 'nao', 'não', 'no', 'off', '0')

def transcrever_parte(arquivo):
    if SIMULAR:
        d = duracao(arquivo); time.sleep(0.2); return [{'start': s, 'end': min(d, s + 20), 'text': f'Trecho simulado de fala aos {hms(s)}.'} for s in range(0, int(d), 20)]
    if groq_disponivel():
        segs = transcrever_groq(arquivo)
        if segs is not None: return segs
    if local_ligado(): return transcrever_local(arquivo)
    raise PausaCota('Cota do Groq acabou e o Whisper do robô está desligado.')

# ----------------------------- Prints dos slides -----------------------------
ROSTOS = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
def dhash(img):
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (17, 16), interpolation=cv2.INTER_AREA)
    return (g[:, 1:] > g[:, :-1]).flatten()
def distancia(a, b): return int(np.count_nonzero(a != b))
def capturar_slides(video, pasta, maximo=60, intervalo=2):
    """Um print a cada mudança estável de tela. Descarta quadros dominados por rosto e borra rostos pequenos.
    O ffmpeg extrai um quadro a cada 2 s de uma vez (bem mais rápido que procurar quadro por quadro)."""
    quadros = os.path.join(pasta, 'quadros'); os.makedirs(quadros, exist_ok=True)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', video, '-an', '-vf', f"fps=1/{intervalo},scale='min(1280,iw)':-2", '-q:v', '4',
                    os.path.join(quadros, 'q_%06d.jpg')], check=True)
    arquivos = sorted(f for f in os.listdir(quadros) if f.startswith('q_'))
    saida = []; ultimo = None; candidato = None
    for k, nome in enumerate(arquivos):
        frame = cv2.imread(os.path.join(quadros, nome))
        if frame is None: continue
        t = k * intervalo
        if frame.std() < 12: candidato = None; continue                     # tela preta ou lisa
        h = dhash(frame)
        if candidato is not None:
            if distancia(h, candidato[1]) <= 6:                               # tela ficou parada: é um slide
                f0, h0, t0 = candidato; candidato = None
                if ultimo is None or distancia(h0, ultimo) > 14:
                    img = preparar_print(f0)
                    if img is not None:
                        caminho = os.path.join(pasta, f'slide_{len(saida):03d}.jpg'); cv2.imwrite(caminho, img, [cv2.IMWRITE_JPEG_QUALITY, 84])
                        saida.append({'t': t0, 'arquivo': caminho}); ultimo = h0
                        if len(saida) >= maximo: break
                continue
            candidato = None
        if ultimo is None or distancia(h, ultimo) > 14: candidato = (frame, h, t)
    for nome in arquivos:
        try: os.remove(os.path.join(quadros, nome))
        except OSError: pass
    return saida
def preparar_print(frame):
    alt, larg = frame.shape[:2]; escala = 1280 / max(larg, 1280); img = cv2.resize(frame, (int(larg * escala), int(alt * escala))) if escala < 1 else frame.copy()
    cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    rostos = ROSTOS.detectMultiScale(cinza, scaleFactor=1.15, minNeighbors=6, minSize=(40, 40))
    area = img.shape[0] * img.shape[1]
    if any(w * h > 0.06 * area for (x, y, w, h) in rostos): return None   # professor em destaque: não é um slide útil
    for (x, y, w, h) in rostos:                                           # rostos pequenos (câmera no canto): borra
        m = int(0.25 * w); x0, y0, x1, y1 = max(0, x - m), max(0, y - m), min(img.shape[1], x + w + m), min(img.shape[0], y + h + m)
        img[y0:y1, x0:x1] = cv2.GaussianBlur(img[y0:y1, x0:x1], (0, 0), 25)
    bordas = cv2.Canny(cinza, 80, 160); densidade = np.count_nonzero(bordas) / bordas.size
    if densidade < 0.004: return None                                     # quase sem conteúdo visual
    return img

# ----------------------------- Montagem das páginas -----------------------------
def montar_paginas(segmentos, slides, duracao_total):
    n = max(1, math.ceil(max(duracao_total, 1) / BLOCO_PAGINA)); paginas = []
    for k in range(n):
        ini, fim = k * BLOCO_PAGINA, (k + 1) * BLOCO_PAGINA
        segs = [s for s in segmentos if ini <= s['start'] < fim]
        figs = [sl for sl in slides if ini <= sl['t'] < fim]
        eventos = [(s['start'], 'fala', s) for s in segs] + [(f['t'], 'fig', f) for f in figs]
        eventos.sort(key=lambda e: (e[0], e[1] == 'fala'))
        linhas, paragrafo, ultimo_marcador, figuras = [], [], -999, []
        for t, tipo, x in eventos:
            if tipo == 'fig':
                if paragrafo: linhas.append(' '.join(paragrafo)); paragrafo = []
                linhas.append(f'[[FIG:{len(figuras)}]]'); figuras.append(x); continue
            texto = re.sub(r'\s+', ' ', x.get('text', '')).strip()
            if not texto: continue
            if t - ultimo_marcador >= 60 or not paragrafo:
                if paragrafo: linhas.append(' '.join(paragrafo)); paragrafo = []
                paragrafo.append(f'[{hms(t)}]'); ultimo_marcador = t
            paragrafo.append(texto)
        if paragrafo: linhas.append(' '.join(paragrafo))
        if linhas: paginas.append({'titulo': f'Aula transcrita: {hms(ini)} a {hms(min(fim, duracao_total))}', 'texto': '\n'.join(linhas), 'figuras': figuras})
    return paginas

def processar(item):
    pasta = tempfile.mkdtemp(prefix='acervo_')
    try: return _processar(item, pasta)
    finally:
        if not SIMULAR: shutil.rmtree(pasta, ignore_errors=True)   # o vídeo baixado e as partes do áudio não ficam no disco
def _processar(item, pasta):
    origem = os.path.join(pasta, 'origem')
    log(f'Baixando {item["nome"]} ({item["tipo"]})'); baixar(item['drive_id'], origem)
    dur = duracao(origem); log(f'Duração: {hms(dur)}')
    rapido = bool(groq_disponivel())
    if dur > resta() * (4 if rapido else 1.2): raise PausaCota('Pouco tempo restante neste ciclo; fica para o próximo.')
    partes = preparar_audio(origem, pasta)
    with ThreadPoolExecutor(max_workers=GROQ_PARALELO + 1) as ex:
        # prints dos slides em paralelo com a transcrição
        fut_slides = ex.submit(capturar_slides, origem, pasta) if item['tipo'] == 'video' else None
        def uma(i_parte):
            i, parte = i_parte; log(f'Transcrevendo parte {i + 1} de {len(partes)}')
            return [{**s, 'start': s['start'] + i * PARTE_AUDIO, 'end': s['end'] + i * PARTE_AUDIO} for s in transcrever_parte(parte)]
        with ThreadPoolExecutor(max_workers=GROQ_PARALELO) as ex2:
            segmentos = [s for lista in ex2.map(uma, enumerate(partes)) for s in lista]
        slides = fut_slides.result() if fut_slides else []
    log(f'{len(segmentos)} trechos de fala, {len(slides)} prints de slides')
    paginas = montar_paginas(segmentos, slides, dur)
    if not paginas: raise RuntimeError('Não foi possível entender fala neste arquivo.')
    if SIMULAR: return paginas
    dono = item.get('criado_por') or 'transcritor'; doc_id = str(uuid.uuid4()); linhas = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        refs_por_pagina = [list(ex.map(lambda f: enviar_imagem(dono, f['arquivo']), p['figuras'])) for p in paginas]
    for n, (p, refs) in enumerate(zip(paginas, refs_por_pagina), 1):
        linhas.append({'id': str(uuid.uuid4()), 'documento_id': doc_id, 'materia_id': item['materia_id'], 'n': n, 'titulo': p['titulo'], 'texto': p['texto'],
                       'texto_norm': norm(p['titulo'] + ' ' + re.sub(r'\[\[FIG:\d+\]\]', '', p['texto'])), 'html': None, 'imagem': None, 'imagens': [], 'figuras': refs, 'destaques': []})
    sb('POST', 'documentos', json={'id': doc_id, 'materia_id': item['materia_id'], 'nome': item['nome'], 'tipo': 'Vídeo' if item['tipo'] == 'video' else 'Áudio',
                                   'drive_id': item['drive_id'], 'ordem': int(time.time() * 1000), 'criado_por': item.get('criado_por'), 'criado_em': agora()})
    for i in range(0, len(linhas), 30): sb('POST', 'paginas', json=linhas[i:i + 30])
    sb('PATCH', f'midias?id=eq.{item["id"]}', json={'status': 'pronto', 'documento_id': doc_id, 'duracao_seg': int(dur), 'erro': None, 'atualizado_em': agora()})
    log(f'Pronto: {item["nome"]} ({len(linhas)} páginas)')

def testar():
    """Confere as 4 chaves sem transcrever nada. Devolve True se todas funcionam."""
    ok = True
    def item(nome, f):
        nonlocal ok
        try: f(); print(f'  OK   {nome}', flush=True)
        except Exception as e: ok = False; print(f'  ERRO {nome}: {str(e)[:200]}', flush=True)
    def groq():
        r = requests.get('https://api.groq.com/openai/v1/models', headers={'Authorization': f'Bearer {os.environ["GROQ_API_KEY"]}'}, timeout=30)
        if r.status_code >= 300: raise RuntimeError(f'Groq respondeu {r.status_code}: {r.text[:120]}')
    def ffmpeg():
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True); subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
    print('Conferindo:', flush=True)
    item('Supabase (endereço e chave de serviço)', lambda: sb('GET', 'midias?select=id&limit=1'))
    item('Google Drive (arquivo da conta de serviço)', token_drive)
    item('Groq (chave da API)', groq)
    item('ffmpeg (programa que separa o áudio)', ffmpeg)
    return ok

def main():
    if '--testar' in sys.argv: sys.exit(0 if testar() else 1)
    if SIMULAR:
        paginas = processar({'nome': os.path.basename(sys.argv[1]), 'tipo': 'video' if not sys.argv[1].endswith(('.mp3', '.m4a', '.wav')) else 'audio', 'drive_id': '', '_local': sys.argv[1]})
        print(json.dumps([{**p, 'figuras': [f['arquivo'] for f in p['figuras']]} for p in paginas], ensure_ascii=False, indent=1)); return
    # itens presos em "processando" há mais de 7 horas voltam para a fila
    limite = datetime.fromtimestamp(time.time() - 7 * 3600, timezone.utc).isoformat()
    sb('PATCH', f'midias?status=eq.processando&atualizado_em=lt.{str(limite).replace("+", "%2B")}', json={'status': 'fila'})
    feitos = 0
    while resta() > 600:
        item = pegar_item()
        if not item: break
        try: processar(item); feitos += 1
        except PausaCota as e:
            log(str(e)); sb('PATCH', f'midias?id=eq.{item["id"]}', json={'status': 'fila', 'tentativas': max(0, item['tentativas'] - 1), 'atualizado_em': agora()}); break
        except Exception as e:
            log('Erro:', e); sb('PATCH', f'midias?id=eq.{item["id"]}', json={'status': 'erro', 'erro': str(e)[:500], 'atualizado_em': agora()})
    log(f'Fim do ciclo: {feitos} arquivo(s) transcrito(s).')

if __name__ == '__main__':
    if SIMULAR and len(sys.argv) > 1:
        _baixar = baixar
        def baixar(drive_id, destino):  # noqa: F811  (teste local: usa o arquivo informado)
            import shutil; shutil.copy(sys.argv[1], destino)
    main()
