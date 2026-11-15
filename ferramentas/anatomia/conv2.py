import json, sys, re, gzip, os, numpy as np, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from traduz import traduz
B = sys.argv[1]; OUT = sys.argv[2]
A = json.load(open(B + '/../isa_anc2.json')); S = json.load(open(B + '/../sist.json')); D = B + '/isa_BP3D_4.0_obj_99/'
MIN = np.array([-340., -80., -50.]); Q = 8.0


def veia(n): return bool(re.search(r'\bvein|venous|vena|\bveins|sinus|tributary|portal', n, re.I)) and not re.search(r'arter', n, re.I)


def ler(k):
    vs = []; fs = []
    for l in open(D + k + '.obj'):
        if l[:2] == 'v ': vs.append(l.split()[1:4])
        elif l[:2] == 'f ': fs.append([int(x.split('/')[0]) - 1 for x in l.split()[1:4]])
    return np.array(vs, dtype=np.float64), np.array(fs, dtype=np.int64).ravel()


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


def planes16(x):  # 16 bits -> plano dos bytes baixos + plano dos altos (comprime melhor)
    b = np.frombuffer(x.astype(np.uint16).tobytes(), np.uint8).reshape(-1, 2)
    return b[:, 0].tobytes() + b[:, 1].tobytes()


ARQ = collections.OrderedDict((k, []) for k in ['esqueleto', 'musculos', 'arterias', 'veias', 'nervoso', 'orgaos', 'pele'])
for k, t in S.items():
    n = A[k][1] or ''
    if t == 'cardiovascular': t = 'veias' if veia(n) else 'arterias'
    ARQ[t].append(k)
resumo = {}
for t, ks in ARQ.items():
    ks.sort(key=lambda k: (traduz(A[k][1] or ''), k))
    parts = []; POS = []; COD = []
    for k in ks:
        v, f = ler(k)
        if not len(f): continue
        p = np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1)          # z para cima -> y para cima; frente para +z
        q = np.clip(np.round((p - MIN) * Q), 0, 65535).astype(np.int32)
        f = bfs(f, len(v))
        _, first = np.unique(f, return_index=True); order = np.unique(f)[np.argsort(first)]
        rem = np.full(len(v), -1, np.int64); rem[order] = np.arange(len(order)); a2 = rem[f]
        m = np.maximum.accumulate(a2); prev = np.concatenate([[-1], m[:-1]]); c = prev + 1 - a2
        assert c.min() >= 0 and c.max() < 65536, (k, c.max())
        POS.append(q[order]); COD.append(c)
        parts.append({'id': k, 'n': A[k][1] or '', 'p': traduz(A[k][1] or ''), 'v': int(len(order)), 'f': int(len(f) // 3)})
    pos = np.concatenate(POS); d = np.diff(pos, axis=0, prepend=np.zeros((1, 3), np.int32))
    assert d.min() >= -32768 and d.max() < 32768
    h = json.dumps({'versao': 2, 'min': MIN.tolist(), 'q': Q, 'parts': parts}, separators=(',', ':'), ensure_ascii=False).encode()
    h += b' ' * ((-len(h)) % 4)
    body = b'BP3D' + len(h).to_bytes(4, 'little') + h + planes16(d.T.copy().ravel()) + planes16(np.concatenate(COD))
    gz = gzip.compress(body, 9)
    open(OUT + '/' + t + '.bin.gz', 'wb').write(gz)
    resumo[t] = {'partes': len(parts), 'mb': round(len(gz) / 1048576, 1), 'v': int(len(pos)), 'f': sum(p['f'] for p in parts)}
    print(t, resumo[t], flush=True)
json.dump(resumo, open(OUT + '/resumo.json', 'w'))
