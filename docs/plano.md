# Banco de Questões de Medicina — plano sem IA e com custo zero

> Cópia do documento criado no Claude em 03/10/2026, na conversa "Aplicativo sem IA usando códigos".
> Original: https://claude.ai/code/artifact/88004757-19ee-48d7-8031-102aa0e179fb

## Resumo

O banco de questões pode sair com **custo zero**. A turma transcreve as provas numa planilha do Google, um script converte a planilha nos dados do app, e o app é uma página HTML hospedada de graça. Nenhuma etapa usa IA e nenhum aluno paga nada para usar.

Em relação ao plano original, o trabalho de transcrever, conferir gabarito e escrever justificativa passa a ser da turma, dividido por matéria. As questões novas ficam para uma segunda versão.

Esforço estimado: 10 a 15 minutos por questão, já com justificativa. Com 300 questões, são 50 a 75 horas no total, ou 5 a 8 horas por pessoa num grupo de 10.

## Ferramentas e custos

Todas as ferramentas abaixo são gratuitas. O custo total do projeto é R$ 0.

| Etapa | Ferramenta | Custo |
| --- | --- | --- |
| Guardar as provas | Google Drive (conta pessoal, 15 GB) | R$ 0 |
| Ler o texto das provas (OCR) | Google Docs ("Abrir com > Documentos Google") e Google Lens no celular | R$ 0 |
| Banco de questões | Google Planilhas | R$ 0 |
| Converter a planilha nos dados do app | Script em Python, rodado no Google Colab (navegador, sem instalar nada) | R$ 0 |
| App | Uma página HTML (index.html) | R$ 0 |
| Hospedagem | Netlify, Google Apps Script ou GitHub Pages | R$ 0 |
| Flashcards no celular | Anki (AnkiDroid e AnkiWeb são grátis; o app de iPhone é pago, mas os flashcards também ficam no próprio app) | R$ 0 |
| Receber relatos de erro | Google Formulários | R$ 0 |

## Equipe e divisão de tarefas

O trabalho é dividido por matéria, e ninguém valida a própria questão.

| Papel | Pessoas | O que faz |
| --- | --- | --- |
| Coordenador | 1 | Cria a pasta e a planilha, distribui as provas, roda o script e publica o app |
| Responsável por matéria | 1 a 2 por matéria | Transcreve, define o gabarito, escreve justificativas e flashcards da sua matéria |
| Revisor | 1 por matéria, de outro grupo | Confere as questões de uma matéria que não é a sua e marca como VALIDADA |
| Programador | 1 (pode ser o coordenador) | Escreve o script e o app uma única vez |

## Passo 1 — Organizar o acervo

O passo termina quando toda prova tem uma linha no inventário e um responsável.

1. Criar no Drive do coordenador a pasta `BancoQuestoes`, com as subpastas `origem`, `P8` e `app`.
2. Copiar as provas do Drive do acervo para `origem`, uma subpasta por matéria.
3. Renomear os arquivos num padrão único: `Disciplina_Tema_Ano_Prova` (ex.: `Ginecologia_Amenorreia_2024_P1.pdf`). Ano desconhecido vira `sem-ano`.
4. Preencher a aba Inventário da planilha (passo 2), com uma linha por arquivo: nome, disciplina, número de questões, se tem gabarito oficial, legibilidade (boa ou ruim), responsável e situação.
5. Começar pelos cadernos já compilados (`Caderno_Questoes_<Disciplina>_8P.pdf`). As questões deles já estão transcritas, então basta copiar para a planilha.

## Passo 2 — Criar a planilha-banco

Um arquivo do Google Planilhas por período (`Banco_P8`) substitui o JSON como fonte da verdade. Ele tem quatro abas: Questoes, Flashcards, Temas e Inventario.

Aba **Questoes**, uma linha por questão:

| Coluna | O que vai | Valores permitidos |
| --- | --- | --- |
| id | Período, sigla da matéria e número (ex.: `P8-GIN-001`) | Único; nunca muda depois de publicado |
| disciplina | Nome da matéria | Lista da aba Temas |
| tema | Tema dentro da matéria | Lista da aba Temas |
| subtema | Detalhe do tema | Livre |
| origem | De onde veio a questão | JA_CAIU, NOVA |
| tipo | Formato | FECHADA, DISCURSIVA |
| enunciado | Texto literal da prova; trecho ilegível entre [colchetes] | Livre |
| alt_a a alt_e | Uma coluna por alternativa; vazia se não existir | Livre |
| gabarito | Letra correta (vazio nas discursivas) | a, b, c, d, e |
| resposta_modelo | Só nas discursivas | Livre |
| selo | Origem do gabarito (passo 4) | OFICIAL, DERIVADO, RESPOSTA_ALUNO, AUTORAL |
| justificativa | Por que a correta está certa e cada outra está errada | Obrigatória |
| fonte | Diretriz, livro e página, ou link | Obrigatória quando o selo é DERIVADO |
| dificuldade | Nível | FACIL, MEDIA, DIFICIL |
| arquivo_origem | Nome do arquivo da prova | Livre |
| ano | Ano da prova | Número ou vazio |
| status | Situação da questão | A_CONFERIR, VALIDADA |
| responsavel | Quem preencheu | Nome |
| revisor | Quem conferiu | Nome |

