# Desliga o robô: tira o agendamento e apaga a pasta (com as chaves cifradas). O site e os dados não são afetados.
$pasta = Join-Path $env:LOCALAPPDATA 'AcervoTranscritor'
if ((Read-Host 'Desligar o robô deste computador e apagar as chaves guardadas nele? (S/N)') -notmatch '^[sS]') { exit }
Get-ScheduledTask -TaskName 'Acervo da Turma*' -ErrorAction SilentlyContinue | ForEach-Object { Stop-ScheduledTask -TaskName $_.TaskName -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false }
# (o Python e o navegador do robô rodando seguravam arquivos, e a pasta ficava pela metade)
Get-Process python, pythonw, chrome, chrome-headless-shell, ffmpeg -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($pasta, [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Remove-Item $pasta -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path $pasta) { Start-Sleep -Seconds 3; Remove-Item $pasta -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path $pasta) { Write-Host "Alguns arquivos estavam em uso e ficaram em $pasta. Reinicie o computador e rode o DESINSTALAR.bat de novo (ou apague essa pasta)." -ForegroundColor Yellow }
Write-Host 'Pronto: o robô foi desligado e as chaves foram apagadas deste computador.' -ForegroundColor Green
Read-Host 'Aperte Enter para fechar'
