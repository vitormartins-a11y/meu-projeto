# Z-Anatomy (extraído por zextrai.py) -> arquivos da Anatomia 3D do site.
# Sistemas em .bin.gz (mesmo formato de antes, com cor por peça), nomes.json (busca) e acidentes (pontos, áreas,
# origens e inserções musculares).
import json, sys, re, gzip, os, pickle, collections, random
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from traduz import traduz
from subdiv import loop

ITENS, TA2, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
I = pickle.load(open(ITENS, 'rb')); POR_NOME = {i['nome']: i for i in I}
filhos = collections.defaultdict(list)
for i in I:
    if i.get('pai'): filhos[i['pai']].append(i)

# ---------- nomes ----------
EN2PT = {}
for l in open(TA2, encoding='utf-8-sig'):
    r = l.strip().strip('"').split(';')
    if len(r) > 5 and r[1] and r[5]: EN2PT.setdefault(r[1].strip().lower(), r[5].strip())
SUF = re.compile(r'\.(r|l|t|s|j|i|g|o\d*[lr]|e\d*[lr]|o\d*|e\d*)$')


def lado(n):
    m = re.search(r'\.(?:[oe]\d*)?([lr])$', n)
    return m.group(1) if m else ''


def base(n):
    n = SUF.sub('', n.strip()).strip()
    n = re.sub(r'^\((.*)\)$', r'\1', n).strip()
    return re.sub(r'\s+', ' ', n).strip(" '*")


def pt(en_base): return br(pt0(en_base))


def pt0(en_base):
    k = en_base.lower()
    if k in EN2PT: return EN2PT[k]
    m = re.match(r'^(.*?)\s*\(([^)]*)\)?\s*$', en_base)          # "Optic nerve (II)", "Middle cerebral artery (M1-segment"
    if m and m.group(1).lower() in EN2PT: return EN2PT[m.group(1).lower()] + ' (' + m.group(2).strip(' *') + ')'
    for a, b in ((' muscle', ''), ('', ' muscle'), (' muscles', ''), ('', ' muscles')):
        k2 = (k[:-len(a)] if a and k.endswith(a) else k) + b
        if k2 in EN2PT: return EN2PT[k2]
    t = traduz(re.sub(r'\s*\(.*$', '', en_base))
    return t or en_base


LADO_PT = {'r': 'direito', 'l': 'esquerdo'}
BR = [(r'\bfémur', 'fêmur'), (r'\bFémur', 'Fêmur'), (r'supra-renal', 'suprarrenal'), (r'mastóide', 'mastoide'), (r'hióide', 'hioide'), (r'coróide', 'corioide'),
      (r'^Entalhe', 'Incisura'), (r'\bentalhe', 'incisura'), (r'^Notch', 'Incisura'), (r'\bPólo\b', 'Polo'), (r'\bpólo\b', 'polo'), (r'^Bursa\b', 'Bolsa'), (r'\bbursa\b', 'bolsa'),
      (r'^Nódulos', 'Linfonodos'), (r'^Nódulo\b', 'Linfonodo'), (r'\bgemelo\b', 'gêmeo'), (r'milohióideo', 'milo-hióideo'), (r'^Testis\b', 'Testículo'),
      (r'\bincus\b', 'bigorna'), (r'\bIncus\b', 'Bigorna'), (r'^Placa de prego', 'Lâmina ungueal'), (r'^Pescoço d', 'Colo d'), (r'\bde ísquio', 'do ísquio'),
      (r'\bde osso\b', 'do osso'), (r'^Osso (primeiro|segundo|terceiro|quarto|quinto) (metatarso|metacarpo)', lambda m: m.group(1).capitalize() + ' osso ' + m.group(2)),
      (r'\bCapitulo\b', 'Capítulo'), (r'\bCrest\b', 'Crista'), (r'\bsacro-espinhoso', 'sacroespinal'), (r'\bfacto\b', 'fato'), (r'\bseção\b', 'secção'),
      (r'\bLingula\b', 'Língula'), (r'\bPars intermediário', 'Parte intermédia'), (r'iliocostalis', 'iliocostal'), (r'\bespinhal\b', 'espinal'),
      (r'\bcoróideo', 'corióideo'), (r'\bacção', 'ação'), (r'\bóptimo', 'ótimo'), (r'^Supinator\b', 'Músculo supinador'), (r'carpi radialis (longo|curto|longus|brevis)', lambda m: 'radial ' + {'longus': 'longo', 'brevis': 'curto'}.get(m.group(1), m.group(1)) + ' do carpo'), (r'carpi radialis', 'radial do carpo'), (r'carpi ulnaris', 'ulnar do carpo'), (r'\bde (úmero|fêmur|rádio|osso|sacro|cóccix|esterno|atlas|áxis|calcâneo|tálus|crânio|ílio|ísquio|púbis|hálux|polegar|dente|metacarpo|metatarso|martelo|estribo)\b', r'do \1'), (r'\bbrevis\b', 'curto'), (r'\blongus\b', 'longo'), (r'\bmagnus\b', 'magno'), (r'\bmaximus\b', 'máximo'), (r'\bminimus\b', 'mínimo'), (r'\bmedius\b', 'médio'), (r'(\w)\(', r'\1 (')]


