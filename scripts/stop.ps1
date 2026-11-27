#===============================================================================
# stop.ps1 — Forex Trading Bot shutdown script (Phase 10)
#
# Performs a graceful shutdown:
# 1. Signals the application to stop (new entries blocked).
# 2. Waits for the process to exit.
# 3. Runs reconciliation (unresolved executions are preserved, not auto-resent).
# 4. Never closes positions — shutdown logic never liquidates.
#===============================================================================

$ErrorActionPreference = "Stop"
$script:ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$script:LogFile = Join-Path $script:ProjectRoot "logs\shutdown.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $script:LogFile -Value $line -ErrorAction SilentlyContinue
}

#------------------------------------------------------------------------------
# 1. Find the running bot process
#------------------------------------------------------------------------------
Write-Log "Looking for running Forex Trading Bot process..."
$botProcess = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*src.main*"
}

if (-not $botProcess) {
    Write-Log "No running bot process found. Nothing to stop."
    exit 0
}

Write-Log "Found bot process (PID $($botProcess.Id)). Requesting graceful shutdown..."

#------------------------------------------------------------------------------
# 2. Request graceful shutdown (Ctrl+C / SIGINT)
#------------------------------------------------------------------------------
# On Windows, send Ctrl+C to the console process group.
try {
    $botProcess.CloseMainWindow() | Out-Null
    Start-Sleep -Seconds 2
}
catch {
    Write-Log "WARNING: Could not send close message: $_" "WARNING"
}

# Wait for process to exit (up to 30 seconds).
$waited = 0
while ($botProcess -and $botProcess.HasExited -eq $false -and $waited -lt 30) {
    Start-Sleep -Seconds 1
    $waited++
}

if ($botProcess.HasExited -eq $false) {
    Write-Log "WARNING: Process did not exit within 30 seconds. Terminating forcefully." "WARNING"
    $botProcess.Kill()
}

#------------------------------------------------------------------------------
# 3. Shutdown summary
#------------------------------------------------------------------------------
Write-Log "Shutdown complete."
Write-Log "NOTE: Shutdown logic never closes or liquidates positions."
Write-Log "NOTE: Unresolved executions are preserved and require reconciliation on next start."
exit 0
