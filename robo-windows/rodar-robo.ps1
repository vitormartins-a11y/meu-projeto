# Rodada do robô da IA (o Windows chama a cada hora). Sem tema na fila, termina sem abrir o navegador.
$ErrorActionPreference = 'Continue'
. "$PSScriptRoot\comum.ps1"
$reg = Arquivo-Registro 'robo-ia'
try { Carregar-Chaves } catch { Add-Content $reg "$(Get-Date -Format 'dd/MM HH:mm') ERRO ao abrir as chaves: $($_.Exception.Message). Rode o INSTALAR.bat de novo." -Encoding UTF8; exit 1 }
$env:APP_URL = 'https://acervodaturma.pages.dev'
$env:MINUTOS = '240'                                         # no máximo 4 horas por rodada
$env:SIMULTANEOS = '2'
Add-Content $reg "===== $(Get-Date -Format 'dd/MM HH:mm') rodada do robô da IA =====" -Encoding UTF8
$env:LOG_ARQUIVO = $reg
$checar = & $Python "$PSScriptRoot\robo_ia.py" --checar 2>$null
if (($checar -join ' ') -match 'esperando a IA: 0\b') { exit 0 }
Rodar-Python $reg @("$PSScriptRoot\robo_ia.py")
