#===============================================================================
# backup.ps1 — Forex Trading Bot backup script (Phase 10)
#
# Creates a backup of trading data:
# - Execution journal (.execution_journal/)
# - Emergency stop / risk breakers (.emergency_stop/)
# - Configuration template (.env.example)
# - Monitoring logs (logs/)
#
# Never includes secrets (.env, credentials, keys).
# Never deletes existing trading history.
#===============================================================================

$ErrorActionPreference = "Stop"
$script:ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$script:BackupDir = Join-Path $script:ProjectRoot "backups"
$script:Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$script:BackupId = "backup-$script:Timestamp"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
}

#------------------------------------------------------------------------------
# 1. Create backup directory
#------------------------------------------------------------------------------
if (-not (Test-Path $script:BackupDir)) { New-Item -ItemType Directory -Path $script:BackupDir -Force | Out-Null }

$backupZip = Join-Path $script:BackupDir "$script:BackupId.zip"
Write-Log "Creating backup: $backupZip"

#------------------------------------------------------------------------------
# 2. Collect files to back up
#------------------------------------------------------------------------------
$filesToBackUp = @()

# Execution journal
$journalDir = Join-Path $script:ProjectRoot ".execution_journal"
if (Test-Path $journalDir) {
    Get-ChildItem -Path $journalDir -Recurse -File | ForEach-Object {
        $filesToBackUp += @{ Source = $_.FullName; Dest = "execution_journal/$($_.Name)" }
    }
}

# Emergency stop / risk breakers
$emergencyDir = Join-Path $script:ProjectRoot ".emergency_stop"
if (Test-Path $emergencyDir) {
    Get-ChildItem -Path $emergencyDir -Recurse -File | ForEach-Object {
        $filesToBackUp += @{ Source = $_.FullName; Dest = "risk/$($_.Name)" }
    }
}

# Config example (not .env - contains secrets)
$envExample = Join-Path $script:ProjectRoot ".env.example"
if (Test-Path $envExample) {
    $filesToBackUp += @{ Source = $envExample; Dest = "config/.env.example" }
}

# Logs
$logsDir = Join-Path $script:ProjectRoot "logs"
if (Test-Path $logsDir) {
    Get-ChildItem -Path $logsDir -Recurse -File | ForEach-Object {
        $filesToBackUp += @{ Source = $_.FullName; Dest = "logs/$($_.Name)" }
    }
}

#------------------------------------------------------------------------------
# 3. Create zip archive
#------------------------------------------------------------------------------
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($null) # ensure type loaded

# Build archive manually for fine-grained control
$archive = [System.IO.Compression.ZipFile]::Open($backupZip, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $manifest = @{
        backupId = $script:BackupId
        timestamp = (Get-Date -Format "o")
        filesIncluded = @()
        filesExcluded = @(".env (secrets - excluded)")
        version = "1.0"
    }

    foreach ($file in $filesToBackUp) {
        $entryName = $file.Dest
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.Source, $entryName, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
        $manifest.filesIncluded += $entryName
        Write-Log "Included: $entryName"
    }

    # Write manifest
    $manifestJson = $manifest | ConvertTo-Json -Depth 10
    $manifestBytes = [System.Text.Encoding]::UTF8.GetBytes($manifestJson)
    $manifestEntry = $archive.CreateEntry("manifest.json", [System.IO.Compression.CompressionLevel]::Optimal)
    $stream = $manifestEntry.Open()
    $stream.Write($manifestBytes, 0, $manifestBytes.Length)
    $stream.Close()
}
finally {
    $archive.Dispose()
}

$size = (Get-Item $backupZip).Length
Write-Log "Backup complete: $script:BackupId ($size bytes)"
Write-Log "Backup location: $backupZip"

#------------------------------------------------------------------------------
# 4. Enforce retention (keep last 10 backups)
#------------------------------------------------------------------------------
$maxBackups = 10
$retentionDays = 30
$cutoffDate = (Get-Date).AddDays(-$retentionDays)

$backups = Get-ChildItem -Path $script:BackupDir -Filter "backup-*.zip" | Sort-Object CreationTime -Descending

# Remove excess beyond max count
$excess = $backups | Select-Object -Skip $maxBackups
foreach ($b in $excess) {
    Write-Log "Removing old backup (count retention): $($b.Name)"
    Remove-Item $b.FullName -Force
}

# Remove backups older than retention days
$freshBackups = Get-ChildItem -Path $script:BackupDir -Filter "backup-*.zip" | Sort-Object CreationTime -Descending
foreach ($b in $freshBackups) {
    if ($b.CreationTime -lt $cutoffDate) {
        Write-Log "Removing old backup (age retention): $($b.Name)"
        Remove-Item $b.FullName -Force
    }
}

Write-Log "Backup retention enforced."
exit 0
