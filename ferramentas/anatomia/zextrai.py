# Extrai do Startup.blend do Z-Anatomy: malhas (triângulos, no mundo), curvas (pontos + raio), rótulos e linhas
# indicadoras, com o caminho de coleções e a cor do material. Grava um pickle para a conversão.
import sys, struct, collections, pickle, math
import numpy as np
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blend import Blend
B = Blend(sys.argv[1]); OUT = sys.argv[2]
m = B.m


def lst(base):
    p = struct.unpack_from('<Q', m, base)[0]; out = []
    while p:
        b = B.bloco(p)
        if not b: break
        out.append(b); p = struct.unpack_from('<Q', m, b[1])[0]
    return out


def lst_ptr(base, tipo, campo):
    return [B.ler(tipo, b[1], campo) for b in lst(base)]


def nome_id(o, tipo):
    return B.ler('ID', B.ler(tipo, o, 'id'), 'name')[2:]


# coleções: caminho de cada objeto
cols = {}
for b in B.blocks:
    if b[0] == 'GR':
        o = b[1]
        cols[b[3]] = (nome_id(o, 'Collection'), lst_ptr(B.ler('Collection', o, 'gobject'), 'CollectionObject', 'ob'),
                      lst_ptr(B.ler('Collection', o, 'children'), 'CollectionChild', 'collection'))
pai_col = {}
for k, (n, obs, fs) in cols.items():
    for f in fs: pai_col.setdefault(f, k)
def caminho(c):
    out = []
    while c in cols and len(out) < 12: out.append(cols[c][0]); c = pai_col.get(c)
    return out[::-1]
col_de_ob = {}
for k, (n, obs, fs) in cols.items():
    for o in obs: col_de_ob.setdefault(o, []).append(caminho(k))

# materiais
def cor_mat(p):
    b = B.bloco(p)
    if not b or b[0] != 'MA': return None
    o = b[1]; return (nome_id(o, 'Material'), B.ler('Material', o, 'r'), B.ler('Material', o, 'g'), B.ler('Material', o, 'b'), B.ler('Material', o, 'a'))
def mat_de(ob_o, data_o, tipo_data):
    for (base, tipo, tot_campo) in ((ob_o, 'Object', 'totcol'), (data_o, tipo_data, 'totcol')):
        pp = B.ler(tipo, base, 'mat'); n = B.ler(tipo, base, tot_campo)
        if pp and n:
            pb = B.bloco(pp)
            if pb:
                for i in range(n):
                    c = cor_mat(struct.unpack_from('<Q', m, pb[1] + 8 * i)[0])
                    if c: return c
    return None


def cdlayers(cd):
    lp = B.ler('CustomData', cd, 'layers'); n = B.ler('CustomData', cd, 'totlayer'); lb = B.bloco(lp); out = []
    if not lb: return out
    for i in range(n):
        lo = lb[1] + i * 120
        out.append((B.ler('CustomDataLayer', lo, 'type'), B.ler('CustomDataLayer', lo, 'name'), B.ler('CustomDataLayer', lo, 'data')))
    return out


def arr(ptr, dtype, n, stride=None):
    b = B.bloco(ptr)
    if not b: return None
    if stride is None: return np.frombuffer(m, dtype=dtype, count=n, offset=b[1]).copy()
    raw = np.frombuffer(m, dtype=np.uint8, count=n * stride, offset=b[1]).reshape(n, stride)
    return raw


