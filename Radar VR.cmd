@echo off
REM Abre o painel do Radar VR sem janela de console.
REM Usa pythonw.exe (variante do Python sem terminal); se ela nao existir,
REM recai para o python normal, que funciona igual mas mostra o console.
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "src\painel.py"
) else (
    start "" ".venv\Scripts\python.exe" "src\painel.py"
)