def br(p):
    for a, b in BR: p = re.sub(a, b, p)
    p = re.sub(r'\b(\w+) \1\b', r'\1', p)                 # palavra repetida
    return re.sub(r'\s+', ' ', p).strip()


MASC_A = {'sistema', 'diafragma', 'plasma', 'dia', 'mapa', 'quiasma', 'parênquima', 'estroma', 'fibroma', 'colo', 'hálux', 'tórax', 'ápice', 'atlas', 'áxis',
          'ligamento', 'músculo', 'nervo', 'ramo', 'osso', 'dente', 'pé', 'lobo', 'lóbulo', 'trato', 'tronco', 'plexo', 'corpo', 'disco', 'arco', 'giro',
          'sulco', 'bíceps', 'tríceps', 'pâncreas', 'testículo', 'linfonodo', 'linfonodos', 'linfáticos', 'vaso', 'seio', 'núcleo', 'menisco', 'tendão',
          'retináculo', 'septo', 'colículo', 'pedúnculo', 'hipocampo', 'tálamo', 'cerebelo', 'cérebro', 'encéfalo', 'olho', 'cristalino', 'fígado', 'baço', 'rim',
          'estômago', 'esôfago', 'duodeno', 'jejuno', 'íleo', 'ceco', 'apêndice', 'reto', 'ânus', 'útero', 'ovário', 'ureter', 'pulmão', 'brônquio', 'coração',
          'átrio', 'ventrículo', 'folheto', 'cone', 'globo', 'putame', 'claustro', 'fórnice', 'quiasma', 'túber', 'hilo', 'canal', 'forame', 'processo', 'côndilo',
          'epicôndilo', 'tubérculo', 'trocânter', 'maléolo', 'meato', 'recesso', 'trígono', 'labro', 'lábio', 'ângulo', 'corno', 'polo', 'óstio', 'hiato'}
PLURAL_NAO = {'pâncreas', 'atlas', 'íris', 'pênis', 'bíceps', 'tríceps', 'áxis', 'tórax', 'ânus', 'hálux', 'testis', 'pars', 'lens'}


def com_lado(p, ld):
    if not ld: return p
    w = norm1(p.split(' ')[0])
    pl = w.endswith('s') and w not in PLURAL_NAO
    ws = w[:-1] if pl else w
    if pl and ws.endswith('e'): ws2 = ws[:-1]
    else: ws2 = ws
    fem = ws not in MASC_A and ws2 not in MASC_A and (ws.endswith(('a', 'ção', 'gem', 'dade', 'ura', 'ise', 'ite', 'são', 'ie', 'ade', 'ância', 'ência')) or ws2.endswith(('ção', 'gem', 'dade', 'são')) or w in ('pele', 'face', 'base', 'fóvea', 'córnea', 'íris', 'artérias', 'veias', 'falange', 'falanges', 'margem', 'pelve', 'cúspide', 'valva', 'cartilagem', 'mão', 'raiz', 'cápsula', 'membrana', 'lente', 'retina', 'esclera', 'túnica', 'parede', 'região', 'regiões'))
    lado_s = ('direit' if ld == 'r' else 'esquerd') + ('a' if fem else 'o') + ('s' if pl else '')
    return f'{p} {lado_s}'


def norm1(x):
    return x.lower()


# ---------- sistemas ----------
def topo(i): return i['cols'][0][0] if i['cols'] else ''
def mat(i): return (i.get('mat') or ('',))[0] or ''


