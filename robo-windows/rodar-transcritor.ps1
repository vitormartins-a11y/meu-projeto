# Rodada do transcritor (o Windows chama a cada 15 minutos). Sem nada na fila, termina em segundos.
$ErrorActionPreference = 'Continue'
. "$PSScriptRoot\comum.ps1"
$reg = Arquivo-Registro 'transcritor'
try { Carregar-Chaves } catch { Add-Content $reg "$(Get-Date -Format 'dd/MM HH:mm') ERRO ao abrir as chaves: $($_.Exception.Message). Rode o INSTALAR.bat de novo." -Encoding UTF8; exit 1 }
$env:ROBO = 'PC'
$env:TEMPO_MAX = '14400'                                     # no máximo 4 horas por rodada
Add-Content $reg "===== $(Get-Date -Format 'dd/MM HH:mm') rodada do transcritor =====" -Encoding UTF8
Rodar-Python $reg @("$PSScriptRoot\transcritor.py")
