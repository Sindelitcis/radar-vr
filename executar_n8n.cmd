@echo off
REM ============================================================================
REM  Radar VR - lancador do n8n
REM  AI Factory / Etapa 1 - PUCPR - Rafael Probst
REM
REM    executar_n8n.cmd ui     abre a interface em http://localhost:5678
REM    executar_n8n.cmd run    executa o fluxo sem abrir a interface
REM    executar_n8n.cmd import (re)importa o fluxo a partir do JSON
REM
REM  As variaveis abaixo existem porque o n8n v2 endureceu varios padroes.
REM  Cada uma esta explicada no docs/04_n8n.md.
REM ============================================================================

cd /d "%~dp0"

REM chave usada pelo n8n para cifrar credenciais no banco local
set N8N_ENCRYPTION_KEY=radar-vr-pucpr-etapa1

REM v2 desabilita Execute Command por padrao (roda comando arbitrario no host).
REM Reabilitado conscientemente: maquina local, fluxo proprio, sem exposicao.
set NODES_EXCLUDE=[]

REM v2 restringe leitura/escrita a ~/.n8n-files. Liberamos so a pasta do projeto.
set N8N_RESTRICT_FILE_ACCESS_TO=%~dp0
set N8N_BLOCK_FILE_ACCESS_TO_N8N_FILES=false

REM ruido desnecessario para uma execucao academica offline
set N8N_DIAGNOSTICS_ENABLED=false
set N8N_VERSION_NOTIFICATIONS_ENABLED=false
set N8N_SECURE_COOKIE=false

if /i "%~1"=="run"    goto :run
if /i "%~1"=="import" goto :import
if /i "%~1"=="ui"     goto :ui
goto :ajuda

:ui
echo.
echo  Subindo o n8n. Leva cerca de 60 segundos na primeira vez.
echo  Quando aparecer "Editor is now accessible", abra:
echo.
echo      http://localhost:5678
echo.
n8n start
goto :eof

:import
echo  Importando n8n\fluxo_radar_vr.json ...
n8n import:workflow --input="n8n\fluxo_radar_vr.json"
goto :eof

:run
echo  Executando o fluxo Radar VR ...
n8n execute --id=radarVRpucpr0001
echo.
echo  Saidas esperadas:
echo    data\radar_vr_n8n.csv
echo    data\pareceres_n8n.json
echo    audio\briefing_AAAA-MM-DD_HH-MM.wav
goto :eof

:ajuda
echo.
echo  Uso:
echo     executar_n8n.cmd ui       abre a interface grafica
echo     executar_n8n.cmd run      executa o fluxo direto
echo     executar_n8n.cmd import   reimporta o fluxo do JSON
echo.
echo  ATENCAO: "ui" e "run" nao podem rodar ao mesmo tempo - ambos usam a
echo  porta 5679 do task broker. Feche a interface antes de usar "run".
echo.
goto :eof
