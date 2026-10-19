"""
Leitor nativo do robô: lê PDFs e imagens com o PyMuPDF (e o Tesseract para as páginas escaneadas), bem mais rápido
que dentro do navegador, e usando todos os núcleos do computador (cada página vai para um processo).

Faz exatamente o que o site faz no navegador (mesmas regras): texto de cada página com o tamanho das letras (para o
título e os destaques), as figuras (com os mesmos filtros de tamanho e a junção de pedaços), a foto da página quando o
texto não basta, e o OCR das páginas escaneadas. O site recebe esse resultado e continua igual a antes (filtros de
logotipo e propaganda, marcadores das figuras, envio das imagens com a conferência de conteúdo).

Não tem efeito ao ser importado (os processos de trabalho importam este arquivo).
"""
import base64
import io
import math
import os
import shutil
import subprocess

PASTA = os.path.dirname(os.path.abspath(__file__))
TESSDATA = os.path.join(PASTA, "tessdata")              # o instalador baixa aqui o português (por.traineddata)
ESCALA_MAX, LARGURA = 2.2, 1400                          # iguais ao site (página desenhada com até 1400 px)


def _tesseract():
    """Tesseract instalado no computador (mais rápido); sem ele, o OCR embutido no PyMuPDF."""
    for c in (os.environ.get("TESSERACT"), shutil.which("tesseract"),
              os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tesseract-OCR", "tesseract.exe"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe")):
        if c and os.path.isfile(c):
            return c
    return None


def recursos():
    """O que este computador consegue fazer: ler PDF (PyMuPDF) e com qual OCR."""
    try:
        import pymupdf  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return {"ok": False}
    tem_por = os.path.isfile(os.path.join(TESSDATA, "por.traineddata"))
    tess = _tesseract()
    ocr = "tesseract" if tess and (tem_por or _tess_tem_por(tess)) else "embutido" if tem_por else None
    forcar = os.environ.get("LEITOR_OCR", "").strip().lower()      # para testes: "embutido" ou "navegador"
    if forcar == "embutido" and tem_por:
        ocr = "embutido"
    elif forcar == "navegador":
        ocr = None
    return {"ok": True, "ocr": ocr}


def _tess_tem_por(tess):
    try:
        r = subprocess.run([tess, "--list-langs"], capture_output=True, text=True, timeout=20)
        return "por" in r.stdout.split()
    except (OSError, subprocess.SubprocessError):
        return False


# ------------------------------------------------------------------ regras iguais às do site
def agrupar_linhas(itens):
    """Junta os pedaços de texto da mesma linha (mesma altura), da esquerda para a direita."""
    linhas = []
    for s, x, y, size in sorted(itens, key=lambda i: (i[2], i[1])):
        row = next((r for r in linhas if abs(r["y"] - y) < max(2, size * 0.45)), None)
        if row:
            row["itens"].append((x, s)); row["size"] = max(row["size"], size)
        else:
            linhas.append({"y": y, "size": size, "itens": [(x, s)]})
    out = []
    for r in sorted(linhas, key=lambda r: r["y"]):
        texto = " ".join(" ".join(s for _, s in sorted(r["itens"], key=lambda i: i[0])).split())
        if texto:
            out.append({"y": r["y"], "size": r["size"], "text": texto})
    return out


def caixas_de_figuras(caixas, W, H):
    """Mesmas regras do site: tamanho mínimo, página escaneada (uma imagem cobrindo quase tudo) e junção dos pedaços."""
    bs = []
    for b in caixas:
        x, y = max(0, b[0]), max(0, b[1])
        w, h = min(W, b[0] + b[2]) - x, min(H, b[1] + b[3]) - y
        if w >= 50 and h >= 40 and w / h < 8 and h / w < 8:
            bs.append([x, y, w, h])
    escaneada = any(b[2] * b[3] >= 0.8 * W * H for b in bs)
    bs = [b for b in bs if b[2] * b[3] < 0.8 * W * H]
    mudou = True
    while mudou:
        mudou = False
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                a, b, g = bs[i], bs[j], 6
                if a[0] - g < b[0] + b[2] and b[0] - g < a[0] + a[2] and a[1] - g < b[1] + b[3] and b[1] - g < a[1] + a[3]:
                    x, y = min(a[0], b[0]), min(a[1], b[1])
                    bs[i] = [x, y, max(a[0] + a[2], b[0] + b[2]) - x, max(a[1] + a[3], b[1] + b[3]) - y]
                    del bs[j]; mudou = True
                    break
            if mudou:
                break
    return sorted(bs, key=lambda b: b[1]), escaneada


