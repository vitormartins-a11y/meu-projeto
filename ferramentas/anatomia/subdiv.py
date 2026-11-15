# Subdivisão de Loop (triângulos), com bordas tratadas: deixa liso o que no Blender é suavizado pelo modificador Subdivision.
import numpy as np


def loop(V, F, niveis=1):
    V = np.asarray(V, np.float64); F = np.asarray(F, np.int64)
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    F = np.unique(F, axis=0) if len(F) else F
    V0, F0 = V, F
    for _ in range(niveis):
        nv = len(V)
        E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
        opos = np.concatenate([F[:, 2], F[:, 0], F[:, 1]])
        chave = E[:, 0] * nv + E[:, 1]
        u, inv, cont = np.unique(chave, return_inverse=True, return_counts=True)
        ue = np.stack([u // nv, u % nv], 1); ne = len(ue)
        borda = cont[np.arange(ne)] == 1; ruim = cont[np.arange(ne)] > 2
        # vértice novo em cada aresta
        soma_op = np.zeros((ne, 3)); np.add.at(soma_op, inv, V[opos])
        Ve = np.where((borda | ruim)[:, None], (V[ue[:, 0]] + V[ue[:, 1]]) / 2, 3 / 8 * (V[ue[:, 0]] + V[ue[:, 1]]) + 1 / 8 * soma_op)
        # vértices antigos
        viz = np.zeros((nv, 3)); val = np.zeros(nv)
        np.add.at(viz, ue[:, 0], V[ue[:, 1]]); np.add.at(viz, ue[:, 1], V[ue[:, 0]]); np.add.at(val, ue[:, 0], 1); np.add.at(val, ue[:, 1], 1)
        vb = np.zeros(nv, bool); vb[ue[borda].ravel()] = True
        vizb = np.zeros((nv, 3)); np.add.at(vizb, ue[borda][:, 0], V[ue[borda][:, 1]]); np.add.at(vizb, ue[borda][:, 1], V[ue[borda][:, 0]])
        n = np.maximum(val, 1); beta = np.where(n > 3, 3 / (8 * n), 3 / 16)
        Vn = np.where(vb[:, None], 0.75 * V + 0.125 * vizb, (1 - n * beta)[:, None] * V + beta[:, None] * viz)
        Vn[val == 0] = V[val == 0]
        fixo = np.zeros(nv, bool); fixo[ue[ruim].ravel()] = True; Vn[fixo] = V[fixo]
        ei = inv.reshape(3, -1).T + nv          # arestas (01, 12, 20) de cada triângulo
        a, b, c = F[:, 0], F[:, 1], F[:, 2]; ab, bc, ca = ei[:, 0], ei[:, 1], ei[:, 2]
        F = np.concatenate([np.stack([a, ab, ca], 1), np.stack([ab, b, bc], 1), np.stack([ca, bc, c], 1), np.stack([ab, bc, ca], 1)])
        V = np.vstack([Vn, Ve])
    # segurança: se algo escapou da caixa original, fica a malha sem suavizar
    mn, mx = V0.min(0), V0.max(0); folga = (mx - mn).max() * 0.05 + 0.5
    if (V.min(0) < mn - folga).any() or (V.max(0) > mx + folga).any(): return V0, F0
    return V, F
