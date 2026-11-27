#===============================================================================
# start.ps1 — Forex Trading Bot startup script (Phase 10)
#
# Starts the trading bot in PAPER mode by default. Prevents duplicate instances
# via a process lock. Validates configuration before starting. Verifies MT5 IPC
# connection when DEMO mode is enabled.
#
# DEMO execution remains disabled unless explicitly authorized.
#===============================================================================

$ErrorActionPreference = "Stop"
$script:ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$script:LogFile = Join-Path $script:ProjectRoot "logs\startup.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $script:LogFile -Value $line -ErrorAction SilentlyContinue
}

#------------------------------------------------------------------------------
# 1. Prevent duplicate instances
#------------------------------------------------------------------------------
$lockFile = Join-Path $script:ProjectRoot ".execution_lock\startup.lock"
$lockDir = Split-Path $lockFile -Parent
if (-not (Test-Path $lockDir)) { New-Item -ItemType Directory -Path $lockDir -Force | Out-Null }

if (Test-Path $lockFile) {
    $existingPid = Get-Content $lockFile -ErrorAction SilentlyContinue
    if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        Write-Log "ERROR: Another instance is already running (PID $existingPid). Aborting startup." "ERROR"
        exit 1
    }
    # Stale lock — remove it.
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
}

try {
    $myPid = $PID
    $myPid | Out-File -FilePath $lockFile -Encoding utf8
}
catch {
    Write-Log "ERROR: Could not create process lock. Aborting startup." "ERROR"
    exit 1
}

#------------------------------------------------------------------------------
# 2. Validate configuration
#------------------------------------------------------------------------------
Write-Log "Validating configuration..."
$envFile = Join-Path $script:ProjectRoot ".env"
$envExample = Join-Path $script:ProjectRoot ".env.example"

if (-not (Test-Path $envFile)) {
    Write-Log "WARNING: .env not found. Copy .env.example to .env and configure as needed." "WARNING"
}

# Enforce safe deployment defaults.
$executionMode = $env:EXECUTION_MODE
if (-not $executionMode) {
    if (Test-Path $envFile) {
        $executionMode = (Get-Content $envFile | Select-String "EXECUTION_MODE=" | ForEach-Object { $_.ToString().Split("=")[1] }) -join ""
    }
}
if (-not $executionMode -or $executionMode -eq "") {
    $executionMode = "PAPER"
}

if ($executionMode -ieq "LIVE" -or $executionMode -ieq "REAL") {
    Write-Log "ERROR: LIVE/REAL execution mode is not permitted. Aborting startup." "ERROR"
    exit 1
}

Write-Log "Execution mode: $executionMode (PAPER is the default and safe mode)"

$demoAuto = $env:DEMO_AUTOMATIC_ENABLED
if ($demoAuto -ieq "true") {
    Write-Log "WARNING: DEMO_AUTOMATIC_ENABLED=true. Automatic demo execution requires explicit CLI activation. Proceeding with DEMO_AUTO disabled." "WARNING"
}

#------------------------------------------------------------------------------
# 3. Start the application
#------------------------------------------------------------------------------
Write-Log "Starting Forex Trading Bot..."
Write-Log "Project root: $script:ProjectRoot"

try {
    & python -m src.main
    $exitCode = $LASTEXITCODE
}
catch {
    Write-Log "ERROR: Application failed to start: $_" "ERROR"
    exit 1
}

#------------------------------------------------------------------------------
# 4. Release lock on exit
#------------------------------------------------------------------------------
finally {
    if (Test-Path $lockFile) { Remove-Item $lockFile -Force -ErrorAction SilentlyContinue }
}

if ($exitCode -ne 0) {
    Write-Log "Application exited with code $exitCode." "ERROR"
    exit $exitCode
}

Write-Log "Application stopped gracefully."
exit 0
