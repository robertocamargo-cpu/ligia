@echo off
title Teste Simulação (Dry Run) - Robô ERP
cd /d "%~dp0"

:: Garante uso do executável correto do Python (py ou python)
set "PY_CMD=python"
where py >nul 2>nul && set "PY_CMD=py"

echo ========================================================
echo   TESTE DE 1 CICLO EM MODO SIMULACAO (SEM IMPRIMIR)
echo ========================================================
%PY_CMD% robot_job.py --once --dry-run
pause