# ------------------------------------------------------------------ imagens
def _webp(img, max_w, q):
    if img.width > max_w:
        from PIL import Image
        img = img.resize((max_w, round(img.height * max_w / img.width)), Image.LANCZOS)
    b = io.BytesIO(); img.save(b, "WEBP", quality=q, method=4)
    return base64.b64encode(b.getvalue()).decode()


def _jpeg(img, q=90):
    b = io.BytesIO(); img.convert("RGB").save(b, "JPEG", quality=q)
    return base64.b64encode(b.getvalue()).decode()


def _ocr(img, ocr):
    """Texto de uma imagem (PIL). ocr = 'tesseract' (programa instalado) ou 'embutido' (PyMuPDF)."""
    if ocr == "tesseract":
        b = io.BytesIO(); img.convert("L").save(b, "PNG")
        cmd = [_tesseract(), "stdin", "stdout", "-l", "por", "--psm", "3"]
        if os.path.isfile(os.path.join(TESSDATA, "por.traineddata")):
            cmd[3:3] = ["--tessdata-dir", TESSDATA]
        r = subprocess.run(cmd, input=b.getvalue(), capture_output=True, timeout=300,
                           env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.decode("utf-8", "replace").strip()
    import pymupdf
    b = io.BytesIO(); img.convert("RGB").save(b, "PNG")
    pix = pymupdf.Pixmap(b.getvalue())
    pdf = pymupdf.open("pdf", pix.pdfocr_tobytes(language="por", tessdata=TESSDATA))
    return "\n".join(pg.get_text() for pg in pdf).strip()


# ------------------------------------------------------------------ PDF
def _itens(pg):
    """Pedaços de texto da página: (texto, x, y da linha de base, tamanho da letra), em pontos, a partir do canto de cima."""
    import pymupdf
    m = pg.rotation_matrix
    out = []
    for bl in pg.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP)["blocks"]:
        for ln in bl.get("lines", []):
            for sp in ln.get("spans", []):
                t = sp.get("text", "")
                if t.strip():
                    o = pymupdf.Point(sp["origin"]) * m
                    out.append([t, round(o.x, 2), round(o.y, 2), round(sp.get("size") or 10, 2)])
    return out


def _caixas_brutas(pg):
    import pymupdf
    m = pg.rotation_matrix
    out = []
    for info in pg.get_image_info():
        r = pymupdf.Rect(info["bbox"]) * m
        if r.is_valid and not r.is_empty:
            out.append([r.x0, r.y0, r.width, r.height])
    return out


def texto_pdf(arq):
    """Só o texto (primeira etapa do envio): rápido."""
    import pymupdf
    doc = pymupdf.open(arq)
    try:
        return [{"w": pg.rect.width, "h": pg.rect.height, "itens": _itens(pg)} for pg in doc]
    finally:
        doc.close()


def indice_pdf(arq):
    """Índice clicável do PDF (marcadores): [{t, pg, nivel}], a página começando em 1. Não lê o texto das páginas."""
    import pymupdf
    with pymupdf.open(arq) as doc:
        out = []
        for nivel, titulo, pg in doc.get_toc(simple=True)[:3000]:
            t = " ".join(str(titulo or "").split())[:160]
            if t and pg and pg > 0:
                out.append({"t": t, "pg": int(pg), "nivel": int(nivel)})
        return out


