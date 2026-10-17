@echo off
REM Abre o microsservico e o n8n, cada um na sua janela, e o editor no navegador.
cd /d "%~dp0"
echo.
echo   Radar VR - fluxo do n8n
echo.
echo   [E] Ensaio  o fluxo roda inteiro, mas nenhuma mensagem e enviada
echo   [R] Real    o e-mail e o Telegram chegam de verdade
echo.
choice /c ER /n /m "  Escolha E ou R: "
set MODO=teste
if errorlevel 2 set MODO=

curl -s -o nul http://127.0.0.1:8765/saude
if errorlevel 1 (
    start "Radar VR - microsservico" cmd /k executar_servico.cmd %MODO%
) else (
    echo   O microsservico ja esta aberto. Para trocar de modo, feche a janela dele e rode de novo.
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
