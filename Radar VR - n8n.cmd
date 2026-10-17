@echo off
REM Abre o microsservico, o n8n e o editor.
cd /d "%~dp0"
echo.
echo   Radar VR
echo.
echo   [E] Ensaio
echo   [R] Real
echo.
choice /c ER /n /m "  Escolha E ou R: "
set MODO=teste
if errorlevel 2 set MODO=

curl -s -o nul http://127.0.0.1:8765/saude
if errorlevel 1 (
    start "Radar VR - microsservico" cmd /k executar_servico.cmd %MODO%
) else (
    echo   O microsservico ja esta aberto.
)

curl -s -o nul http://localhost:5678/healthz
if errorlevel 1 start "Radar VR - n8n" cmd /k executar_n8n.cmd

REM /healthz responde antes do editor estar pronto; a pagina inicial so
REM deixa de devolver 404 quando a interface terminou de carregar.
echo   Aguardando o n8n subir...
:espera
timeout /t 2 /nobreak >nul
curl -sf -o nul http://localhost:5678/
if errorlevel 1 goto :espera
start "" http://localhost:5678
