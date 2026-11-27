#===============================================================================
# health_check.ps1 — Forex Trading Bot health check (Phase 10)
#
# Performs a read-only health check of the running application:
# - Verifies the process is alive
# - Checks the monitoring dashboard endpoint (if enabled)
# - Validates configuration
# - Reports execution mode and safety status
#
# Exit codes: 0 = healthy, 1 = unhealthy, 2 = unknown
#===============================================================================

$ErrorActionPreference = "Continue"
$script:ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] [$Level] $Message"
}

$exitCode = 0

#------------------------------------------------------------------------------
# 1. Check if bot process is running
#------------------------------------------------------------------------------
$botProcess = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*src.main*"
}

if (-not $botProcess) {
    Write-Log "UNHEALTHY: No bot process found." "ERROR"
    exit 1
}

Write-Log "HEALTHY: Bot process is running (PID $($botProcess.Id))."

#------------------------------------------------------------------------------
# 2. Check dashboard endpoint (if monitoring is enabled)
#------------------------------------------------------------------------------
$dashboardPort = $env:MONITORING_DASHBOARD_PORT
if (-not $dashboardPort) { $dashboardPort = 8765 }
$dashboardEnabled = $env:MONITORING_DASHBOARD_ENABLED

if ($dashboardEnabled -ieq "true") {
    $url = "http://127.0.0.1:$dashboardPort/api/health"
    try {
        $response = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 5 -ErrorAction Stop
        if ($response.overall -eq "healthy") {
            Write-Log "HEALTHY: Dashboard reports overall status: healthy."
        }
        elseif ($response.overall -eq "degraded") {
            Write-Log "DEGRADED: Dashboard reports overall status: degraded." "WARN"
            $exitCode = 1
        }
        else {
            Write-Log "UNHEALTHY: Dashboard reports overall status: $($response.overall)." "ERROR"
            $exitCode = 1
        }
    }
    catch {
        Write-Log "WARNING: Could not reach dashboard at $url: $_" "WARNING"
        $exitCode = 2
    }
}
else {
    Write-Log "INFO: Dashboard not enabled (MONITORING_DASHBOARD_ENABLED != true). Skipping endpoint check."
}

#------------------------------------------------------------------------------
# 3. Validate configuration (PAPER mode default)
#------------------------------------------------------------------------------
$executionMode = $env:EXECUTION_MODE
if (-not $executionMode) { $executionMode = "PAPER" }

if ($executionMode -ieq "LIVE" -or $executionMode -ieq "REAL") {
    Write-Log "UNHEALTHY: LIVE/REAL execution mode is configured. This is not permitted." "ERROR"
    exit 1
}

Write-Log "HEALTHY: Execution mode is $executionMode (safe mode)."

#------------------------------------------------------------------------------
# 4. Check lock file (duplicate instance detection)
#------------------------------------------------------------------------------
$lockFile = Join-Path $script:ProjectRoot ".execution_lock\startup.lock"
if (Test-Path $lockFile) {
    $lockPid = Get-Content $lockFile -ErrorAction SilentlyContinue
    if ($lockPid -and $lockPid -ne $botProcess.Id) {
        Write-Log "WARNING: Lock file exists with different PID ($lockPid). Possible duplicate instance." "WARN"
    }
}

Write-Log "Health check complete. Exit code: $exitCode"
exit $exitCode
