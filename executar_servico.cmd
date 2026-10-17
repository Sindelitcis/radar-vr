@echo off
REM Sobe o microsservico do Radar VR em http://127.0.0.1:8765
REM   executar_servico.cmd          envios reais
REM   executar_servico.cmd teste    modo DRY_RUN: nenhuma mensagem sai da maquina
cd /d "%~dp0"
if /i "%~1"=="teste" set RADAR_DRY_RUN=1
"%~dp0.venv\Scripts\python.exe" "%~dp0src\servico.py"
