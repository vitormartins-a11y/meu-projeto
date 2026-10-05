"""Testes do montar.py. Rodar com:  python -m unittest discover tests"""

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import montar  # noqa: E402

BASE = {
    "disciplina": "Ginecologia", "tema": "Amenorreia", "origem": "JA_CAIU", "tipo": "FECHADA",
    "enunciado": "Enunciado", "alt_a": "A", "alt_b": "B", "alt_c": "C", "gabarito": "b",
    "selo": "OFICIAL", "justificativa": "Correta: (b).", "dificuldade": "MEDIA",
    "status": "VALIDADA", "responsavel": "Ana", "revisor": "Bia",
}


def linha(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


class MontarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dados = os.path.join(self.tmp, "dados")
        self.saida = os.path.join(self.tmp, "saida")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def escrever(self, periodo, questoes, flashcards=(), temas=None):
        pasta = os.path.join(self.dados, f"P{periodo}")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, "Banco_P%s - Questoes.csv" % periodo), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=montar.COLUNAS_QUESTOES)
            w.writeheader()
            for q in questoes:
                w.writerow({k: q.get(k, "") for k in montar.COLUNAS_QUESTOES})
        with open(os.path.join(pasta, "Flashcards.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=montar.COLUNAS_FLASHCARDS)
            w.writeheader()
            for c in flashcards:
                w.writerow(c)
        if temas:
            with open(os.path.join(pasta, "Temas.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["disciplina", "tema"])
                w.writerows(temas)

    def rodar(self, periodo):
        montar.main(["--periodo", str(periodo), "--dados", self.dados, "--saida", self.saida,
                     "--config", os.path.join(RAIZ, "config.json")])
        with open(os.path.join(self.saida, f"P{periodo}", f"banco_p{periodo}.json"), encoding="utf-8") as f:
            banco = json.load(f)
        with open(os.path.join(self.saida, f"P{periodo}", "A_CONFERIR.md"), encoding="utf-8") as f:
            relatorio = f.read()
        return {q["id"]: q for q in banco}, relatorio

    def test_questao_valida(self):
        self.escrever(8, [linha(id="P8-GIN-001")])
        banco, _ = self.rodar(8)
        q = banco["P8-GIN-001"]
        self.assertEqual(q["status"], "VALIDADA")
        self.assertEqual([a["letra"] for a in q["alternativas"]], ["a", "b", "c"])

    def test_erros_ficam_fora_do_app(self):
        self.escrever(8, [
            linha(id="P8-GIN-001"),
            linha(id="P8-GIN-001"),                 # id repetido
            linha(id="P8-GIN-002", gabarito=""),    # fechada sem gabarito
            linha(id="P8-GIN-003", gabarito="e"),   # gabarito em alternativa vazia
            linha(id="P8-GIN-004", tipo="ABERTA"),  # tipo fora do menu
            linha(id=""),                           # sem id
        ])
        banco, rel = self.rodar(8)
        self.assertEqual(list(banco), ["P8-GIN-001"])
        for trecho in ("id repetido", "sem gabarito", "alternativa vazia", "fora do menu", "id vazio"):
            self.assertIn(trecho, rel)

    def test_regras_que_rebaixam_para_a_conferir(self):
        self.escrever(8, [
            linha(id="P8-GIN-001", justificativa=""),
            linha(id="P8-GIN-002", selo="DERIVADO", fonte=""),
            linha(id="P8-GIN-003", selo="RESPOSTA_ALUNO"),
            linha(id="P8-GIN-004", revisor="Ana"),          # revisou a própria questão
            linha(id="P8-GIN-005", revisor=""),
            linha(id="P8-GIN-006", enunciado="[questão com imagem, ver arquivo de origem]"),
            linha(id="P8-GIN-007", selo="DERIVADO", fonte="Diretriz X"),
        ])
        banco, _ = self.rodar(8)
        for i in range(1, 7):
            self.assertEqual(banco[f"P8-GIN-00{i}"]["status"], "A_CONFERIR", i)
        self.assertEqual(banco["P8-GIN-007"]["status"], "VALIDADA")

    def test_normaliza_valores_digitados_a_mao(self):
        self.escrever(8, [linha(id="P8-GIN-001", origem="Já caiu", dificuldade="Média", gabarito="B)",
                                tema="amenorreia")],
                      temas=[["Ginecologia", "Amenorreia"]])
        banco, _ = self.rodar(8)
        q = banco["P8-GIN-001"]
        self.assertEqual((q["origem"], q["dificuldade"], q["gabarito"], q["tema"]),
                         ("JA_CAIU", "MEDIA", "b", "Amenorreia"))

    def test_tema_fora_da_aba_temas_gera_aviso(self):
        self.escrever(8, [linha(id="P8-GIN-001", tema="Endometriose")], temas=[["Ginecologia", "Amenorreia"]])
        _, rel = self.rodar(8)
        self.assertIn("não está na aba Temas", rel)

    def test_discursiva(self):
        self.escrever(8, [linha(id="P8-CAR-001", tipo="DISCURSIVA", alt_a="", alt_b="", alt_c="", gabarito="",
                                resposta_modelo="Resposta")])
        banco, _ = self.rodar(8)
        self.assertEqual(banco["P8-CAR-001"]["tipo"], "DISCURSIVA")
        self.assertEqual(banco["P8-CAR-001"]["status"], "VALIDADA")

    def test_flashcards_e_anki(self):
        self.escrever(8, [linha(id="P8-GIN-001")], flashcards=[
            {"id": "F1", "disciplina": "Ginecologia", "tema": "Amenorreia", "frente": "Pergunta; com ponto e vírgula",
             "verso": "Resposta", "questao_origem": "P8-GIN-001"},
            {"id": "F2", "disciplina": "Ginecologia", "tema": "Amenorreia", "frente": "", "verso": "x", "questao_origem": ""},
        ])
        self.rodar(8)
        with open(os.path.join(self.saida, "P8", "flashcards_p8.json"), encoding="utf-8") as f:
            self.assertEqual([c["id"] for c in json.load(f)], ["F1"])
        with open(os.path.join(self.saida, "P8", "flashcards_p8.csv"), encoding="utf-8") as f:
            texto = f.read()
        self.assertIn("#separator:Semicolon", texto)
        self.assertIn('"Pergunta; com ponto e vírgula";Resposta;Ginecologia::Amenorreia', texto)

    def test_app_junta_periodos_e_escapa_script(self):
        self.escrever(8, [linha(id="P8-GIN-001", enunciado="PA < 90 </script><b>x</b>")])
        self.escrever(7, [linha(id="P7-GIN-001")])
        self.rodar(8)
        self.rodar(7)
        with open(os.path.join(self.saida, "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("/*__DADOS__*/", html)
        self.assertIn('"7":', html)
        self.assertIn('"8":', html)
        self.assertNotIn("</script><b>", html)
        self.assertIn('content="noindex', html)

    def test_id_repetido_entre_periodos(self):
        self.escrever(8, [linha(id="P8-GIN-001")])
        self.escrever(7, [linha(id="P8-GIN-001")])
        self.rodar(8)
        banco7, rel = self.rodar(7)
        self.assertEqual(banco7, {})
        self.assertIn("já usado no período 8", rel)


if __name__ == "__main__":
    unittest.main()
