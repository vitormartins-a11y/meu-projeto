# Desliga o robô: tira o agendamento e apaga a pasta (com as chaves cifradas). O site e os dados não são afetados.
$pasta = Join-Path $env:LOCALAPPDATA 'AcervoTranscritor'
if ((Read-Host 'Desligar o robô deste computador e apagar as chaves guardadas nele? (S/N)') -notmatch '^[sS]') { exit }
Get-ScheduledTask -TaskName 'Acervo da Turma*' -ErrorAction SilentlyContinue | ForEach-Object { Stop-ScheduledTask -TaskName $_.TaskName -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false }
Start-Sleep -Seconds 2
Remove-Item $pasta -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'Pronto: o robô foi desligado e as chaves foram apagadas deste computador.' -ForegroundColor Green
Read-Host 'Aperte Enter para fechar'
