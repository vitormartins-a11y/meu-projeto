# Libera espaço no Supabase sem perder conteúdo: primeiro mede e mostra, e só apaga se você confirmar.
$ErrorActionPreference = 'Continue'
. "$PSScriptRoot\comum.ps1"
$reg = Arquivo-Registro 'liberar-espaco'
try { Carregar-Chaves } catch { Write-Host "Não consegui abrir as chaves: $($_.Exception.Message). Rode o INSTALAR.bat de novo." -ForegroundColor Red; Read-Host 'Aperte Enter para fechar'; exit 1 }
$env:LOG_ARQUIVO = $reg
Write-Host 'Medindo o espaço (nada é apagado agora). Pode levar alguns minutos...' -ForegroundColor Cyan
& $Python "$PSScriptRoot\liberar_espaco.py" --medir
if ($LASTEXITCODE -ne 0) { Write-Host 'Não deu certo (veja acima). Mande um print desta janela.' -ForegroundColor Red; Read-Host 'Aperte Enter para fechar'; exit 1 }
Write-Host ''
$r = Read-Host 'Apagar agora o lixo e as fotos de página que o robô refaz? (S/N)'
if ($r -match '^[sS]') {
  & $Python "$PSScriptRoot\liberar_espaco.py" --apagar
  if ($LASTEXITCODE -ne 0) { Write-Host 'Parou no meio (veja acima). O que já saiu não faz falta; rode de novo para continuar.' -ForegroundColor Yellow }
} else { Write-Host 'Nada foi apagado.' }
Read-Host 'Aperte Enter para fechar'
