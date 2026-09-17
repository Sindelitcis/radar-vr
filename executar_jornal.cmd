@echo off
REM Executa uma edicao do jornal. Chamado pelo no Execute Command do n8n.
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0src\jornal.py"