EXCLUI = re.compile(r'^(Anterior segment of eyeball|Posterior segment of eyeball|Pleura|Greater omentum|Lesser omentum|Lymph node|Take a picture|HOW TO|Visceral systems|Interlobar sulci)', re.I)
NARIZ_LARINGE = re.compile(r'nasal|alar|septal|laryn|thyroid cartilage|cricoid|arytenoid|cuneiform cartilage|corniculate|epiglott|tracheal|auricular cartilage|cartilage of (ear|acoustic|external)|meatus', re.I)


def sistema(i):
    n = i['nome']; t = topo(i); mt = mat(i)
    if n.endswith(('.j', '.i', '.g', '.t', '.s')) or i['tipo'] not in (1, 2): return None
    if EXCLUI.match(base(n)) or re.search(r'-(curve|profile)\b|BezierCircle', n): return None
    if any(x in (3, 12, 57, 42) for x in i['mods']) and i['tipo'] == 1 and not re.match(r'Mucosa of stomach', n): return None
    if t.startswith('1:'):
        if mt == 'Cartilage' and NARIZ_LARINGE.search(n): return 'visceras'
        return 'esqueleto'
    if t.startswith('3:'): return 'articulacoes'
    if t.startswith('4:'):
        if mt in ('Ligament', 'Articular capsule', 'Cartilage', 'Bursa'): return 'articulacoes'
        if mt == 'Fascia' or re.search(r'fascia|aponeurosis|sheath|retinacul', n, re.I): return 'fascias'
        return 'musculos'
    if t.startswith('5:'):
        if i['tipo'] == 1: return 'coracao'
        if mt in ('Vein', 'Pulmonary vein') or re.search(r'\bvein|venous|sinus|vena\b', n, re.I): return 'veias'
        return 'arterias'
    if t.startswith('6:'): return 'linfatico'
    if t.startswith('7:'): return 'nervoso'
    if t.startswith('8:'): return 'visceras'
    if t.startswith('9:'): return 'pele'
    if n == 'Medulla-path': return 'nervoso'
    return None


# ---------- cores realistas (sRGB) ----------
def hx(s): return s
COR_MAT = {
    'Teeth': '#F3EFE4', 'Cartilage': '#CBD8DC', 'Ligament': '#D9D1BE', 'Articular capsule': '#D2C8B4', 'Fat': '#E9CF7A', 'Bursa': '#C7D7DF',
    'Tendon': '#E4DDCB', 'Fascia': '#DCD2C2', 'Artery': '#B8232A', 'Pulmonary artery': '#4462B3', 'Vein': '#2F4C9C', 'Pulmonary vein': '#B5363A',
    'Frontal lobe': '#E2BDB2', 'Parietal lobe': '#E2BDB2', 'Temporal lobe': '#E2BDB2', 'Occipital lobe': '#E2BDB2', 'Limbic lobe': '#DDB3A8',
    'Brain': '#E0B9AE', 'Brain-Inner': '#E9D4CC', 'Cerebellum': '#D7A99D', 'White matter': '#F1EAE2', 'Nucleus': '#C9A096',
    'Nucleus (efferent fibers)': '#C9A096', 'Nucleus (afferent fibers)': '#C9A096', 'LCR': '#9CCBE0', 'Eye': '#F4F2EC', 'Cornea': '#DCEEF3',
    'Iris': '#6E4B2E', 'Mucosa': '#D58A86', 'Gland': '#C98068', 'Bronchi': '#E6D3C2', 'Ductus': '#9DAA4E', 'Intestine': '#D79C88',
    'Lung-base': '#D9938E', 'Organ': '#B5584A', 'Peritoneum': '#EBD392', 'Gallbladder': '#4F7D3B', 'Mucosa of stomach': '#C77064',
    'Nail': '#E9CBC2', 'Black': '#3A2A20',
}
TRANSP = [(r'^cornea', '#D8ECF2', 0.22), (r'anterior chamber', '#D2E8F0', 0.10), (r'^lens', '#EDE3BE', 0.55), (r'vitreous', '#DCEAEE', 0.10),
          (r'suspensory ligament of eyeball', '#E6E0D2', 0.25)]
