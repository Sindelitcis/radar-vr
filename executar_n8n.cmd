@echo off
REM ============================================================================
REM  Radar VR - lancador do n8n
REM
REM    executar_n8n.cmd ui      abre a interface em http://localhost:5678
REM    executar_n8n.cmd run     executa o boletim personalizado sem interface
REM    executar_n8n.cmd import  reimporta os fluxos a partir dos JSON
REM
REM  O microsservico precisa estar no ar: executar_servico.cmd
REM  As variaveis abaixo estao explicadas em docs/05_n8n.md.
REM ============================================================================

cd /d "%~dp0"

set N8N_ENCRYPTION_KEY=radar-vr-pucpr-etapa1
set NODES_EXCLUDE=[]
set N8N_RESTRICT_FILE_ACCESS_TO=%~dp0
set N8N_BLOCK_FILE_ACCESS_TO_N8N_FILES=false
set N8N_BLOCK_ENV_ACCESS_IN_NODE=false
set N8N_DIAGNOSTICS_ENABLED=false
set N8N_VERSION_NOTIFICATIONS_ENABLED=false
set N8N_SECURE_COOKIE=false

set RADAR_DIR_LOGS=%~dp0logs
if "%RADAR_SERVICO_URL%"=="" set RADAR_SERVICO_URL=http://127.0.0.1:8765

if /i "%~1"=="run"    goto :run
if /i "%~1"=="import" goto :import
if /i "%~1"=="ui"     goto :ui
goto :ajuda

:ui
echo  Subindo o n8n. Quando aparecer "Editor is now accessible", abra:
echo      http://localhost:5678
call n8n start
goto :eof

:import
call n8n import:workflow --input="n8n\fluxo_falhas.json"
call n8n import:workflow --input="n8n\fluxo_boletim_personalizado.json"
goto :eof

:run
call n8n execute --id=radarVRetapa2001
goto :eof

:ajuda
echo  Uso: executar_n8n.cmd ui ^| run ^| import
echo  "ui" e "run" nao rodam juntos: ambos usam a porta 5679 do task broker.
goto :eof