def malha(me):
    o = me[1]
    nv = B.ler('Mesh', o, 'totvert'); np_ = B.ler('Mesh', o, 'totpoly'); nl = B.ler('Mesh', o, 'totloop'); ne = B.ler('Mesh', o, 'totedge')
    pos = None
    for t, nome, d in cdlayers(B.ler('Mesh', o, 'vdata')):
        if t == 0 and d: pos = arr(d, None, nv, 16)[:, :12].copy().view(np.float32).reshape(nv, 3)
        elif nome == 'position' and d: pos = arr(d, np.float32, nv * 3).reshape(nv, 3)
    if pos is None:
        mv = B.ler('Mesh', o, 'mvert')
        if mv: pos = arr(mv, None, nv, 16)[:, :12].copy().view(np.float32).reshape(nv, 3)
    if pos is None: return None, None, None
    tris = np.zeros((0, 3), np.int64)
    mp = B.ler('Mesh', o, 'mpoly'); ml = B.ler('Mesh', o, 'mloop')
    if mp and ml and np_:
        P = arr(mp, None, np_, 12)[:, :8].copy().view(np.int32).reshape(np_, 2)
        L = arr(ml, None, nl, 8)[:, :4].copy().view(np.int32).reshape(nl)
        ts = []
        tot = P[:, 1]
        for k in np.unique(tot):
            sel = P[tot == k]
            if k < 3: continue
            base = sel[:, 0]
            for j in range(1, k - 1):
                ts.append(np.stack([L[base], L[base + j], L[base + j + 1]], 1))
        if ts: tris = np.concatenate(ts)
    edges = None
    if ne:
        for t, nome, d in cdlayers(B.ler('Mesh', o, 'edata')):
            if t == 3 and d: edges = arr(d, None, ne, 12)[:, :8].copy().view(np.int32).reshape(ne, 2)   # MEdge v1,v2
        if edges is None and B.ler('Mesh', o, 'medge'):
            edges = arr(B.ler('Mesh', o, 'medge'), None, ne, 12)[:, :8].copy().view(np.int32).reshape(ne, 2)
    return pos, tris, edges


def bez_pts(nu_o, n, ciclico, res):
    bz = B.bloco(B.ler('Nurb', nu_o, 'bezt'))
    if not bz: return None
    raw = np.frombuffer(m, dtype=np.uint8, count=n * 72, offset=bz[1]).reshape(n, 72)
    v = raw[:, :36].copy().view(np.float32).reshape(n, 3, 3); rad = raw[:, 44:48].copy().view(np.float32).reshape(n)
    seg = list(range(n - 1)) + ([n - 1] if ciclico else [])
    pts = []; rr = []
    for i in seg:
        j = (i + 1) % n; p0, p1, p2, p3 = v[i, 1], v[i, 2], v[j, 0], v[j, 1]
        for s in range(res):
            t = s / res; a = (1 - t) ** 3; b_ = 3 * (1 - t) ** 2 * t; c = 3 * (1 - t) * t * t; d = t ** 3
            pts.append(a * p0 + b_ * p1 + c * p2 + d * p3); rr.append(rad[i] * (1 - t) + rad[j] * t)
    if not ciclico: pts.append(v[n - 1, 1]); rr.append(rad[n - 1])
    return np.array(pts, np.float64), np.array(rr, np.float64)


def poly_pts(nu_o, n):
    bp = B.bloco(B.ler('Nurb', nu_o, 'bp'))
    if not bp: return None
    raw = np.frombuffer(m, dtype=np.uint8, count=n * 36, offset=bp[1]).reshape(n, 36)
    v = raw[:, :12].copy().view(np.float32).reshape(n, 3); rad = raw[:, 28:32].copy().view(np.float32).reshape(n)
    return v.astype(np.float64), rad.astype(np.float64)


def curva(cu_o):
    out = []
    for nb in lst(B.ler('Curve', cu_o, 'nurb')):
        o = nb[1]; t = B.ler('Nurb', o, 'type'); n = B.ler('Nurb', o, 'pntsu'); res = max(2, min(12, B.ler('Nurb', o, 'resolu') or 4))
        cic = bool(B.ler('Nurb', o, 'flagu') & 1)
        if n < 1: continue
        r = bez_pts(o, n, cic, min(res, 6)) if t == 1 else poly_pts(o, n)
        if r is not None: out.append(r)
    return out


