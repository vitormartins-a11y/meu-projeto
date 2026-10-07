# Instalador do robô do Acervo da Turma no Windows (transcrição das aulas + organização pela IA).
# Instala tudo na pasta do usuário (não precisa ser administrador do computador) e agenda:
#   - transcrição: a cada 15 minutos;   - robô da IA: a cada 1 hora.
# Pode rodar de novo quando quiser (para atualizar ou trocar as chaves): o que já está instalado é reaproveitado.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'          # deixa os downloads muito mais rápidos
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Host.UI.RawUI.WindowTitle = 'Acervo da Turma - instalação do robô'
$aqui = $PSScriptRoot
$pasta = Join-Path $env:LOCALAPPDATA 'AcervoTranscritor'
function Titulo($t) { Write-Host ''; Write-Host "== $t" -ForegroundColor Cyan }
function Ok($t) { Write-Host "   $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "   $t" -ForegroundColor Yellow }

try {
  Write-Host 'Robô do Acervo da Turma - instalação' -ForegroundColor White
  Write-Host 'Isto leva de 5 a 15 minutos (depende da internet). Não feche esta janela.'
  New-Item -ItemType Directory -Force -Path $pasta, "$pasta\registros", "$pasta\modelos" | Out-Null

  # ---------------------------------------------------------------- 1. Python
  Titulo '1 de 6: Python'
  function Achar-Python {
    foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:ProgramFiles\Python312\python.exe")) { if (Test-Path $c) { return $c } }
    return $null
  }
  $python = Achar-Python
  if (-not $python) {
    Aviso 'Baixando o Python 3.12 (uns 25 MB)...'
    $inst = Join-Path $env:TEMP 'python-3.12.7-amd64.exe'
    Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile $inst -UseBasicParsing
    Aviso 'Instalando o Python...'
    Start-Process $inst -ArgumentList '/quiet InstallAllUsers=0 PrependPath=0 Include_test=0 Include_launcher=0' -Wait
    Remove-Item $inst -Force -ErrorAction SilentlyContinue
    $python = Achar-Python
    if (-not $python) { throw 'Não consegui instalar o Python. Instale o Python 3.12 pelo site python.org e rode este instalador de novo.' }
  }
  Ok "Python pronto ($python)"

  # ---------------------------------------------------------------- 2. ffmpeg
  Titulo '2 de 6: ffmpeg (separa o áudio e tira os prints dos vídeos)'
  $ff = Join-Path $pasta 'ffmpeg'
  if (-not (Test-Path "$ff\ffmpeg.exe")) {
    Aviso 'Baixando o ffmpeg (uns 90 MB)...'
    $zip = Join-Path $env:TEMP 'ffmpeg-acervo.zip'; $tmp = Join-Path $env:TEMP 'ffmpeg-acervo'
    Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $zip -UseBasicParsing
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive $zip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Force -Path $ff | Out-Null
    Get-ChildItem $tmp -Recurse -Include 'ffmpeg.exe', 'ffprobe.exe' | Copy-Item -Destination $ff -Force
    Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path "$ff\ffmpeg.exe")) { throw 'Não consegui instalar o ffmpeg.' }
  }
  Ok 'ffmpeg pronto'

  # ---------------------------------------------------------------- 3. programas e bibliotecas
  Titulo '3 de 6: programas do robô'
  foreach ($a in 'transcritor.py', 'robo_ia.py', 'requirements.txt', 'comum.ps1', 'rodar-transcritor.ps1', 'rodar-robo.ps1', 'desinstalar.ps1', 'ver-registro.ps1') {
    Copy-Item (Join-Path $aqui $a) -Destination $pasta -Force
  }
  $vpy = "$pasta\venv\Scripts\python.exe"
  if (-not (Test-Path $vpy)) { & $python -m venv "$pasta\venv"; if ($LASTEXITCODE -ne 0) { throw 'Não consegui preparar o Python.' } }
  Aviso 'Instalando as bibliotecas (pode demorar alguns minutos)...'
  & $vpy -m pip install --upgrade pip --quiet --disable-pip-version-check
  & $vpy -m pip install -r "$pasta\requirements.txt" --quiet --disable-pip-version-check
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as bibliotecas do Python. Confira a internet e rode o instalador de novo.' }
  Aviso 'Instalando o navegador do robô da IA (uns 150 MB)...'
  $env:PLAYWRIGHT_BROWSERS_PATH = "$pasta\navegador"
  & $vpy -m playwright install chromium
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o navegador do robô. Rode o instalador de novo.' }
  Ok 'Programas, bibliotecas e navegador prontos'

  # ---------------------------------------------------------------- 4. chaves
  Titulo '4 de 6: chaves'
  $cfg = Join-Path $pasta 'chaves.xml'
  $usarAntigas = $false
  if (Test-Path $cfg) { $usarAntigas = (Read-Host '   Já existem chaves guardadas neste computador. Usar as mesmas? (S/N)') -match '^[sS]' }
  if (-not $usarAntigas) {
    Write-Host '   Tenha em mãos as chaves do guia (Supabase, Groq e o arquivo .json do Google).'
    $url = (Read-Host '   Cole o endereço do Supabase (Project URL, começa com https://) e aperte Enter').Trim().TrimEnd('/')
    if ($url -notmatch '^https://') { throw 'O endereço do Supabase precisa começar com https://' }
    $svc = Read-Host '   Cole a chave service_role do Supabase (ela não aparece enquanto você cola) e aperte Enter' -AsSecureString
    $groq = Read-Host '   Cole a chave do Groq (começa com gsk_; não aparece enquanto você cola) e aperte Enter' -AsSecureString
    Write-Host '   Agora escolha o arquivo .json da conta de serviço do Google (uma janela vai abrir; ela pode ficar atrás desta).'
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = 'Escolha o arquivo .json da conta de serviço do Google'
    $dlg.Filter = 'Arquivo JSON (*.json)|*.json'
    $dlg.InitialDirectory = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads'
    if ($dlg.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw 'Nenhum arquivo .json foi escolhido.' }
    $json = Get-Content $dlg.FileName -Raw -Encoding UTF8
    $j = $json | ConvertFrom-Json
    if (-not $j.client_email -or -not $j.private_key) { throw 'Esse arquivo não é o da conta de serviço do Google (falta client_email ou private_key).' }
    # cifradas pelo Windows (DPAPI): só a sua conta do Windows, neste computador, consegue abrir
    [pscustomobject]@{
      SUPABASE_URL         = $url
      SUPABASE_SERVICE_KEY = ($svc | ConvertFrom-SecureString)
      GROQ_API_KEY         = ($groq | ConvertFrom-SecureString)
      GOOGLE_SA_KEY        = (ConvertTo-SecureString $json -AsPlainText -Force | ConvertFrom-SecureString)
      GOOGLE_EMAIL         = $j.client_email
    } | Export-Clixml $cfg
    Ok "Chaves guardadas e cifradas. Conta do Google: $($j.client_email)"
  }

  # ---------------------------------------------------------------- 5. teste
  Titulo '5 de 6: conferindo as chaves'
  . "$pasta\comum.ps1"
  Carregar-Chaves
  & $vpy "$pasta\transcritor.py" --testar
  if ($LASTEXITCODE -ne 0) { throw 'Alguma chave não funcionou (veja o ERRO acima). Rode o instalador de novo e cole a chave certa.' }
  Ok 'Tudo conferido'

  # ---------------------------------------------------------------- 6. agendamento
  Titulo '6 de 6: agendamento automático'
  function Agendar($nome, $script, $minutos, $descricao) {
    $acao = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$pasta\$script`""
    try { $gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $minutos) -RepetitionDuration (New-TimeSpan -Days 3650) }
    catch { $gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $minutos) }
    $conf = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 5)
    Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $conf -Description $descricao -Force | Out-Null
  }
  Agendar 'Acervo da Turma - Transcrever aulas' 'rodar-transcritor.ps1' 15 'Transcreve os áudios e vídeos da fila do Acervo da Turma (a cada 15 minutos, quando o computador está ligado).'
  Agendar 'Acervo da Turma - Robô da IA' 'rodar-robo.ps1' 60 'Organiza com a IA os temas da fila do Acervo da Turma (a cada hora, quando o computador está ligado).'
  Start-ScheduledTask -TaskName 'Acervo da Turma - Transcrever aulas'
  Start-ScheduledTask -TaskName 'Acervo da Turma - Robô da IA'
  Ok 'Agendado: transcrição a cada 15 minutos e robô da IA a cada hora. A primeira rodada já começou.'

  Write-Host ''
  Write-Host 'PRONTO! O robô está instalado.' -ForegroundColor Green
  Write-Host 'Ele trabalha sozinho sempre que o computador estiver ligado e acordado. Você pode usar o computador normalmente.'
  Write-Host 'Para ver o que ele está fazendo: VER-REGISTRO.bat. Para desligar de vez: DESINSTALAR.bat.'
}
catch {
  Write-Host ''
  Write-Host "Não deu certo: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host 'Mande um print desta janela para quem está te ajudando.' -ForegroundColor Yellow
}
Write-Host ''
Read-Host 'Aperte Enter para fechar'
