#!/usr/bin/env python3
"""
montar.py — converte a planilha do Banco de Questões nos dados do app.

Uso (no computador ou no Google Colab):

    python montar.py --periodo 8

Lê   dados/P8/Questoes.csv, dados/P8/Flashcards.csv e (opcional) dados/P8/Temas.csv
Gera saida/P8/banco_p8.json
     saida/P8/flashcards_p8.json
     saida/P8/flashcards_p8.csv     (para importar no Anki, separador ;)
     saida/P8/A_CONFERIR.md         (problemas encontrados e questões não conferidas)
     saida/index.html               (o app, com os dados de TODOS os períodos já montados)

Os CSVs saem da planilha do Google em Arquivo > Fazer download > CSV, uma aba por vez.
O nome que o Google dá ("Banco_P8 - Questoes.csv") também é reconhecido.

Não usa nenhuma biblioteca externa: só Python 3.8+.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))

COLUNAS_QUESTOES = [
    "id", "disciplina", "tema", "subtema", "origem", "tipo", "enunciado",
    "alt_a", "alt_b", "alt_c", "alt_d", "alt_e", "gabarito", "resposta_modelo",
    "selo", "justificativa", "fonte", "dificuldade", "arquivo_origem", "ano",
    "status", "responsavel", "revisor",
]
COLUNAS_FLASHCARDS = ["id", "disciplina", "tema", "frente", "verso", "questao_origem"]
LETRAS = ["a", "b", "c", "d", "e"]

VALORES = {
    "origem": {"JA_CAIU", "NOVA"},
    "tipo": {"FECHADA", "DISCURSIVA"},
    "selo": {"OFICIAL", "DERIVADO", "RESPOSTA_ALUNO", "AUTORAL"},
    "dificuldade": {"FACIL", "MEDIA", "DIFICIL"},
    "status": {"A_CONFERIR", "VALIDADA"},
}

MARCA_IMAGEM = "[questão com imagem"


# ----------------------------------------------------------------- utilidades

def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar_enum(valor):
    """'Já caiu' -> 'JA_CAIU', 'média' -> 'MEDIA', 'Resposta aluno' -> 'RESPOSTA_ALUNO'."""
    v = sem_acento(valor.strip()).upper()
    v = re.sub(r"[\s\-]+", "_", v)
    if v == "RESPOSTA_DE_ALUNO":
        v = "RESPOSTA_ALUNO"
    if v == "A_CONFERIR" or v == "CONFERIR":
        v = "A_CONFERIR"
    return v


def normalizar_chave(texto):
    """Usado para comparar disciplina/tema sem diferenciar acento e maiúscula."""
    return re.sub(r"\s+", " ", sem_acento(texto).strip().lower())


def ler_csv(caminho):
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        leitor = csv.DictReader(f)
        if leitor.fieldnames is None:
            return [], []
        cabecalho = [(c or "").strip().lower() for c in leitor.fieldnames]
        leitor.fieldnames = cabecalho
        linhas = []
        for n, linha in enumerate(leitor, start=2):  # linha 1 é o cabeçalho
            limpa = {k: (v or "").strip() for k, v in linha.items() if k}
            if any(limpa.values()):
                limpa["_linha"] = n
                linhas.append(limpa)
        return cabecalho, linhas


def achar_csv(pasta, aba):
    """Acha 'Questoes.csv' ou 'Banco_P8 - Questoes.csv' (sem diferenciar acento/maiúscula)."""
    if not os.path.isdir(pasta):
        return None
    alvo = normalizar_chave(aba)
    candidatos = []
    for nome in sorted(os.listdir(pasta)):
        if not nome.lower().endswith(".csv"):
            continue
        base = normalizar_chave(os.path.splitext(nome)[0])
        if base == alvo or base.endswith("- " + alvo) or base.endswith(" " + alvo) or base.endswith("_" + alvo):
            candidatos.append(os.path.join(pasta, nome))
    return candidatos[0] if candidatos else None


class Relatorio:
    def __init__(self):
        self.erros = []    # linha não entra no app
        self.avisos = []   # linha entra, mas pode ter sido rebaixada para A_CONFERIR

    def erro(self, aba, linha, ident, msg):
        self.erros.append((aba, linha, ident, msg))

    def aviso(self, aba, linha, ident, msg):
        self.avisos.append((aba, linha, ident, msg))


# ------------------------------------------------------------------ questões

def validar_questoes(linhas, temas, periodo, rel, ids_outros_periodos):
    questoes = []
    vistos = {}
    for l in linhas:
        n = l["_linha"]
        qid = l.get("id", "")
        rotulo = qid or "(sem id)"
        problemas_graves = []
        rebaixar = []

        if not qid:
            problemas_graves.append("id vazio")
        elif qid in vistos:
            problemas_graves.append(f"id repetido (já usado na linha {vistos[qid]})")
        elif qid in ids_outros_periodos:
            problemas_graves.append(f"id repetido (já usado no período {ids_outros_periodos[qid]})")
        else:
            vistos[qid] = n
            if not qid.upper().startswith(f"P{periodo}-"):
                rel.aviso("Questoes", n, rotulo, f"id não começa com P{periodo}- (padrão: P{periodo}-GIN-001)")

        # valores de menu
        valores = {}
        for campo, permitidos in VALORES.items():
            bruto = l.get(campo, "")
            v = normalizar_enum(bruto) if bruto else ""
            if not v:
                if campo in ("tipo", "selo"):
                    problemas_graves.append(f"{campo} vazio")
                elif campo == "status":
                    v = "A_CONFERIR"
                else:
                    rel.aviso("Questoes", n, rotulo, f"{campo} vazio")
            elif v not in permitidos:
                msg = f"{campo} = \"{bruto}\" fora do menu ({', '.join(sorted(permitidos))})"
                if campo in ("tipo", "selo"):
                    problemas_graves.append(msg)
                else:
                    rel.aviso("Questoes", n, rotulo, msg)
                    v = "A_CONFERIR" if campo == "status" else ""
            valores[campo] = v

        disciplina = l.get("disciplina", "")
        tema = l.get("tema", "")
        if not disciplina:
            problemas_graves.append("disciplina vazia")
        if not tema:
            problemas_graves.append("tema vazio")
        if temas is not None and disciplina and tema:
            chave = (normalizar_chave(disciplina), normalizar_chave(tema))
            if chave not in temas:
                rel.aviso("Questoes", n, rotulo, f"disciplina/tema \"{disciplina} / {tema}\" não está na aba Temas")
            else:
                disciplina, tema = temas[chave]  # usa a grafia oficial da aba Temas

        enunciado = l.get("enunciado", "")
        if not enunciado:
            problemas_graves.append("enunciado vazio")

        alternativas = [{"letra": x, "texto": l.get("alt_" + x, "")} for x in LETRAS if l.get("alt_" + x, "")]
        gabarito = l.get("gabarito", "").strip().lower().strip("()). ")
        resposta_modelo = l.get("resposta_modelo", "")

        if valores["tipo"] == "FECHADA":
            letras_preenchidas = [a["letra"] for a in alternativas]
            ultima = max((LETRAS.index(x) for x in letras_preenchidas), default=-1)
            buracos = [x for x in LETRAS[:ultima] if x not in letras_preenchidas]
            if buracos:
                rel.aviso("Questoes", n, rotulo, "alternativa(s) vazia(s) no meio: " + ", ".join(buracos))
            if len(alternativas) < 2:
                problemas_graves.append("questão fechada com menos de 2 alternativas")
            if not gabarito:
                problemas_graves.append("questão fechada sem gabarito")
            elif gabarito not in LETRAS:
                problemas_graves.append(f"gabarito \"{l.get('gabarito')}\" não é uma letra de a a e")
            elif gabarito not in letras_preenchidas:
                problemas_graves.append(f"gabarito ({gabarito}) aponta para alternativa vazia")
        elif valores["tipo"] == "DISCURSIVA":
            if not resposta_modelo:
                rel.aviso("Questoes", n, rotulo, "discursiva sem resposta_modelo")
                rebaixar.append("sem resposta-modelo")
            gabarito = ""

        justificativa = l.get("justificativa", "")
        fonte = l.get("fonte", "")
        status = valores["status"]

        # regras do plano que rebaixam para A_CONFERIR
        if not justificativa:
            rebaixar.append("justificativa vazia")
        if valores["selo"] == "DERIVADO" and not fonte:
            rebaixar.append("selo DERIVADO sem fonte")
        if valores["selo"] == "RESPOSTA_ALUNO" and status == "VALIDADA":
            rebaixar.append("selo RESPOSTA_ALUNO não pode ser VALIDADA (confirme com fonte e troque o selo para DERIVADO)")
        if MARCA_IMAGEM in enunciado.lower() and status == "VALIDADA":
            rebaixar.append("questão com imagem fica A_CONFERIR até as imagens entrarem no app")
        if status == "VALIDADA":
            revisor = l.get("revisor", "")
            responsavel = l.get("responsavel", "")
            if not revisor:
                rebaixar.append("VALIDADA sem revisor")
            elif responsavel and normalizar_chave(revisor) == normalizar_chave(responsavel):
                rebaixar.append("revisor é o próprio responsável (ninguém valida a própria questão)")

        ano = l.get("ano", "")
        if ano and not re.fullmatch(r"\d{4}", ano):
            rel.aviso("Questoes", n, rotulo, f"ano \"{ano}\" não é um número de 4 dígitos")
            ano = ""

        if problemas_graves:
            for p in problemas_graves:
                rel.erro("Questoes", n, rotulo, p)
            continue

        if rebaixar:
            if status == "VALIDADA":
                rel.aviso("Questoes", n, rotulo, "rebaixada para A_CONFERIR: " + "; ".join(rebaixar))
            else:
                for r in rebaixar:
                    rel.aviso("Questoes", n, rotulo, r)
            status = "A_CONFERIR"

        q = {
            "id": qid,
            "periodo": periodo,
            "disciplina": disciplina,
            "tema": tema,
            "subtema": l.get("subtema", ""),
            "origem": valores["origem"],
            "tipo": valores["tipo"],
            "dificuldade": valores["dificuldade"],
            "status": status,
            "enunciado": enunciado,
            "alternativas": alternativas,
            "gabarito": gabarito,
            "resposta_modelo": resposta_modelo,
            "selo": valores["selo"],
            "justificativa": justificativa,
            "fonte": fonte,
            "ano": int(ano) if ano else None,
            "arquivo_origem": l.get("arquivo_origem", ""),
        }
        questoes.append(q)
    return questoes


# ---------------------------------------------------------------- flashcards

def validar_flashcards(linhas, ids_questoes, temas, rel):
    cards = []
    vistos = {}
    for l in linhas:
        n = l["_linha"]
        fid = l.get("id", "")
        rotulo = fid or "(sem id)"
        graves = []
        if not fid:
            graves.append("id vazio")
        elif fid in vistos:
            graves.append(f"id repetido (já usado na linha {vistos[fid]})")
        else:
            vistos[fid] = n
        for campo in ("frente", "verso", "disciplina", "tema"):
            if not l.get(campo, ""):
                graves.append(f"{campo} vazio")
        if graves:
            for g in graves:
                rel.erro("Flashcards", n, rotulo, g)
            continue
        disciplina, tema = l["disciplina"], l["tema"]
        if temas is not None:
            chave = (normalizar_chave(disciplina), normalizar_chave(tema))
            if chave in temas:
                disciplina, tema = temas[chave]
            else:
                rel.aviso("Flashcards", n, rotulo, f"disciplina/tema \"{disciplina} / {tema}\" não está na aba Temas")
        origem = l.get("questao_origem", "")
        if origem and origem not in ids_questoes:
            rel.aviso("Flashcards", n, rotulo, f"questao_origem {origem} não existe (ou foi descartada por erro)")
        cards.append({
            "id": fid,
            "disciplina": disciplina,
            "tema": tema,
            "frente": l["frente"],
            "verso": l["verso"],
            "questao_origem": origem,
        })
    return cards


def ler_temas(caminho):
    if not caminho:
        return None
    _, linhas = ler_csv(caminho)
    temas = {}
    for l in linhas:
        d, t = l.get("disciplina", ""), l.get("tema", "")
        if d and t:
            temas[(normalizar_chave(d), normalizar_chave(t))] = (d, t)
    return temas or None


# ------------------------------------------------------------------- saídas

def escrever_anki(cards, caminho):
    def tag(texto):
        return re.sub(r"[^\w]+", "_", sem_acento(texto)).strip("_")
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        f.write("#separator:Semicolon\n#html:false\n#columns:Frente;Verso;Tags\n#tags column:3\n")
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        for c in cards:
            w.writerow([c["frente"], c["verso"], f"{tag(c['disciplina'])}::{tag(c['tema'])}"])


def escrever_relatorio(caminho, periodo, rel, questoes, cards, arquivos):
    a_conferir = [q for q in questoes if q["status"] == "A_CONFERIR"]
    linhas = [
        f"# A conferir — {periodo}º período",
        "",
        f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} a partir de: " + ", ".join(f"`{os.path.basename(a)}`" for a in arquivos if a),
        "",
        f"- Questões no app: **{len(questoes)}** ({len(questoes) - len(a_conferir)} validadas, {len(a_conferir)} a conferir)",
        f"- Flashcards no app: **{len(cards)}**",
        f"- Erros (linha ficou FORA do app): **{len(rel.erros)}**",
        f"- Avisos (linha entrou, mas precisa de atenção): **{len(rel.avisos)}**",
        "",
    ]

    def tabela(titulo, itens, explicacao):
        out = [f"## {titulo}", "", explicacao, ""]
        if not itens:
            return out + ["Nenhum.", ""]
        out += ["| Aba | Linha | id | Problema |", "| --- | --- | --- | --- |"]
        for aba, n, ident, msg in itens:
            out.append(f"| {aba} | {n} | {ident} | {msg.replace('|', '/')} |")
        return out + [""]

    linhas += tabela("Erros", rel.erros, "Corrija na planilha e rode o script de novo. Essas linhas não aparecem no app.")
    linhas += tabela("Avisos", rel.avisos, "Essas linhas aparecem no app, mas com o aviso \"não conferida\" quando foram rebaixadas.")

    linhas += ["## Questões A_CONFERIR", "", "Aparecem no app com o aviso \"não conferida\". Precisam de revisão cruzada (passo 5).", ""]
    if a_conferir:
        linhas += ["| id | Disciplina | Tema | Selo |", "| --- | --- | --- | --- |"]
        for q in a_conferir:
            linhas.append(f"| {q['id']} | {q['disciplina']} | {q['tema']} | {q['selo']} |")
    else:
        linhas.append("Nenhuma.")
    linhas.append("")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))


def carregar_periodos(saida):
    periodos = {}
    for pasta in sorted(glob.glob(os.path.join(saida, "P*"))):
        m = re.fullmatch(r"P(\d+)", os.path.basename(pasta))
        if not m:
            continue
        p = m.group(1)
        banco = os.path.join(pasta, f"banco_p{p}.json")
        flash = os.path.join(pasta, f"flashcards_p{p}.json")
        if not os.path.exists(banco):
            continue
        with open(banco, encoding="utf-8") as f:
            questoes = json.load(f)
        cards = []
        if os.path.exists(flash):
            with open(flash, encoding="utf-8") as f:
                cards = json.load(f)
        periodos[p] = {"questoes": questoes, "flashcards": cards}
    return periodos


def achar_template(caminho=None):
    opcoes = [caminho] if caminho else []
    opcoes += [os.path.join(AQUI, "app", "template.html"), os.path.join(AQUI, "template.html"), "template.html"]
    for c in opcoes:
        if c and os.path.exists(c):
            return c
    return None


def montar_app(saida, config, template_path):
    periodos = carregar_periodos(saida)
    dados = {
        "config": config,
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "periodos": periodos,
    }
    # "</" escapado para o JSON nunca fechar a tag <script> antes da hora
    js = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    with open(template_path, encoding="utf-8") as f:
        html = f.read()
    marcador = "/*__DADOS__*/null"
    if marcador not in html:
        raise SystemExit(f"O template {template_path} não tem o marcador {marcador}")
    html = html.replace(marcador, js)
    titulo = config.get("titulo") or "Banco de Questões"
    html = html.replace("<title>Banco de Questões</title>", f"<title>{titulo}</title>")
    destino = os.path.join(saida, "index.html")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(html)
    return destino, periodos


def ler_config(caminho):
    padrao = {"titulo": "Banco de Questões", "subtitulo": "", "form_url": ""}
    if caminho and os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            padrao.update(json.load(f))
    return padrao


# --------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Converte os CSVs da planilha nos dados do app do Banco de Questões.")
    ap.add_argument("--periodo", required=True, help="número do período, ex.: 8")
    ap.add_argument("--dados", default="dados", help="pasta com as subpastas P8, P7... (padrão: dados)")
    ap.add_argument("--saida", default="saida", help="pasta onde o app e os JSONs são gerados (padrão: saida)")
    ap.add_argument("--questoes", help="caminho do CSV da aba Questoes (se não estiver em dados/P<n>/)")
    ap.add_argument("--flashcards", help="caminho do CSV da aba Flashcards")
    ap.add_argument("--temas", help="caminho do CSV da aba Temas (opcional, mas recomendado)")
    ap.add_argument("--config", default=None, help="config.json com titulo, subtitulo e form_url (padrão: config.json ao lado do script)")
    ap.add_argument("--template", default=None, help="caminho do app/template.html")
    args = ap.parse_args(argv)

    periodo = re.sub(r"\D", "", str(args.periodo))
    if not periodo:
        ap.error("--periodo precisa ser um número, ex.: 8")
    pasta = os.path.join(args.dados, f"P{periodo}")

    arq_q = args.questoes or achar_csv(pasta, "Questoes") or achar_csv(".", "Questoes")
    arq_f = args.flashcards or achar_csv(pasta, "Flashcards") or achar_csv(".", "Flashcards")
    arq_t = args.temas or achar_csv(pasta, "Temas") or achar_csv(".", "Temas")
    if not arq_q or not os.path.exists(arq_q):
        sys.exit(f"Não achei o CSV da aba Questoes. Coloque-o em {pasta}/Questoes.csv ou use --questoes.")

    cab, linhas_q = ler_csv(arq_q)
    faltando = [c for c in ("id", "disciplina", "tema", "tipo", "enunciado", "gabarito", "selo") if c not in cab]
    if faltando:
        sys.exit(f"O CSV {arq_q} não tem as colunas: {', '.join(faltando)}. Confira o cabeçalho com modelo/Questoes.csv.")

    temas = ler_temas(arq_t)
    rel = Relatorio()

    # ids dos outros períodos já montados, para pegar id repetido entre períodos
    ids_outros = {}
    for p, conteudo in carregar_periodos(args.saida).items():
        if p != periodo:
            for q in conteudo["questoes"]:
                ids_outros[q["id"]] = p

    questoes = validar_questoes(linhas_q, temas, periodo, rel, ids_outros)
    cards = []
    if arq_f and os.path.exists(arq_f):
        _, linhas_f = ler_csv(arq_f)
        cards = validar_flashcards(linhas_f, {q["id"] for q in questoes}, temas, rel)
    else:
        print("Aviso: CSV de Flashcards não encontrado; o período fica sem flashcards.")

    destino = os.path.join(args.saida, f"P{periodo}")
    os.makedirs(destino, exist_ok=True)
    with open(os.path.join(destino, f"banco_p{periodo}.json"), "w", encoding="utf-8") as f:
        json.dump(questoes, f, ensure_ascii=False, indent=1)
    with open(os.path.join(destino, f"flashcards_p{periodo}.json"), "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=1)
    escrever_anki(cards, os.path.join(destino, f"flashcards_p{periodo}.csv"))
    escrever_relatorio(os.path.join(destino, "A_CONFERIR.md"), periodo, rel, questoes, cards, [arq_q, arq_f, arq_t])

    config = ler_config(args.config or os.path.join(AQUI, "config.json"))
    template = achar_template(args.template)
    if not template:
        sys.exit("Não achei app/template.html. Ele precisa estar ao lado do montar.py (ou use --template).")
    app, periodos = montar_app(args.saida, config, template)

    a_conferir = sum(1 for q in questoes if q["status"] == "A_CONFERIR")
    print(f"Período {periodo}: {len(questoes)} questões ({a_conferir} a conferir), {len(cards)} flashcards.")
    print(f"Erros: {len(rel.erros)} (linhas fora do app) · Avisos: {len(rel.avisos)}")
    print(f"Relatório: {os.path.join(destino, 'A_CONFERIR.md')}")
    print(f"Anki:      {os.path.join(destino, f'flashcards_p{periodo}.csv')}")
    print(f"App:       {app}  (períodos: {', '.join(sorted(periodos, key=int))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