Como montar:

1. Nas colunas com valores fixos, criar um menu suspenso: selecionar a coluna, depois Dados > Validação de dados > Menu suspenso. Isso evita grafias diferentes, como "Amenorreia" e "amenorréia".
2. Na aba **Temas**, listar as duplas disciplina e tema, partindo do `INDICE POR TEMA.txt`. Os menus de disciplina e tema leem dessa aba.
3. Congelar a primeira linha e ativar a quebra de texto, para os enunciados longos ficarem legíveis.
4. Salvar uma cópia vazia como modelo (`Banco_MODELO`), para reaproveitar nos outros períodos.

## Passo 3 — Transcrever as questões

O OCR do Google é gratuito e lê português, mas erra. Toda transcrição é conferida contra a imagem original.

1. **PDF ou foto, no computador:** no Drive, clicar com o botão direito no arquivo e escolher Abrir com > Documentos Google. O Google cria um documento com a imagem e, embaixo, o texto reconhecido. Em PDFs longos ele costuma ler só as primeiras páginas, então vale dividir o arquivo antes.
2. **Foto, no celular:** abrir no Google Lens, tocar em Texto e depois em Copiar.
3. Colar na planilha e corrigir palavra por palavra. Atenção redobrada em números, doses e unidades: o OCR troca "0,5 mg" por "05 mg" com facilidade.
4. Trecho ilegível vai entre colchetes: `[ilegível]` ou `[palavra provável?]`. Nunca completar de cabeça.
5. Questão que depende de imagem (ECG, foto de lesão, gráfico): escrever `[questão com imagem, ver arquivo de origem]` e deixar o status em A_CONFERIR. As imagens entram numa versão futura.
6. Atualizar a situação do arquivo na aba Inventario.

## Passo 4 — Gabarito, selo e justificativa

O selo diz a quem estuda de onde veio a resposta. Ele é obrigatório em toda questão.

1. A prova tem gabarito oficial: usar esse gabarito, com selo **OFICIAL**.
2. Não tem: pesquisar a resposta em diretriz, consenso ou livro-texto e registrar a fonte (livro e página, ou link). Selo **DERIVADO**.
3. Só existe a marcação de um aluno: selo **RESPOSTA_ALUNO** e status A_CONFERIR até alguém confirmar com fonte.
4. Questão escrita pela turma (versão 2): selo **AUTORAL**.

A justificativa tem de 2 a 5 frases e segue um modelo fixo: "Correta: (b), porque... Erradas: (a) ...; (c) ...; (d) ...". Questão sem justificativa fica em A_CONFERIR.

Fontes que servem: diretrizes das sociedades médicas, protocolos do Ministério da Saúde e os livros-texto indicados pelos professores. Se a fonte discordar do gabarito oficial, o oficial fica na planilha, a divergência é explicada na justificativa e a questão vai para a lista A_CONFERIR.

## Passo 5 — Revisão cruzada

Uma questão só vira VALIDADA depois que alguém de outro grupo confere. O revisor checa cinco pontos:

- [ ] O enunciado bate com a imagem original, inclusive números e unidades
- [ ] O gabarito está certo e o selo corresponde à origem da resposta
- [ ] A justificativa explica a correta e cada alternativa errada
- [ ] A fonte existe e sustenta a resposta
- [ ] Disciplina, tema e demais campos usam os valores dos menus

Se estiver tudo certo, o revisor muda o status para VALIDADA e escreve o próprio nome na coluna revisor. Se houver problema, deixa um comentário na célula (Inserir > Comentário) e mantém A_CONFERIR.

Vale pedir a um monitor ou professor que revise uma amostra de umas 10 questões por matéria. Isso pega erros que a turma repete sem perceber.

No app, questões A_CONFERIR aparecem com o aviso "não conferida" e podem ser escondidas pelo filtro.

## Passo 6 — Flashcards

Cada card carrega um fato só. Se o verso tem três informações, viram três cards.

A aba **Flashcards** tem as colunas id, disciplina, tema, frente, verso e questao_origem. O mais prático é escrever 2 a 4 cards logo depois da justificativa de cada questão, porque os fatos já estão ali.

| Frente | Verso | Avaliação |
| --- | --- | --- |
| Primeiro exame na investigação de amenorreia secundária? | Beta-hCG | Bom: um fato |
| Como investigar amenorreia secundária? | Beta-hCG, TSH, prolactina e FSH | Ruim: quatro fatos, vira quatro cards |

O script do passo 7 transforma essa aba num CSV com separador `;`, que o Anki importa direto.

