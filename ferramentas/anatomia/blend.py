# Leitor mínimo de arquivos .blend (64 bits, little-endian, sem compressão): SDNA, blocos, structs.
import struct, sys, re, mmap


class Blend:
    def __init__(self, path):
        self.f = open(path, 'rb'); self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        h = self.m[:12]; assert h[:7] == b'BLENDER' and h[7:8] == b'-' and h[8:9] == b'v', h
        self.blocks = []; self.por_end = {}; self.local = None
        o = 12
        while o < len(self.m):
            code = self.m[o:o + 4]; size, old, sdna, count = struct.unpack_from('<iQii', self.m, o + 4)
            b = (code.rstrip(b'\0').decode('latin1'), o + 24, size, old, sdna, count)
            self.blocks.append(b)
            if old and (code[:2] != b'DA' or old not in self.por_end): self.por_end[old] = b
            self.idx_de_end = None
            o += 24 + size
            if code == b'ENDB': break
        self.sdna()

    def sdna(self):
        b = [x for x in self.blocks if x[0] == 'DNA1'][0]; m = self.m; o = b[1]
        assert m[o:o + 4] == b'SDNA'; o += 4
        b0 = o
        def al(o): return b0 + ((o - b0 + 3) & ~3)
        assert m[o:o + 4] == b'NAME'; o += 4; n = struct.unpack_from('<i', m, o)[0]; o += 4
        names = []
        for _ in range(n): e = m.find(b'\0', o); names.append(m[o:e].decode()); o = e + 1
        o = al(o); assert m[o:o + 4] == b'TYPE'; o += 4; n = struct.unpack_from('<i', m, o)[0]; o += 4
        types = []
        for _ in range(n): e = m.find(b'\0', o); types.append(m[o:e].decode()); o = e + 1
        o = al(o); assert m[o:o + 4] == b'TLEN'; o += 4
        tlen = list(struct.unpack_from('<%dh' % len(types), m, o)); o += 2 * len(types)
        o = al(o); assert m[o:o + 4] == b'STRC'; o += 4; n = struct.unpack_from('<i', m, o)[0]; o += 4
        self.structs = []; self.st_por_nome = {}
        for i in range(n):
            t, nf = struct.unpack_from('<hh', m, o); o += 4
            campos = []; off = 0
            for _ in range(nf):
                ft, fn = struct.unpack_from('<hh', m, o); o += 4
                nome = names[fn]; tam = self.tam_campo(nome, tlen[ft])
                campos.append((nome, types[ft], off, tam)); off += tam
            self.structs.append((types[t], campos, tlen[t]))
            self.st_por_nome[types[t]] = i
        self.types = types; self.tlen = tlen

    @staticmethod
    def tam_campo(nome, tl):
        n = 1
        for k in re.findall(r'\[(\d+)\]', nome): n *= int(k)
        if nome.startswith('*') or nome.startswith('(*'): return 8 * n
        return tl * n

    def campos(self, tipo):
        return {re.sub(r'[\*\[].*|\(\*|\)\(.*', '', c[0].lstrip('*')).split('[')[0]: c for c in self.structs[self.st_por_nome[tipo]][1]}

    def ler(self, tipo, base, campo, sub=None):
        """valor de um campo de um struct que começa no deslocamento base"""
        c = self.campos(tipo)[campo]; nome, t, off, tam = c; o = base + off
        if nome.startswith('*'): return struct.unpack_from('<Q', self.m, o)[0]
        if t == 'char': return self.m[o:o + tam].split(b'\0')[0].decode('utf8', 'replace')
        fmt = {'int': 'i', 'float': 'f', 'short': 'h', 'double': 'd', 'uint': 'I', 'int64_t': 'q', 'uint64_t': 'Q', 'int8_t': 'b', 'uchar': 'B', 'ushort': 'H'}.get(t)
        if fmt is None: return o          # struct embutido: devolve o deslocamento
        n = tam // struct.calcsize(fmt)
        v = struct.unpack_from('<%d%s' % (n, fmt), self.m, o)
        return v[0] if n == 1 else v

    def contexto(self, bloco_id):
        """os blocos DATA que vêm logo depois de um bloco de ID (é assim que o Blender acha os dados dele)"""
        if not hasattr(self, '_pos'): self._pos = {b[1]: i for i, b in enumerate(self.blocks)}
        i = self._pos[bloco_id[1]] + 1; loc = {}
        while i < len(self.blocks) and self.blocks[i][0] == 'DATA':
            b = self.blocks[i]; loc.setdefault(b[3], b); i += 1
        self.local = loc

    def bloco(self, ptr):
        if self.local is not None and ptr in self.local: return self.local[ptr]
        return self.por_end.get(ptr)
