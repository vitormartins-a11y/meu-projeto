# Libera espaço no Supabase sem perder conteúdo: primeiro mede e mostra, e só muda algo se você confirmar.
$ErrorActionPreference = 'Continue'
. "$PSScriptRoot\comum.ps1"
$reg = Arquivo-Registro 'liberar-espaco'
try { Carregar-Chaves } catch { Write-Host "Não consegui abrir as chaves: $($_.Exception.Message). Rode o INSTALAR.bat de novo." -ForegroundColor Red; Read-Host 'Aperte Enter para fechar'; exit 1 }
$env:LOG_ARQUIVO = $reg
Write-Host 'Medindo o espaço (nada é mudado agora). Pode levar alguns minutos...' -ForegroundColor Cyan
& $Python "$PSScriptRoot\liberar_espaco.py" --medir
if ($LASTEXITCODE -ne 0) { Write-Host 'Não deu certo (veja acima). Mande um print desta janela.' -ForegroundColor Red; Read-Host 'Aperte Enter para fechar'; exit 1 }
Write-Host ''
# o robô para enquanto a limpeza mexe nas imagens (para os dois não mexerem na mesma página) e volta no fim
$tarefas = Get-ScheduledTask -TaskName 'Acervo da Turma*' -ErrorAction SilentlyContinue
$r = Read-Host 'PASSO 1 - Apagar o lixo e as fotos de página que o robô refaz? (S/N)'
if ($r -match '^[sS]') {
  $tarefas | Stop-ScheduledTask -ErrorAction SilentlyContinue
  & $Python "$PSScriptRoot\liberar_espaco.py" --apagar
  if ($LASTEXITCODE -ne 0) { Write-Host 'Parou no meio (veja acima). O que já saiu não faz falta; rode de novo para continuar.' -ForegroundColor Yellow }
  Write-Host ''
  $r2 = Read-Host 'PASSO 2 - Se ainda passar do limite, refazer menores as figuras mais pesadas até uns 950 MB? Pode levar algumas horas; deixe o computador ligado (S/N)'
  if ($r2 -match '^[sS]') {
    & $Python "$PSScriptRoot\liberar_espaco.py" --diminuir
    if ($LASTEXITCODE -ne 0) { Write-Host 'Parou no meio (veja acima). O que já foi refeito está certo; rode de novo para continuar.' -ForegroundColor Yellow }
  }
  # volta só a transcrição: o robô da IA fica parado até a versão econômica (ele é quem mais gasta o tráfego do Supabase)
  Start-ScheduledTask -TaskName 'Acervo da Turma - Transcrever aulas' -ErrorAction SilentlyContinue
} else { Write-Host 'Nada foi mudado.' }
Read-Host 'Aperte Enter para fechar'
