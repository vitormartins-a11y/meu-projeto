# Abre os registros de hoje (o que o robô fez) no Bloco de Notas.
$dir = Join-Path $PSScriptRoot 'registros'
$arqs = Get-ChildItem $dir -Filter '*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 2
if (-not $arqs) { Write-Host 'Ainda não há registros. O robô roda sozinho a cada 15 minutos (transcrição) e a cada hora (IA).'; Read-Host 'Aperte Enter para fechar'; exit }
foreach ($a in $arqs) { Start-Process notepad.exe $a.FullName }
Get-ScheduledTask -TaskName 'Acervo da Turma*' -ErrorAction SilentlyContinue | ForEach-Object {
  $i = $_ | Get-ScheduledTaskInfo
  Write-Host ("{0}: última rodada {1}, próxima {2}" -f $_.TaskName, $i.LastRunTime, $i.NextRunTime)
}
Read-Host 'Aperte Enter para fechar'