## Passo 7 — Script conversor e app

O código é escrito uma vez e depois só é rodado. Nada nele fica preso ao 8º período: disciplinas e temas são lidos da planilha.

**O ciclo de atualização:**

1. Baixar as abas Questoes e Flashcards: Arquivo > Fazer download > CSV.
2. Rodar `montar.py --periodo 8` no Google Colab, enviando os dois CSVs.
3. O script confere cada linha: valor fora dos menus, fechada sem gabarito, gabarito apontando para alternativa vazia, justificativa vazia e id repetido.
4. O script gera `banco_p8.json`, `flashcards_p8.json`, `flashcards_p8.csv` (para o Anki) e `A_CONFERIR.md` com a lista de problemas encontrados.
5. O script embute os dados de todos os períodos dentro do `index.html`, num arquivo único. Isso evita um bloqueio comum: o navegador não deixa um HTML aberto do celular carregar um JSON separado.

**O que o app faz** (igual ao plano original):

- Navegação disciplina > tema > questões, com a contagem visível em cada tema
- Filtros combináveis: período, disciplina, tema, já caiu ou nova, dificuldade, selo e "só as que errei"
- Modo Estudo: uma questão por vez, com justificativa depois de responder
- Modo Simulado: bloco de N questões com cronômetro e relatório de acertos por tema no fim
- Modo Flashcards: virar o card e marcar "sabia" ou "não sabia"
- Modo Discursivas: espaço para escrever e resposta-modelo revelável
- Selo do gabarito ao lado de cada resposta, em uma palavra
- Progresso salvo no próprio navegador, com uma linha avisando que limpar os dados do navegador apaga o histórico
- Link "reportar erro" em cada questão (passo 9)

Quem programa precisa saber o básico de Python e de HTML com JavaScript.

## Passo 8 — Publicar para a turma

As provas são material dos professores, então o acesso deve ficar restrito à turma. As três opções abaixo são gratuitas.

| Opção | Quem acessa | Dificuldade | Observação |
| --- | --- | --- | --- |
| Google Apps Script (Web App) | Só contas com o e-mail da faculdade | Média | Exige que o e-mail da faculdade seja Google; é a opção mais restrita |
| Netlify Drop (arrastar a pasta em app.netlify.com/drop) | Quem tiver o link | Fácil | Os arquivos não ficam expostos num repositório |
| GitHub Pages | Quem tiver o link | Fácil | No plano grátis o repositório fica público, então todo o banco fica visível |

Recomendação: se o e-mail da faculdade for Google, usar o Apps Script restrito ao domínio. Se não for, usar o Netlify e divulgar o link só no grupo da turma.

Nas duas opções com link, colocar no `index.html` a marcação que pede ao Google para não indexar a página (`<meta name="robots" content="noindex">`).

## Passo 9 — Manutenção e outros períodos

Corrigir e expandir o banco usa o mesmo ciclo do passo 7, sem mexer no código.

- **Relatos de erro:** um Google Formulário com dois campos, id da questão e o que está errado. O link fica em cada questão do app, e as respostas caem numa planilha que o coordenador acompanha.
- **Correção:** o coordenador corrige na planilha, roda o script e republica. O progresso dos alunos é mantido desde que os ids nunca mudem.
- **Outro período:** copiar `Banco_MODELO` como `Banco_P7`, repetir os passos 1 a 6 e rodar `montar.py --periodo 7`. O app ganha o novo período no filtro sozinho.
- **Questões novas (versão 2):** escritas por monitores ou alunos, com origem NOVA e selo AUTORAL, passando pela mesma revisão cruzada.

## Cronograma sugerido

Em 7 semanas a turma tem um piloto na 5ª e o app completo na 7ª.

| Atividade | Semanas | Quem |
| --- | --- | --- |
| Preparar acervo | 1 | coordenador |
| Transcrever e gabaritar | 2 a 5 | turma, por matéria |
| Script e app | 2 a 4 | programador |
| Revisão cruzada | 4 a 6 | outro grupo |
| **Piloto com 1 matéria** | fim da 5 | app pronto + 1 matéria validada |
| **Lançamento completo** | fim da 7 | todas as matérias |

O piloto depende do script e do app prontos e de ao menos uma matéria validada. Lançar cada matéria assim que fica pronta mantém a turma engajada e revela problemas cedo.

## Regras que não mudam

- **Nunca inventar enunciado.** Questão que já caiu é transcrita, não reescrita; o ilegível vai entre colchetes.
- **Nunca apresentar gabarito derivado como oficial.** O selo é obrigatório.
- **Toda questão com justificativa.** Sem ela, a questão fica A_CONFERIR.
- **Ninguém valida a própria questão.**
- **Ids nunca mudam depois de publicados**, senão o progresso dos alunos se perde.
- **Acesso restrito à turma.** O material é acervo de estudo dos alunos e deve continuar assim.
