@echo off
title Parar Assistente LigIA
cd /d "%~dp0"

echo ========================================================
echo         ENCERRANDO ASSISTENTE LIGIA...
echo ========================================================

powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*robot_job.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host 'Processo LigIA encerrado (PID: ' $_.ProcessId ')' }"

echo.
echo Concluido!
timeout /t 3