ORGAO = [  # por nome (vale mais que o material)
    (r'^liver|segment of liver', '#7A2B20'), (r'lung', '#D9938E'), (r'bronch', '#E6D3C2'), (r'trachea', '#E2D2C0'), (r'kidney', '#7B3026'),
    (r'renal pelvis|ureter', '#E2C6A6'), (r'spleen', '#6B2C3B'), (r'pancrea', '#E3B27C'), (r'stomach', '#D88878'), (r'duodenum|jejunum|ileum', '#D99B86'),
    (r'colon|caecum|cecum|appendix|rectum|taenia|mesocolon|meso-appendix', '#C99079'), (r'oesophag|esophag|pharynx', '#D18478'), (r'gallbladder', '#4F7D3B'),
    (r'bile|hepatic duct|cystic duct|choledoch|pancreatic duct', '#9DAA4E'), (r'thyroid gland|parathyroid', '#A6473B'), (r'suprarenal|adrenal', '#D8A23F'),
    (r'urinary bladder', '#D9A792'), (r'prostate|seminal', '#C98B77'), (r'testis|epididym', '#E5C8B6'), (r'penis|glans|corpus', '#C98276'),
    (r'tongue', '#C66B69'), (r'gingiva|palate|uvula', '#D9858A'), (r'parotid|submandibular|sublingual', '#D29A7A'), (r'hypophysis|pineal', '#C99A8E'),
    (r'atrium|ventricle$|ventricle of heart|^left ventricle|^right ventricle', '#9C3B33'), (r'papillary', '#9C3B33'), (r'leaflet|valve|cusp', '#E2C6B3'),
    (r'pulmonary trunk', '#4462B3'), (r'sinus|plexus', '#2F4C9C'), (r'thymus', '#D8B49B'), (r'tonsil', '#C9877C'),
    (r'retina', '#B4462F'), (r'^iris', '#5B3A22'), (r'sclera|eyeball', '#F1EDE4'), (r'lacrimal gland', '#D8A38C'), (r'lacrimal|nasolacrimal', '#D99A94'),
]


def cor(i, sis, rnd):
    n = base(i['nome']).lower(); mt = mat(i)
    if sis == 'esqueleto':
        if mt == 'Teeth' or re.search(r'tooth|incisor|canine|molar|premolar', n): return '#F3EFE4'
        if mt == 'Cartilage' or 'cartilage' in n: return '#CBD8DC'
        v = rnd.uniform(-0.035, 0.035); return var('#CDBFA0', v)
    if sis == 'musculos':
        if mt == 'Tendon' or re.search(r'tendon|aponeuros', n): return '#E4DDCB'
        return var('#80271F', rnd.uniform(-0.08, 0.07))
    if sis == 'nervoso':
        if i['tipo'] == 2 or 'nerve' in mt.lower() or re.search(r'nerve|ganglion|plexus|trunk|ramus|root', n): return '#EBD27F'
    if sis == 'pele':
        if mt in COR_MAT: return COR_MAT[mt]
        return var('#E1B497', rnd.uniform(-0.02, 0.02))
    if sis == 'linfatico':
        if i.get('sint'): return '#D9D08A'
        if 'spleen' in n: return '#6B2C3B'
        if 'thymus' in n: return '#D8B49B'
        if 'tonsil' in n: return '#C9877C'
        return '#B5B85C'
    for rx, c in ORGAO:
        if re.search(rx, n): return c
    if mt in COR_MAT: return COR_MAT[mt]
    base_m = re.sub(r'-\d+$', '', mt)
    if base_m in COR_MAT: return COR_MAT[base_m]
    if sis == 'arterias': return '#B8232A'
    if sis == 'veias': return '#2F4C9C'
    if sis == 'articulacoes': return '#D9D1BE'
    if sis == 'fascias': return '#DCD2C2'
    if sis == 'coracao': return '#9C3B33'
    if sis == 'nervoso': return '#E2BDB2'
    return '#C98A70'


def var(h, v):
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    f = lambda x: max(0, min(255, round(x * (1 + v))))
    return '#%02X%02X%02X' % (f(r), f(g), f(b))


# ---------- geometria ----------
def para_site(p):   # metros, Z para cima, frente em -Y  ->  mm, Y para cima, frente em +Z
    p = np.asarray(p, np.float64) * 1000.0
    return np.stack([p[:, 0], p[:, 2], -p[:, 1]], 1)


