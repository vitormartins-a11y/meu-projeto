# Histórico do projeto

## O que veio da conversa "Aplicativo sem IA usando códigos"

O Claude Code não consegue ler o histórico de conversas do claude.ai: as mensagens e as imagens enviadas no chat não estão acessíveis daqui.
O que deu para trazer foram os dois materiais que a conversa publicou na conta:

| Material | Data | Onde está agora |
| --- | --- | --- |
| Documento "Banco de Questões de Medicina — plano sem IA e com custo zero" ([original](https://claude.ai/code/artifact/88004757-19ee-48d7-8031-102aa0e179fb)) | 03/10/2026 | [`docs/plano.md`](plano.md) |
| Prévia "Banco de Questões — Preview" ([original](https://claude.ai/artifact/5UTmGgNPZYkQvhPZFDM6wx)) | 24/09/2026 | [`docs/preview_original.html`](preview_original.html) |

Se houver outros arquivos ou imagens que só estão no chat (por exemplo, `INDICE POR TEMA.txt` ou os cadernos de questões), eles precisam ser baixados de lá e colocados nesta pasta à mão.

## Avaliação do que já estava feito

**O plano estava completo:** ferramentas e custos, equipe, passos 1 a 9, cronograma de 7 semanas e as regras do projeto.
Faltava pôr em prática o passo 7, o "Script conversor e app", que é a parte de código.

**A prévia era uma demonstração visual**, com 5 questões fixas no código. Comparada com o que o plano pede, faltava:

- o `montar.py`: ainda não existia script nenhum para ler a planilha, conferir as linhas e gerar o app;
- filtros de período e de selo, e a opção de esconder questões não conferidas;
- aviso "não conferida" nas questões A_CONFERIR;
- simulado com N questões sorteadas e cronômetro (a prévia usava sempre todas as questões, sem tempo);
- link "reportar erro";
- salvar o "sabia/não sabia" dos flashcards e o texto das discursivas;
- a marcação `noindex`.

A prévia também tinha dois defeitos que quebrariam com dados reais:

- o texto entrava no HTML sem tratamento, então um enunciado com `<` (como "PA < 90") quebrava a tela;
- os botões usavam `onclick="pickTema('...')"`, que quebra quando o nome do tema tem apóstrofo.

## O que foi feito nesta sessão (05/10/2026)

- `montar.py`: lê os CSVs da planilha e confere todas as regras do plano. Gera os JSONs, o CSV do Anki e o relatório `A_CONFERIR.md`. Depois monta um `index.html` único com todos os períodos.
- `app/template.html`: o app completo, com tudo o que o passo 7 lista, a partir do visual da prévia.
- Modelos de planilha, dados de exemplo e um app de demonstração (`demo/`).
- Caderno do Colab, publicação pelo Google Apps Script, testes automáticos e o README.
