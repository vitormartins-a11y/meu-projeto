/**
 * Publica o Banco de Questões como Web App do Google Apps Script,
 * com acesso restrito às contas do domínio da faculdade.
 *
 * 1. Em script.google.com, crie um projeto e cole este arquivo em Code.gs.
 * 2. Arquivo > Novo > HTML, com o nome "index" (sem .html).
 *    Apague o conteúdo e cole o saida/index.html inteiro gerado pelo montar.py.
 * 3. Implantar > Nova implantação > Tipo: App da Web.
 *    Executar como: Eu. Quem pode acessar: Qualquer pessoa em <domínio da faculdade>.
 * 4. Copie o link e divulgue no grupo da turma.
 *
 * Para atualizar: cole o novo index.html por cima e faça Implantar > Gerenciar
 * implantações > Editar > Nova versão. O link continua o mesmo.
 */
function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle('Banco de Questões')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}