def tubo(pts, rad, lados):
    pts = np.asarray(pts, np.float64); rad = np.asarray(rad, np.float64)
    ok = np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-4]; pts = pts[ok]; rad = rad[ok]
    if len(pts) < 2: return None, None
    T = np.gradient(pts, axis=0); T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-12
    a = np.array([0, 0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0, 0])
    N = np.cross(T[0], a); N /= np.linalg.norm(N); Ns = [N]
    for k in range(1, len(pts)):
        n = Ns[-1] - np.dot(Ns[-1], T[k]) * T[k]; ln = np.linalg.norm(n)
        Ns.append(n / ln if ln > 1e-9 else Ns[-1])
    Ns = np.array(Ns); Bs = np.cross(T, Ns)
    ang = np.linspace(0, 2 * np.pi, lados, endpoint=False)
    V = (pts[:, None, :] + rad[:, None, None] * (np.cos(ang)[None, :, None] * Ns[:, None, :] + np.sin(ang)[None, :, None] * Bs[:, None, :])).reshape(-1, 3)
    F = []
    for k in range(len(pts) - 1):
        for j in range(lados):
            a0 = k * lados + j; a1 = k * lados + (j + 1) % lados; b0 = a0 + lados; b1 = a1 + lados
            F += [(a0, b0, a1), (a1, b0, b1)]
    # tampas (pontas fechadas)
    c0 = len(V); c1 = c0 + 1; V = np.vstack([V, pts[0], pts[-1]]); L = (len(pts) - 1) * lados
    for j in range(lados):
        F.append((c0, (j + 1) % lados, j)); F.append((c1, L + j, L + (j + 1) % lados))
    return V, np.array(F, np.int64)


def suavizar(V, F, niveis):
    if not niveis or len(F) > 60000: return V, F
    niveis = min(niveis, 2 if len(F) < 15000 else 1)
    try: return loop(V, F, niveis)
    except Exception as e: print('  subdivisão falhou', e); return V, F


def componentes(F, nv):
    pai = np.arange(nv)
    def raiz(x):
        while pai[x] != x: pai[x] = pai[pai[x]]; x = pai[x]
        return x
    for a, b, c in F:
        ra, rb, rc = raiz(a), raiz(b), raiz(c); pai[rb] = ra; pai[raiz(c)] = ra
    return np.array([raiz(x) for x in range(nv)])


def aumentar_nos(V, F, alvo=11.0):
    """os linfonodos vêm como esferas de 2,6 mm: cada um vira uma de ~8 mm (tamanho real), no mesmo lugar"""
    comp = componentes(F, len(V)); V = V.copy()
    for c in np.unique(comp):
        k = comp == c; ctr = V[k].mean(0); tam = (V[k].max(0) - V[k].min(0)).max()
        if 0 < tam < 6: V[k] = ctr + (V[k] - ctr) * (alvo / tam)
    return V


def geometria(i, sis):
    if i['tipo'] == 1:
        if not len(i.get('tris', [])): return None, None
        V, F = para_site(i['pos']), i['tris'].astype(np.int64)
        V, F = suavizar(V, F, i.get('subdiv', 0))
        if sis == 'linfatico' and re.search(r'node', i['nome'], re.I): V = aumentar_nos(V, F)
        return V, F
    Vs, Fs, off = [], [], 0
    esc = i.get('escala', 1.0) * (i.get('ext2') or 0.0005)
    for pts, rad in i.get('curvas', []):
        P = para_site(pts); r = np.asarray(rad, np.float64) * esc * 1000.0
        if sis == 'nervoso': r = np.maximum(r * 2.2, 0.55)
        elif i.get('sint'): pass
        else: r = np.maximum(r, 0.35)
        lados = 10 if r.max() > 4 else 8 if r.max() > 1.2 else 6
        V, F = tubo(P, r, lados)
        if V is None: continue
        Vs.append(V); Fs.append(F + off); off += len(V)
    if not Vs: return None, None
    return np.vstack(Vs), np.vstack(Fs)


def bfs(a, nvp):
    t = a.reshape(-1, 3); nt = len(t)
    flat = t.ravel(); tri = np.repeat(np.arange(nt), 3)
    o = np.argsort(flat, kind='stable'); st = np.searchsorted(flat[o], np.arange(nvp + 1))
    vt = tri[o].tolist(); st = st.tolist(); tl = t.tolist()
    seen = bytearray(nt); out = []; dq = collections.deque()
    for s0 in range(nt):
        if seen[s0]: continue
        seen[s0] = 1; dq.append(s0)
        while dq:
            x = dq.popleft(); out.append(x)
            for v in tl[x]:
                for y in vt[st[v]:st[v + 1]]:
                    if not seen[y]: seen[y] = 1; dq.append(y)
    return t[np.array(out)].ravel()


