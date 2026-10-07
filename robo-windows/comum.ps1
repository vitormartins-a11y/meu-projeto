# Usado pelos outros scripts: abre as chaves cifradas e prepara o ambiente do Python.
$env:PATH = "$PSScriptRoot\ffmpeg;" + $env:PATH
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$PSScriptRoot\modelos"                      # modelo do Whisper (baixado uma vez, uns 800 MB)
$env:PLAYWRIGHT_BROWSERS_PATH = "$PSScriptRoot\navegador"
$Python = "$PSScriptRoot\venv\Scripts\python.exe"
function Abrir-Segredo($cifrado) {
  $ss = ConvertTo-SecureString $cifrado
  $p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
}
function Carregar-Chaves {
  $c = Import-Clixml (Join-Path $PSScriptRoot 'chaves.xml')
  $env:SUPABASE_URL = $c.SUPABASE_URL
  $env:SUPABASE_SERVICE_KEY = Abrir-Segredo $c.SUPABASE_SERVICE_KEY
  $env:GROQ_API_KEY = Abrir-Segredo $c.GROQ_API_KEY
  $env:GOOGLE_SA_KEY = Abrir-Segredo $c.GOOGLE_SA_KEY
}
# um arquivo de registro por dia; os de mais de 14 dias são apagados
function Arquivo-Registro($nome) {
  $dir = Join-Path $PSScriptRoot 'registros'
  Get-ChildItem $dir -Filter '*.log' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | Remove-Item -Force -ErrorAction SilentlyContinue
  Join-Path $dir ("$nome-" + (Get-Date -Format 'yyyy-MM-dd') + '.log')
}
# O próprio Python grava cada linha no registro, na hora e com acentos (LOG_ARQUIVO). Aqui só sobra o que ele
# escrever antes de começar (ex.: falta de biblioteca), que vai para um arquivo à parte.
function Rodar-Python($registro, [string[]]$argumentos) {
  $env:LOG_ARQUIVO = $registro
  & $Python @argumentos 2> "$registro.erros.txt"
  if ((Test-Path "$registro.erros.txt") -and ((Get-Item "$registro.erros.txt").Length -eq 0)) { Remove-Item "$registro.erros.txt" -Force -ErrorAction SilentlyContinue }
}
