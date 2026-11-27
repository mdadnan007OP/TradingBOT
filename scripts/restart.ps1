#===============================================================================
# restart.ps1 — Forex Trading Bot restart script (Phase 10)
#
# Performs a safe restart:
# 1. Stops the running instance gracefully (stop.ps1).
# 2. Waits for the process to exit.
# 3. Validates configuration.
# 4. Starts the application (start.ps1).
#
# New entries are blocked before shutdown. Existing positions are never closed.
# Unresolved executions are reconciled before the new instance starts.
#===============================================================================

$ErrorActionPreference = "Stop"
$script:ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$script:StopScript = Join-Path $script:ProjectRoot "scripts\stop.ps1"
$script:StartScript = Join-Path $script:ProjectRoot "scripts\start.ps1"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
}

Write-Log "=== Forex Trading Bot Restart ==="

#------------------------------------------------------------------------------
# 1. Stop the running instance
#------------------------------------------------------------------------------
Write-Log "Step 1: Stopping current instance..."
& $script:StopScript
$stopCode = $LASTEXITCODE
if ($stopCode -ne 0) {
    Write-Log "WARNING: Stop script exited with code $stopCode. Proceeding with restart anyway." "WARN"
}

# Wait briefly for port/lock cleanup.
Start-Sleep -Seconds 3

#------------------------------------------------------------------------------
# 2. Validate configuration before starting
#------------------------------------------------------------------------------
Write-Log "Step 2: Validating configuration..."
$envFile = Join-Path $script:ProjectRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Log "WARNING: .env not found. Using defaults." "WARNING"
}

$executionMode = $env:EXECUTION_MODE
if (-not $executionMode) { $executionMode = "PAPER" }
if ($executionMode -ieq "LIVE" -or $executionMode -ieq "REAL") {
    Write-Log "ERROR: LIVE/REAL execution mode is not permitted. Aborting restart." "ERROR"
    exit 1
}
Write-Log "Configuration valid. Execution mode: $executionMode"

#------------------------------------------------------------------------------
# 3. Start the application
#------------------------------------------------------------------------------
Write-Log "Step 3: Starting application..."
& $script:StartScript
$startCode = $LASTEXITCODE

if ($startCode -eq 0) {
    Write-Log "=== Restart complete. Application is running. ==="
    exit 0
}
else {
    Write-Log "=== Restart failed. Start script exited with code $startCode. ===" "ERROR"
    exit $startCode
}
