@echo off
title Assistente LigIA (ERP ADMSIS)
cd /d "%~dp0"

echo ========================================================
echo         ASSISTENTE LIGIA - IMPRESSAO AUTOMATICA
echo ========================================================
echo  Status: Em execucao (Checagem a cada 2 minutos)
echo  Para pausar ou encerrar, basta fechar esta janela.
echo ========================================================
echo.

set "PY_CMD=python"
where py >nul 2>nul && set "PY_CMD=py"

%PY_CMD% robot_job.py
pause