def contar_paginas(arq):
    import pymupdf
    with pymupdf.open(arq) as doc:
        return len(doc)


def imagens_pdf(arq, indices, ocr):
    """Texto, figuras, foto e OCR das páginas pedidas (cada processo faz algumas páginas)."""
    import pymupdf
    from PIL import Image
    doc = pymupdf.open(arq)
    out = []
    try:
        for i in indices:
            pg = doc[i]
            W, H = pg.rect.width, pg.rect.height
            itens = _itens(pg)
            caixas, escaneada = caixas_de_figuras(_caixas_brutas(pg), W, H)
            linhas = agrupar_linhas(itens)
            n_letras = sum(len("".join(s.split())) for s, *_ in itens)
            precisa_ocr = n_letras < 40 or (escaneada and (len(linhas) < 5 or n_letras < 600))
            p = {"w": W, "h": H, "itens": itens, "caixas": caixas, "escaneada": escaneada,
                 "recortes": [], "foto": None, "fotoRev": None, "ocr": None, "fotoOcr": None}
            # página só de texto: não precisa ser desenhada (o site faz a mesma conta)
            if caixas or precisa_ocr or n_letras < 300:
                s = min(ESCALA_MAX, LARGURA / W)
                pix = pg.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                for x, y, w, h in caixas:
                    pad = 4
                    sx, sy = max(0, math.floor(x * s) - pad), max(0, math.floor(y * s) - pad)
                    sw = min(img.width - sx, math.ceil(w * s) + pad * 2)
                    sh = min(img.height - sy, math.ceil(h * s) + pad * 2)
                    p["recortes"].append(_webp(img.crop((sx, sy, sx + sw, sy + sh)), 1000, 72) if sw > 0 and sh > 0 else None)
                if precisa_ocr:
                    if ocr:
                        try:
                            p["ocr"] = _ocr(img, ocr)
                        except Exception as e:                  # o site faz o OCR desta página
                            p["fotoOcr"] = _jpeg(img); p["erroOcr"] = str(e)[:200]
                    else:
                        p["fotoOcr"] = _jpeg(img)
                if precisa_ocr or n_letras < 300:
                    p["foto"] = _webp(img, 1200, 62)
                elif caixas:                               # para a IA trocar uma figura mal recortada pela página inteira
                    p["fotoRev"] = _webp(img, 1200, 62)
            out.append(p)
    finally:
        doc.close()
    return out


def fotos_pdf(arq, indices):
    """Só a foto (página inteira) das páginas pedidas: o "Ver página inteira" das figuras da apostila."""
    import pymupdf
    from PIL import Image
    doc = pymupdf.open(arq)
    out = []
    try:
        for i in indices:
            if i < 0 or i >= doc.page_count:
                out.append({"i": i, "foto": None})
                continue
            pg = doc[i]
            s = min(ESCALA_MAX, LARGURA / pg.rect.width)
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            out.append({"i": i, "foto": _webp(img, 1200, 62)})
    finally:
        doc.close()
    return out


def _heic():
    """Fotos de iPhone (HEIC/HEIF): o PIL só abre com o pillow-heif (o navegador também não abre)."""
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except Exception:  # noqa: BLE001
        pass


def imagem(arq, ocr):
    """Foto ou print (JPG, PNG, HEIC do iPhone...): OCR e a imagem guardada, iguais ao site."""
    from PIL import Image
    _heic()
    img = Image.open(arq)
    img.load()
    if img.mode not in ("RGB", "L"):
        fundo = Image.new("RGB", img.size, "white")
        fundo.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = fundo
    img = img.convert("RGB")
    s = min(1, 1600 / max(img.width, img.height))
    if s < 1:
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    p = {"foto": _webp(img, 1400, 68), "ocr": None, "fotoOcr": None}
    if ocr:
        try:
            p["ocr"] = _ocr(img, ocr)
        except Exception:
            p["fotoOcr"] = _jpeg(img)
    else:
        p["fotoOcr"] = _jpeg(img)
    return p
