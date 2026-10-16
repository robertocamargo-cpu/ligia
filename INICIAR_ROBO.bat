@echo off
title Robô de Impressão de Pedidos ERP ADMSIS
cd /d "%~dp0"

:: Garante uso do executável correto do Python (py ou python)
set "PY_CMD=python"
where py >nul 2>nul && set "PY_CMD=py"

echo ========================================================
echo   INICIANDO ROBO DE IMPRESSAO AUTOMATICA (ERP ADMSIS)
echo ========================================================
%PY_CMD% robot_job.py
pause
