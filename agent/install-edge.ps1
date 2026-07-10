# ═══════════════════════════════════════════════════════════════════
# Kaydan Edge Gateway — Installateur Windows (PowerShell)
# ═══════════════════════════════════════════════════════════════════
#
# Prérequis :
#   - Windows 10 20H2+ / Windows 11 / Server 2019+
#   - Python 3.10+ installé (winget install Python.Python.3.12)
#   - PowerShell 5.1+
#
# Usage rapide (à double-cliquer si execution policy permet) :
#   clic droit → Exécuter avec PowerShell
#
# Ce script :
#   1. Vérifie Python 3.10+
#   2. Copie le config dans C:\ProgramData\KaydanEdge\
#   3. Crée un venv Python dans C:\Program Files\KaydanEdge\
#   4. Installe l'agent depuis PyPI (ou depuis un wheel embarqué)
#   5. Enregistre un service Windows via NSSM
#   6. Démarre le service
# ═══════════════════════════════════════════════════════════════════

# ─── Vérif privilèges admin ────────────────────────────────────────
$currentUser = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host ""
    Write-Host "  ERREUR : Ce script doit être exécuté en tant qu'administrateur." `
        -ForegroundColor Red
    Write-Host "  Clic droit sur le fichier → 'Exécuter en tant qu'administrateur'"
    Write-Host ""
    pause
    exit 1
}

$ErrorActionPreference = "Stop"

# ─── Config ───────────────────────────────────────────────────────
$InstallDir  = "$env:ProgramFiles\KaydanEdge"
$ConfigDir   = "$env:ProgramData\KaydanEdge"
$LogsDir     = "$ConfigDir\logs"
$ServiceName = "KaydanEdgeGateway"
$NssmUrl     = "https://nssm.cc/release/nssm-2.24.zip"

function Info($msg)  { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Step($msg)  { Write-Host "" ; Write-Host "→ $msg" -ForegroundColor Cyan }
function Fail($msg)  { Write-Host "  ✗ $msg" -ForegroundColor Red ; pause ; exit 1 }

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "         Kaydan Edge Gateway — Installation Windows              " -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan

# ─── 1. Vérification Python ────────────────────────────────────────
Step "1/6 — Vérification de Python 3.10+"
try {
    $pyVersion = & python --version 2>&1
    if (-not ($pyVersion -match "Python (\d+)\.(\d+)")) {
        Fail "Python non détecté. Installer via : winget install Python.Python.3.12"
    }
    $major = [int]$matches[1]
    $minor = [int]$matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Fail "Python 3.10+ requis, trouvé $pyVersion"
    }
    Info "Python $major.$minor OK"
} catch {
    Fail "Impossible d'exécuter Python : $_"
}

# ─── 2. Création des dossiers ─────────────────────────────────────
Step "2/6 — Création des dossiers"
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path $ConfigDir  -Force | Out-Null
New-Item -ItemType Directory -Path $LogsDir    -Force | Out-Null
Info "Install : $InstallDir"
Info "Config  : $ConfigDir"

# Copie la config depuis le ZIP décompressé (dossier courant)
$configSrc = Join-Path $PSScriptRoot "config\kshield-agent.toml"
if (Test-Path $configSrc) {
    Copy-Item $configSrc -Destination "$ConfigDir\kshield-agent.toml" -Force
    Info "Config copiée dans $ConfigDir"
} else {
    Fail "config\kshield-agent.toml introuvable dans ce dossier."
}

# Copie les certs si présents
$certsSrc = Join-Path $PSScriptRoot "certs"
if (Test-Path $certsSrc) {
    Copy-Item $certsSrc -Destination "$ConfigDir\certs" -Recurse -Force
    Info "Certificats copiés"
}

# ─── 3. Création du venv Python ───────────────────────────────────
Step "3/6 — Création de l'environnement Python isolé"
$VenvDir = Join-Path $InstallDir "venv"
if (-not (Test-Path $VenvDir)) {
    & python -m venv $VenvDir
    Info "Venv créé"
} else {
    Info "Venv existant réutilisé"
}
$Pip    = Join-Path $VenvDir "Scripts\pip.exe"
$PyExe  = Join-Path $VenvDir "Scripts\python.exe"
$AgentExe = Join-Path $VenvDir "Scripts\kshield-agent.exe"

# ─── 4. Installation de l'agent ───────────────────────────────────
Step "4/6 — Installation du package kshield-agent"
& $Pip install --quiet --upgrade pip
# En Phase 1, on installe depuis GitHub (repo public ou avec token). Phase 2
# livrera un wheel préinstallé dans le ZIP.
$repoUrl = "git+https://github.com/sergehoo/kshield.git@main#subdirectory=agent"
& $Pip install --quiet $repoUrl
if ($LASTEXITCODE -ne 0) {
    Fail "Échec de l'installation du package Python."
}
Info "Agent installé"

# ─── 5. Activation (échange token) ────────────────────────────────
Step "5/6 — Appairage avec le cloud Kaydan Shield"

# Lit la config pour extraire server_url + activation_token
$config = Get-Content "$ConfigDir\kshield-agent.toml" -Raw
$serverUrl  = [regex]::Match($config, 'server_url\s*=\s*"([^"]+)"').Groups[1].Value
$actToken   = [regex]::Match($config, 'activation_token\s*=\s*"([^"]+)"').Groups[1].Value

if (-not $serverUrl -or -not $actToken) {
    Fail "server_url ou activation_token manquant dans la config."
}

Write-Host "     Serveur : $serverUrl"
Write-Host "     Token   : $($actToken.Substring(0, 12))..."

$env:KSHIELD_CONFIG_FILE = "$ConfigDir\kshield-agent.toml"
& $AgentExe activate --server-url $serverUrl --token $actToken
if ($LASTEXITCODE -ne 0) {
    Warn "Activation échouée — vérifier le token et la connexion Internet."
    Warn "Le service sera installé quand même, il retentera au démarrage."
}

# ─── 6. Enregistrement du service Windows via NSSM ────────────────
Step "6/6 — Création du service Windows"

# NSSM n'est pas natif Windows — on le télécharge si absent
$NssmDir = "$InstallDir\nssm"
$NssmExe = "$NssmDir\nssm.exe"
if (-not (Test-Path $NssmExe)) {
    Info "Téléchargement de NSSM (Non-Sucking Service Manager)..."
    $NssmZip = "$env:TEMP\nssm.zip"
    Invoke-WebRequest -Uri $NssmUrl -OutFile $NssmZip -UseBasicParsing
    Expand-Archive -Path $NssmZip -DestinationPath $env:TEMP -Force
    New-Item -ItemType Directory -Path $NssmDir -Force | Out-Null
    $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
    Copy-Item "$env:TEMP\nssm-2.24\$arch\nssm.exe" -Destination $NssmExe -Force
    Remove-Item "$env:TEMP\nssm-2.24" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $NssmZip -Force -ErrorAction SilentlyContinue
    Info "NSSM installé"
}

# Supprime le service existant s'il y en a un (mise à jour)
$existingSvc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingSvc) {
    Info "Service existant détecté — reconfiguration"
    & $NssmExe stop $ServiceName confirm 2>&1 | Out-Null
    & $NssmExe remove $ServiceName confirm 2>&1 | Out-Null
    Start-Sleep -Seconds 2
}

# Crée le service
& $NssmExe install $ServiceName $AgentExe "run"
& $NssmExe set $ServiceName AppDirectory     $InstallDir
& $NssmExe set $ServiceName AppEnvironmentExtra "KSHIELD_CONFIG_FILE=$ConfigDir\kshield-agent.toml"
& $NssmExe set $ServiceName DisplayName      "Kaydan Edge Gateway"
& $NssmExe set $ServiceName Description      "Passerelle temps réel Kaydan Shield — Kaydan Groupe"
& $NssmExe set $ServiceName Start            SERVICE_AUTO_START
& $NssmExe set $ServiceName AppStdout        "$LogsDir\service-stdout.log"
& $NssmExe set $ServiceName AppStderr        "$LogsDir\service-stderr.log"
& $NssmExe set $ServiceName AppRotateFiles   1
& $NssmExe set $ServiceName AppRotateBytes   10485760   # 10 MB
& $NssmExe set $ServiceName AppExit          Default Restart
& $NssmExe set $ServiceName AppRestartDelay  5000       # 5 s après crash
Info "Service '$ServiceName' enregistré"

# Démarre le service
& $NssmExe start $ServiceName
Start-Sleep -Seconds 3
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Info "Service DÉMARRÉ"
} else {
    Warn "Service pas encore démarré — voir : $LogsDir\service-stderr.log"
}

# ─── Fin ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✓ Installation terminée" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Service        : $ServiceName"
Write-Host "  Config         : $ConfigDir\kshield-agent.toml"
Write-Host "  Logs           : $LogsDir\"
Write-Host ""
Write-Host "  Commandes utiles :"
Write-Host "    Statut       : Get-Service $ServiceName"
Write-Host "    Redémarrer   : Restart-Service $ServiceName"
Write-Host "    Arrêter      : Stop-Service $ServiceName"
Write-Host "    Voir logs    : Get-Content $LogsDir\service-stderr.log -Tail 20"
Write-Host ""
Write-Host "  Vérifier sur : $serverUrl/edge-gateway"
Write-Host ""
pause