itens = []
MODS = {}
for b in B.blocks:
    if b[0] != 'OB': continue
    o = b[1]; nome = nome_id(o, 'Object'); tipo = B.ler('Object', o, 'type')
    B.local = None; db = B.bloco(B.ler('Object', o, 'data'))
    W = np.array(B.ler('Object', o, 'obmat'), np.float64).reshape(4, 4).T     # Blender guarda por colunas
    par = B.bloco(B.ler('Object', o, 'parent')); par_nome = nome_id(par[1], 'Object') if par else None
    B.contexto(b); mods = [(B.ler('ModifierData', mb[1], 'type'), mb) for mb in lst(B.ler('Object', o, 'modifiers'))]
    mods_flag = {}
    for t, mb in mods:
        if t == 5: mods_flag[5] = struct.unpack_from('<h', m, mb[1] + 120)[0] if False else None
    if db: B.contexto(db)
    it = dict(nome=nome, tipo=tipo, pai=par_nome, cols=col_de_ob.get(b[3], []), W=W, mods=[t for t, _ in mods])
    it['subdiv'] = max([B.ler('SubsurfModifierData', mb[1], 'levels') for t, mb in mods if t == 1] or [0])
    if tipo == 1 and db and db[0] == 'ME':
        pos, tris, edges = malha(db); B.contexto(b)
        if pos is None: continue
        it['mat'] = mat_de(o, db[1], 'Mesh')
        # espelho (modificador Mirror): no espaço do próprio objeto ou do objeto de espelho
        P = (np.c_[pos, np.ones(len(pos))] @ W.T)[:, :3]
        # ganchos (Hook): o vértice preso segue o objeto do gancho: mundo = gancho.obmat @ parentinv @ local
        ancoras = []
        for t, mb in mods:
            if t != 9 or not nome.endswith(('.j', '.i')): continue
            hob = B.bloco(B.ler('HookModifierData', mb[1], 'object')); ib = B.bloco(B.ler('HookModifierData', mb[1], 'indexar'))
            tot = B.ler('HookModifierData', mb[1], 'totindex'); forca = B.ler('HookModifierData', mb[1], 'force')
            if not hob or hob[0] != 'OB' or not ib or not tot: continue
            idx = np.frombuffer(m, np.int32, tot, ib[1]).copy(); idx = idx[(idx >= 0) & (idx < len(pos))]
            Hm = np.array(B.ler('Object', hob[1], 'obmat'), np.float64).reshape(4, 4).T
            Pi = np.array(B.ler('HookModifierData', mb[1], 'parentinv'), np.float64).reshape(4, 4).T
            novo = (np.c_[pos[idx], np.ones(len(idx))] @ (Hm @ Pi).T)[:, :3]
            P[idx] = P[idx] * (1 - forca) + novo * forca
            ancoras.append((nome_id(hob[1], 'Object'), P[idx].astype(np.float32)))
        it['ancoras'] = ancoras
        for t, mb in mods:
            if t != 5: continue
            fl = B.ler('MirrorModifierData', mb[1], 'flag'); mob = B.bloco(B.ler('MirrorModifierData', mb[1], 'mirror_ob'))
            M = np.array(B.ler('Object', mob[1], 'obmat'), np.float64).reshape(4, 4).T if mob and mob[0] == 'OB' else W
            Mi = np.linalg.inv(M)
            for ax in [i for i, bit in enumerate((8, 16, 32)) if fl & bit] or [0]:
                loc = (np.c_[P, np.ones(len(P))] @ Mi.T)[:, :3]; loc[:, ax] *= -1
                P2 = (np.c_[loc, np.ones(len(loc))] @ M.T)[:, :3]
                if len(tris): tris = np.concatenate([tris, tris[:, ::-1] + len(P)])
                if edges is not None: edges = np.concatenate([edges, edges + len(P)])
                P = np.concatenate([P, P2])
        W = np.eye(4)
        it['pos'] = P[:, :3].astype(np.float32); it['tris'] = tris.astype(np.int32); it['edges'] = edges
    elif tipo == 2 and db and db[0] == 'CU':
        c = db[1]
        it['ext2'] = B.ler('Curve', c, 'ext2'); it['ext1'] = B.ler('Curve', c, 'ext1'); it['bevobj'] = bool(B.ler('Curve', c, 'bevobj'))
        it['bevel_mode'] = B.ler('Curve', c, 'bevel_mode'); it['taper'] = bool(B.ler('Curve', c, 'taperobj'))
        it['mat'] = mat_de(o, c, 'Curve')
        cs = []
        for pts, rad in curva(c):
            P = np.c_[pts, np.ones(len(pts))] @ W.T; cs.append((P[:, :3].astype(np.float32), rad.astype(np.float32)))
        it['curvas'] = cs
        it['escala'] = float(np.cbrt(abs(np.linalg.det(W[:3, :3]))))
    elif tipo == 4 and db and db[0] == 'CU':
        c = db[1]; sp = B.ler('Curve', c, 'str'); sb = B.bloco(sp)
        it['texto'] = m[sb[1]:sb[1] + sb[2]].split(b'\0')[0].decode('utf8', 'replace') if sb else ''
        it['loc'] = W[:3, 3].astype(np.float32)
    itens.append(it)
pickle.dump(itens, open(OUT, 'wb'))
print(len(itens), collections.Counter(i['tipo'] for i in itens))
