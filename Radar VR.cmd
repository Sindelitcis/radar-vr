@echo off
REM Abre o painel sem console quando o pythonw.exe existe.
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "src\painel.py"
) else (
    start "" ".venv\Scripts\python.exe" "src\painel.py"
)