def planes16(x):
    b = np.frombuffer(x.astype(np.uint16).tobytes(), np.uint8).reshape(-1, 2)
    return b[:, 0].tobytes() + b[:, 1].tobytes()


MIN = np.array([-400., -60., -260.]); Q = 8.0


def gravar(nome, parts):
    """parts: [{id, n, p, c, V (mm), F}] -> nome.bin.gz"""
    hs = []; POS = []; COD = []
    for pa in parts:
        V, F = pa['V'], pa['F'].ravel()
        q = np.clip(np.round((V - MIN) * Q), 0, 65535).astype(np.int32)
        f = bfs(F, len(V))
        _, first = np.unique(f, return_index=True); order = np.unique(f)[np.argsort(first)]
        rem = np.full(len(V), -1, np.int64); rem[order] = np.arange(len(order)); a2 = rem[f]
        mm = np.maximum.accumulate(a2); prev = np.concatenate([[-1], mm[:-1]]); c = prev + 1 - a2
        if c.max() >= 65536: print('  pulei (índice)', pa['n']); continue
        POS.append(q[order]); COD.append(c)
        h = {k: pa[k] for k in ('id', 'n', 'p', 'c') if k in pa}; h['v'] = int(len(order)); h['f'] = int(len(f) // 3)
        for k in ('g', 'x', 't'):
            if k in pa: h[k] = pa[k]
        hs.append(h)
    pos = np.concatenate(POS); d = np.diff(pos, axis=0, prepend=np.zeros((1, 3), np.int32))
    assert d.min() >= -32768 and d.max() < 32768
    h = json.dumps({'versao': 3, 'min': MIN.tolist(), 'q': Q, 'parts': hs}, separators=(',', ':'), ensure_ascii=False).encode()
    h += b' ' * ((-len(h)) % 4)
    body = b'BP3D' + len(h).to_bytes(4, 'little') + h + planes16(d.T.copy().ravel()) + planes16(np.concatenate(COD))
    gz = gzip.compress(body, 9); open(os.path.join(OUT, nome + '.bin.gz'), 'wb').write(gz)
    return {'partes': len(hs), 'mb': round(len(gz) / 1048576, 1), 'f': sum(x['f'] for x in hs)}


# ---------- vasos linfáticos ----------
def frente_vertebra(nome):
    v = POR_NOME.get(nome)
    if not v or not len(v.get('pos', [])): return None
    P = v['pos'] * 1000; k = np.abs(P[:, 0] - P[:, 0].mean()) < 8
    Q = P[k] if k.sum() > 10 else P; j = np.argsort(Q[:, 1])[:12]
    return np.array([P[:, 0].mean(), Q[j, 1].mean(), Q[j, 2].mean()])


def linfaticos():
    out = []
    def curva(nome, pts, r):
        pts = np.array(pts, float) / 1000.0
        # suaviza a linha (Catmull-Rom simples)
        P = []
        for k in range(len(pts) - 1):
            p0 = pts[max(k - 1, 0)]; p1 = pts[k]; p2 = pts[k + 1]; p3 = pts[min(k + 2, len(pts) - 1)]
            for t in np.linspace(0, 1, 8, endpoint=False):
                t2, t3 = t * t, t * t * t
                P.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
        P.append(pts[-1]); P = np.array(P)
        out.append({'nome': nome, 'tipo': 2, 'pai': None, 'cols': [['6: Lymphoid organs']], 'mods': [], 'mat': ('Lymph vessel',),
                    'curvas': [(P.astype(np.float32), np.full(len(P), 1.0, np.float32))], 'ext2': r / 1000.0, 'escala': 1.0, 'sint': 1})
    vs = {}
    for n in ['L2', 'L1', 'T12', 'T11', 'T10', 'T9', 'T8', 'T7', 'T6', 'T5', 'T4', 'T3', 'T2', 'T1']:
        p = frente_vertebra('Vertebra ' + n)
        if p is not None: vs[n] = p
    if len(vs) < 10: print('  sem vértebras para os linfáticos'); return out
    def em(n, dx, dy=-3.0, dz=0.0): p = vs[n]; return [dx, p[1] + dy, p[2] + dz]
    angE = [30.0, -15.0, 1412.0]; angD = [-30.0, -15.0, 1412.0]
    curva('Cisterna chyli', [em('L2', -7, -4, 5), em('L1', -7, -4), em('T12', -7, -4, -10)], 6.0)
    curva('Thoracic duct', [em('T12', -7, -4, -10), em('T11', -7), em('T10', -6), em('T9', -6), em('T8', -5), em('T7', -4), em('T6', -2),
                            em('T5', 2), em('T4', 6), em('T3', 9), em('T2', 12), em('T1', 15, -4), [22, -2, 1448], [29, -10, 1430], angE], 2.6)
    curva('Right lymphatic duct', [[-20, -6, 1432], [-26, -11, 1422], angD], 2.2)
    for ld, sx, ang in (('l', 1, angE), ('r', -1, angD)):
        curva(f'Jugular trunk.{ld}', [[sx * 33, -10, 1475], [sx * 32, -13, 1445], ang], 1.6)
        curva(f'Subclavian trunk.{ld}', [[sx * 72, -9, 1408], [sx * 50, -12, 1410], ang], 1.6)
        curva(f'Lumbar trunk.{ld}', [[sx * 20, -24, 995], [sx * 12, -22, 1030], em('L2', -7 + sx * 4, -4, 5)], 1.6)
        curva(f'Bronchomediastinal trunk.{ld}', [[sx * 22, -30, 1340], [sx * 26, -20, 1390], ang], 0.9)
    curva('Intestinal trunk', [[-2, -55, 1085], [-5, -30, 1088], em('L1', -7, -4)], 1.6)
    return out


EN2PT.update({'cisterna chyli': 'Cisterna do quilo', 'thoracic duct': 'Ducto torácico', 'right lymphatic duct': 'Ducto linfático direito',
              'jugular trunk': 'Tronco jugular', 'subclavian trunk': 'Tronco subclávio', 'lumbar trunk': 'Tronco lombar',
              'bronchomediastinal trunk': 'Tronco broncomediastinal', 'intestinal trunk': 'Tronco intestinal'})
I += linfaticos()

# ---------- montar ----------
rnd = random.Random(7)
SIST = collections.defaultdict(list)
todos_min = []
for i in I:
    s = sistema(i)
    if not s: continue
    V, F = geometria(i, s)
    if V is None or not len(F): continue
    nb = base(i['nome']); ld = lado(i['nome'])
    if i['nome'] == 'Medulla-path': nb = 'Spinal cord'
    ptn = com_lado(pt(nb), ld)
    pa = {'id': i['nome'], 'n': nb + ({'r': ' (right)', 'l': ' (left)'}.get(ld, '')), 'p': ptn, 'c': cor(i, s, rnd), 'V': V, 'F': F}
    for rx, c, t in TRANSP:
        if re.search(rx, nb, re.I): pa['c'] = c; pa['t'] = t
    SIST[s].append(pa)
    todos_min.append(V.min(0)); todos_min.append(V.max(0))
mm = np.array(todos_min); print('limites (mm)', mm.min(0).round(), mm.max(0).round())
resumo = {}
for s, parts in SIST.items():
    parts.sort(key=lambda x: (x['p'].lower(), x['id']))
    resumo[s] = gravar(s, parts); print(s, resumo[s], flush=True)

# busca
nomes = []
for s, parts in SIST.items():
    vistos = set()
    for pa in parts:
        if pa['id'] in vistos: continue
        vistos.add(pa['id']); nomes.append({'i': pa['id'], 'n': pa['n'], 'p': pa['p'], 's': s})

# ---------- acidentes ----------
estr = {pa['id']: s for s, parts in SIST.items() for pa in parts}
ACI = collections.defaultdict(lambda: {'pontos': [], 'areas': [], 'fix': []})
AREAS = []; FIXS = []
for i in I:
    n = i['nome']
    if i['tipo'] == 4 and n.endswith(('.t', '.s')) and i.get('pai') in estr:
        loc = para_site(i['loc'][None, :])[0]; p = loc
        js = [j for j in filhos.get(n, []) if j['nome'].endswith(('.j', '.i')) and len(j.get('pos', []))]
        anc = [a for j in js for a in j.get('ancoras', [])]
        if anc:      # a ponta presa (gancho) ao osso; de preferência a do próprio osso
            a = next((a for a in anc if a[0] == i['pai']), anc[0]); p = para_site(a[1])[0]
        elif js:
            V = para_site(js[0]['pos']); d = np.linalg.norm(V - loc, axis=1); p = V[np.argmax(d)]
        dono = POR_NOME.get(i['pai'])
        if dono is not None and len(dono.get('pos', [])) and np.linalg.norm(para_site(dono['pos']) - p, axis=1).min() > 40: continue
        nb = base(n); ACI[i['pai']]['pontos'].append({'n': nb, 'p': pt(nb), 'x': [round(float(v), 1) for v in p], **({'s': 1} if n.endswith('.s') else {})})
    elif False:
        ms = [j for j in filhos.get(n, []) if j['nome'].endswith('.i') and len(j.get('tris', []))]
        if not ms: continue
        nb = base(n); aid = 'A%d' % len(AREAS)
        AREAS.append({'id': aid, 'n': nb, 'p': pt(nb), 'c': '#2563EB', 'V': para_site(ms[0]['pos']), 'F': ms[0]['tris'].astype(np.int64)})
        ACI[i['pai']]['areas'].append({'n': nb, 'p': pt(nb), 'a': aid})
    elif i['tipo'] == 1 and topo(i).startswith('2:') and i.get('pai') and len(i.get('tris', [])):
        m = re.search(r'\.(o|e)(\d*)([lr])$', n)
        if not m: continue
        FIXS.append(i)
# origens e inserções: o lado vem da posição (o arquivo tem nomes trocados); o que só existe de um lado é espelhado
def osso_lado(osso, ld):
    if osso.endswith(('.r', '.l')): return osso[:-2] + '.' + ld
    return osso
def alvos_musculo(musc, ld):
    mid = musc + '.' + ld
    if mid in estr: return [mid]
    alt = [k for k in estr if base(k) == base(musc) and lado(k) == ld]
    if alt: return alt
    g = base(musc) + '.g'          # músculo inteiro: vale para as cabeças/partes dele
    return [k for k in estr if POR_NOME.get(k, {}).get('pai') == g and lado(k) == ld]
vistos = {}
for i in FIXS:
    m = re.search(r'\.(o|e)(\d*)([lr])$', i['nome']); tipo = 'o' if m.group(1) == 'o' else 'e'
    musc = re.sub(r'^\((.*)\)$', r'\1', SUF.sub('', i['nome']).strip())
    V = para_site(i['pos']); ld = 'l' if V[:, 0].mean() > 0 else 'r'
    Vs, Fs = suavizar(V, i['tris'].astype(np.int64), i.get('subdiv', 0))
    vistos[(musc, tipo, m.group(2), ld)] = (i['pai'], Vs, Fs)
for (musc, tipo, num, ld), (osso, V, F) in list(vistos.items()):
    outro = 'r' if ld == 'l' else 'l'
    if (musc, tipo, num, outro) not in vistos:
        V2 = V.copy(); V2[:, 0] *= -1; vistos[(musc, tipo, num, outro)] = (osso, V2, F[:, ::-1].copy())
for (musc, tipo, num, ld), (osso, V, F) in vistos.items():
    osso = osso_lado(osso, ld)
    if osso not in estr: continue
    aid = 'F%d' % len(AREAS)
    AREAS.append({'id': aid, 'n': musc, 'p': pt(musc), 'c': '#C2410C' if tipo == 'o' else '#7C3AED', 'V': V, 'F': F})
    nome_osso = next((pa['p'] for pa in SIST[estr[osso]] if pa['id'] == osso), osso)
    for mid in alvos_musculo(musc, ld):
        ACI[osso]['fix'].append({'m': mid, 'p': com_lado(pt(base(musc)), ld), 't': tipo, 'a': aid})
        ACI[mid]['fix'].append({'m': osso, 'p': nome_osso, 't': tipo, 'a': aid, 'osso': 1})
# sem repetição no osso (o mesmo músculo pode valer para várias partes)
for k, v in ACI.items():
    u = {}; [u.setdefault((f['a'], f.get('osso', 0)), f) for f in v['fix']]; v['fix'] = list(u.values())
print('acidentes', sum(len(v['pontos']) for v in ACI.values()), 'pontos,', sum(len(v['areas']) for v in ACI.values()), 'áreas,',
      sum(len(v['fix']) for v in ACI.values()), 'fixações', len(AREAS), 'malhas')
resumo['acidentes'] = gravar('acidentes', AREAS); print('acidentes', resumo['acidentes'])
json.dump({k: v for k, v in ACI.items()}, open(os.path.join(OUT, 'acidentes.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
json.dump(nomes, open(os.path.join(OUT, 'nomes.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
json.dump(resumo, open(os.path.join(OUT, '..', 'resumo-anatomia.json'), 'w'), ensure_ascii=False, indent=1)
