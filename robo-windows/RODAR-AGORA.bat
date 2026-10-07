@echo off
title Acervo da Turma - rodar agora
powershell.exe -NoProfile -Command "Get-ScheduledTask -TaskName 'Acervo da Turma*' | Start-ScheduledTask; Write-Host 'O robo comecou a trabalhar agora. Veja o que ele faz em VER-REGISTRO.bat.'"
pause
