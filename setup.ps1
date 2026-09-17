# ============================================================================
#  Radar VR - preparacao do ambiente
#  Idempotente: reexecutar nao refaz o que ja esta pronto.
#
#      powershell -ExecutionPolicy Bypass -File setup.ps1
# ============================================================================

$ErrorActionPreference = "Continue"
$raiz = $PSScriptRoot
Set-Location $raiz

function Passo($n, $texto) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host " PASSO $n - $texto" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
}

# ---------------------------------------------------------------- 1. Ollama
Passo 1 "Ollama"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "  Ja instalado." -ForegroundColor Green
} else {
    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

# ------------------------------------------------------------- 2. espeak-ng
Passo 2 "espeak-ng (phonemizer PT-BR)"
if (Test-Path "C:\Program Files\eSpeak NG\espeak-ng.exe") {
    Write-Host "  Ja instalado." -ForegroundColor Green
} else {
    winget install --id eSpeak-NG.eSpeak-NG -e --accept-source-agreements --accept-package-agreements
}

# -------------------------------------------------------- 3. ambiente Python
Passo 3 "Ambiente Python 3.11"
$py = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { py -3.11 -m venv .venv }
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements.txt

# --------------------------------------------------------- 4. modelos Kokoro
Passo 4 "Modelos do Kokoro"
$dirModelos = Join-Path $raiz "modelos"
New-Item -ItemType Directory -Force -Path $dirModelos | Out-Null

$base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
foreach ($nome in @("kokoro-v1.0.onnx", "voices-v1.0.bin")) {
    $destino = Join-Path $dirModelos $nome
    if (Test-Path $destino) {
        $mb = [math]::Round((Get-Item $destino).Length / 1MB, 1)
        Write-Host "  $nome ja existe ($mb MB)." -ForegroundColor Green
        continue
    }
    Write-Host "  Baixando $nome..." -ForegroundColor Yellow
    # curl.exe em vez de Invoke-WebRequest: o cmdlet degrada muito em
    # arquivos grandes por causa do rendering da barra de progresso.
    curl.exe -L --fail --retry 3 -o $destino "$base/$nome"
    if (Test-Path $destino) {
        $mb = [math]::Round((Get-Item $destino).Length / 1MB, 1)
        Write-Host "  OK ($mb MB)" -ForegroundColor Green
    } else {
        Write-Host "  FALHOU - baixe manualmente de $base/$nome" -ForegroundColor Red
    }
}

# ------------------------------------------------------------ 5. modelo LLM
Passo 5 "Modelo de linguagem"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    if ((ollama list 2>$null | Out-String) -match "llama3.1:8b") {
        Write-Host "  llama3.1:8b ja disponivel." -ForegroundColor Green
    } else {
        Write-Host "  Baixando llama3.1:8b (~4.9 GB)..." -ForegroundColor Yellow
        ollama pull llama3.1:8b
    }
} else {
    Write-Host "  Ollama fora do PATH. Abra um terminal novo e rode:" -ForegroundColor Red
    Write-Host "     ollama pull llama3.1:8b" -ForegroundColor Red
}

# ------------------------------------------------------------------- 6. n8n
Passo 6 "n8n"
if (Get-Command n8n -ErrorAction SilentlyContinue) {
    Write-Host "  Ja instalado (versao $(n8n --version))." -ForegroundColor Green
} else {
    Write-Host "  Instalando via npm (pacote grande, ~10 min)..." -ForegroundColor Yellow
    npm install -g n8n --no-fund --no-audit
}
if (Get-Command n8n -ErrorAction SilentlyContinue) {
    $env:N8N_ENCRYPTION_KEY = "radar-vr-pucpr-etapa1"
    $env:N8N_DIAGNOSTICS_ENABLED = "false"
    n8n import:workflow --input="n8n\fluxo_radar_vr.json" 2>&1 |
        Select-String -Pattern "imported|error" | ForEach-Object { "    $_" }
}

# ----------------------------------------------------------- 7. verificacao
Passo 7 "Verificacao"
$ok = $true
function Checar($rotulo, $condicao) {
    if ($condicao) {
        Write-Host "  [ OK ] $rotulo" -ForegroundColor Green
    } else {
        Write-Host "  [FALTA] $rotulo" -ForegroundColor Red
        $script:ok = $false
    }
}

Checar "Python venv"          (Test-Path $py)
Checar "requests"             (& $py -c "import requests" 2>$null; $LASTEXITCODE -eq 0)
Checar "kokoro-onnx"          (& $py -c "import kokoro_onnx" 2>$null; $LASTEXITCODE -eq 0)
Checar "soundfile"            (& $py -c "import soundfile" 2>$null; $LASTEXITCODE -eq 0)
Checar "modelo kokoro"        (Test-Path (Join-Path $dirModelos "kokoro-v1.0.onnx"))
Checar "vozes kokoro"         (Test-Path (Join-Path $dirModelos "voices-v1.0.bin"))
Checar "espeak-ng"            (Test-Path "C:\Program Files\eSpeak NG\espeak-ng.exe")
Checar "n8n"                  ($null -ne (Get-Command n8n -ErrorAction SilentlyContinue))

try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    Checar "servico Ollama"   $true
    Checar "llama3.1:8b"      ($tags.models.name -contains "llama3.1:8b")
} catch {
    Checar "servico Ollama"   $false
}

Write-Host ""
if ($ok) {
    Write-Host " Ambiente pronto. Abra o painel com:" -ForegroundColor Green
    Write-Host "   .\`"Radar VR.cmd`"" -ForegroundColor White
} else {
    Write-Host " Itens pendentes acima. Se o Ollama acabou de ser instalado," -ForegroundColor Yellow
    Write-Host " abra um terminal novo e execute setup.ps1 outra vez." -ForegroundColor Yellow
}
Write-Host ""
