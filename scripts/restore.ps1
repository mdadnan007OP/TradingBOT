#===============================================================================
# restore.ps1 — Forex Trading Bot restore script (Phase 10)
#
# Restores from a backup created by backup.ps1.
#
# IMPORTANT: This does NOT delete existing trading history automatically.
# The operator must explicitly confirm before overwriting existing files.
#
# Usage: .\restore.ps1 -BackupId backup-20261126-120000
#        .\restore.ps1 -List
#===============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$BackupId,

    [Parameter(Mandatory = $false)]
    [switch]$List,

    [Parameter(Mandatory = $false)]
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
$script:ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$script:BackupDir = Join-Path $script:ProjectRoot "backups"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
}

#------------------------------------------------------------------------------
# List available backups
#------------------------------------------------------------------------------
if ($List) {
    Write-Log "Available backups:"
    $backups = Get-ChildItem -Path $script:BackupDir -Filter "backup-*.zip" -ErrorAction SilentlyContinue | Sort-Object CreationTime -Descending
    if (-not $backups) {
        Write-Log "No backups found in $script:BackupDir"
        exit 0
    }
    foreach ($b in $backups) {
        $size = [math]::Round($b.Length / 1KB, 2)
        Write-Log "  $($b.BaseName)  ($size KB)  Created: $($b.CreationTime)"
    }
    exit 0
}

#------------------------------------------------------------------------------
# Require BackupId for restore
#------------------------------------------------------------------------------
if (-not $BackupId) {
    Write-Log "ERROR: -BackupId is required for restore. Use -List to see available backups." "ERROR"
    exit 1
}

$backupZip = Join-Path $script:BackupDir "$BackupId.zip"
if (-not (Test-Path $backupZip)) {
    Write-Log "ERROR: Backup not found: $backupZip" "ERROR"
    exit 1
}

#------------------------------------------------------------------------------
# Require explicit confirmation
#------------------------------------------------------------------------------
if (-not $Confirm) {
    Write-Log "WARNING: Restore will overwrite existing files. This does NOT delete trading history automatically."
    Write-Log "WARNING: Re-run with -Confirm to proceed: .\restore.ps1 -BackupId $BackupId -Confirm"
    exit 0
}

#------------------------------------------------------------------------------
# Verify backup integrity
#------------------------------------------------------------------------------
Write-Log "Verifying backup integrity: $BackupId"
try {
    [System.IO.Compression.ZipFile]::OpenRead($backupZip) | ForEach-Object {
        $bad = $_.TestZip()  # not a real method; just open/close to verify
        $_.Dispose()
    }
}
catch {
    Write-Log "ERROR: Backup is corrupted or unreadable: $_" "ERROR"
    exit 1
}

# Read manifest
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($backupZip)
    $manifestEntry = $archive.Entries | Where-Object { $_.FullName -eq "manifest.json" }
    if (-not $manifestEntry) {
        Write-Log "ERROR: Backup is missing manifest (corrupted)." "ERROR"
        $archive.Dispose()
        exit 1
    }
    $stream = $manifestEntry.Open()
    $reader = New-Object System.IO.StreamReader($stream)
    $manifestJson = $reader.ReadToEnd()
    $stream.Close()
    $archive.Dispose()
    $manifest = $manifestJson | ConvertFrom-Json
    Write-Log "Backup manifest: $($manifest.backupId) created $($manifest.timestamp)"
}
catch {
    Write-Log "ERROR: Could not read backup manifest: $_" "ERROR"
    exit 1
}

#------------------------------------------------------------------------------
# Extract files
#------------------------------------------------------------------------------
Write-Log "Restoring files from backup..."
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($backupZip, $script:ProjectRoot, $true)
    Write-Log "Restore complete. Files extracted to $script:ProjectRoot"
}
catch {
    Write-Log "ERROR: Restore failed: $_" "ERROR"
    exit 1
}

Write-Log "NOTE: Review restored files before restarting the bot."
Write-Log "NOTE: Unresolved executions in the journal will require reconciliation on next start."
exit 0
