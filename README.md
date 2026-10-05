# Banco de Questões de Medicina — sem IA e com custo zero

App de estudo com as provas que já caíram, montado a partir de uma planilha do Google.
Nenhuma etapa usa IA e nada é pago. O plano completo está em [`docs/plano.md`](docs/plano.md).

**Ver funcionando:** abra [`demo/index.html`](demo/index.html) no navegador. É um banco de exemplo com 5 questões e 5 flashcards.

## Como funciona

```
Planilha Banco_P8 (Google Planilhas)
   │  Arquivo > Fazer download > CSV  (abas Questoes, Flashcards, Temas)
   ▼
dados/P8/*.csv
   │  python montar.py --periodo 8      (no computador ou no Google Colab)
   ▼
saida/index.html            ← o app, um arquivo só, com todos os períodos dentro
saida/P8/A_CONFERIR.md      ← problemas encontrados na planilha
saida/P8/flashcards_p8.csv  ← para importar no Anki
saida/P8/banco_p8.json, flashcards_p8.json
```

## O que tem aqui

| Arquivo | Para que serve |
| --- | --- |
| `montar.py` | Confere a planilha e gera o app. Só usa Python, sem instalar nada. |
| `app/template.html` | O código do app. O `montar.py` coloca os dados dentro dele. |
| `config.json` | Título do app e link do formulário de "reportar erro". |
| `modelo/*.csv` | Cabeçalhos das quatro abas da planilha (Questoes, Flashcards, Temas, Inventario). |
| `exemplo/P8/*.csv` | Planilha de exemplo, já preenchida. |
| `demo/` | App gerado a partir do exemplo. |
| `colab/montar_banco.ipynb` | Caderno do Google Colab para rodar o script pelo navegador. |
| `apps_script/Code.gs` | Publicação restrita ao e-mail da faculdade (Google Apps Script). |
| `tests/test_montar.py` | Testes do script: `python -m unittest discover tests`. |
| `docs/plano.md` | O plano completo (passos 1 a 9, cronograma e regras). |
| `docs/preview_original.html` | A primeira prévia do app, feita antes do script. |
| `docs/HISTORICO.md` | O que veio da conversa anterior e o que foi feito nesta. |

## Passo a passo do coordenador

1. **Criar a planilha.** No Google Planilhas, crie `Banco_P8` com as abas `Questoes`, `Flashcards`, `Temas` e `Inventario`.
   Para ter os cabeçalhos certos, use Arquivo > Importar com os CSVs de `modelo/`, um por aba.
   Depois crie os menus suspensos (Dados > Validação de dados), como no passo 2 do plano.
2. **Preencher.** A turma transcreve e revisa (passos 3 a 6 do plano).
3. **Baixar os CSVs.** Em cada aba: Arquivo > Fazer download > Valores separados por vírgula (.csv).
   Salve em `dados/P8/`. O nome que o Google dá (`Banco_P8 - Questoes.csv`) já é reconhecido.
4. **Rodar o script.**
   - No computador: `python montar.py --periodo 8`
   - No Colab: suba esta pasta para o Drive em `BancoQuestoes/app`, abra `colab/montar_banco.ipynb` no Colab e rode as células.
5. **Ler o `saida/P8/A_CONFERIR.md`.** Erros tiram a linha do app. Avisos deixam a linha no app, marcada como "não conferida".
6. **Publicar `saida/index.html`** (veja abaixo).

Para outro período, repita com `dados/P7/` e `python montar.py --periodo 7`. O app passa a mostrar um seletor de período.

### O que o script confere

| Problema | O que acontece |
| --- | --- |
| id vazio ou repetido (também entre períodos) | linha fica fora do app |
| tipo ou selo fora do menu, disciplina, tema ou enunciado vazios | linha fica fora do app |
| fechada sem gabarito, gabarito que não é a–e ou aponta para alternativa vazia | linha fica fora do app |
| origem, dificuldade ou status fora do menu; tema que não está na aba Temas | aviso |
| justificativa vazia | vira A_CONFERIR |
| selo DERIVADO sem fonte | vira A_CONFERIR |
| selo RESPOSTA_ALUNO marcada como VALIDADA | vira A_CONFERIR |
| VALIDADA sem revisor, ou revisor igual ao responsável | vira A_CONFERIR |
| questão com imagem (`[questão com imagem, ...]`) | vira A_CONFERIR |
| discursiva sem resposta-modelo | vira A_CONFERIR |

Grafias como "Já caiu", "média" ou "B)" são aceitas e corrigidas sozinhas.

## O que o app faz

- Navegação disciplina > tema, com a contagem de questões ao lado
- Filtros: período, disciplina, tema, já caiu ou nova, dificuldade, selo, "só as que errei", "só as não respondidas" e "esconder não conferidas"
- **Estudo:** uma questão por vez; depois de responder, mostra a justificativa, o selo e a fonte
- **Simulado:** sorteia 5, 10, 20 ou mais questões, com cronômetro ou tempo limite; no fim, mostra acertos por tema e a revisão das que você errou
- **Flashcards:** virar, marcar "sabia" ou "não sabia", esconder os que já sabia, ir para a questão de origem
- **Discursivas:** espaço para escrever (fica salvo) e resposta-modelo que se revela com um clique
- Aviso "não conferida" nas questões A_CONFERIR
- Link "reportar erro" em cada questão, se o `form_url` estiver configurado
- Progresso salvo no navegador; funciona offline e no celular
- Atalhos de teclado: A–E para responder, setas para navegar, espaço para virar o card

### Ligar o "reportar erro"

1. Crie um Google Formulário com dois campos: "id da questão" e "o que está errado".
2. No formulário, menu ⋮ > Gerar link pré-preenchido. Escreva `{id}` no campo do id e copie o link.
3. Cole em `config.json`, no campo `form_url`. Por exemplo:
   `"form_url": "https://docs.google.com/forms/d/e/XXXX/viewform?usp=pp_url&entry.123456={id}"`
4. Rode o `montar.py` de novo.

## Publicar para a turma

| Opção | Quem acessa | Como |
| --- | --- | --- |
| Google Apps Script | só contas do domínio da faculdade | siga as instruções no topo de `apps_script/Code.gs` |
| Netlify Drop | quem tiver o link | crie uma pasta só com o `index.html` e arraste em [app.netlify.com/drop](https://app.netlify.com/drop) |
| GitHub Pages | quem tiver o link, e o repositório fica público | não recomendado para as provas |

O `index.html` já sai com `<meta name="robots" content="noindex">`, que pede aos buscadores para não indexar a página.

## Privacidade

As provas são material dos professores. Por isso, `dados/` e `saida/` estão no `.gitignore`: a planilha real da turma e o app gerado com ela não sobem para o GitHub. Só os dados de exemplo e o app de demonstração ficam no repositório.

O progresso de cada aluno fica só no navegador dele. Nada é enviado para servidor nenhum.
