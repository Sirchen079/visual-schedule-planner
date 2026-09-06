param([Parameter(Mandatory = $true)][string]$Installer)
$ErrorActionPreference = 'Stop'

# Only install into a newly created temporary directory, never over an existing v2 installation.
$existing = Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue |
    Get-ItemProperty | Where-Object { $_.DisplayName -like '知时*' }
if ($existing) { throw 'An existing Zhishi v2 installation is present; refusing to replace it.' }
$checkRoot = Join-Path ([IO.Path]::GetTempPath()) ('zhishi-release-check-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $checkRoot | Out-Null
$installDir = Join-Path $checkRoot 'installed'
$profileDir = Join-Path $checkRoot 'profile'
$runDir = Join-Path $checkRoot 'outside-repository'
New-Item -ItemType Directory -Path $runDir | Out-Null
Write-Output "CHECK_ROOT=$checkRoot"

function Wait-CheckedProcess($proc, $label, $seconds = 120) {
    if (-not $proc.WaitForExit($seconds * 1000)) { throw "$label timed out; process id=$($proc.Id)" }
    $proc.Refresh()
    if ($proc.ExitCode -ne 0) { throw "$label failed with exit $($proc.ExitCode)" }
}

$install = Start-Process -FilePath (Resolve-Path -LiteralPath $Installer).Path -ArgumentList @('/S', "/D=$installDir") -WindowStyle Hidden -PassThru
Wait-CheckedProcess $install 'NSIS install'
$appExe = Join-Path $installDir '知时.exe'
if (-not (Test-Path -LiteralPath $appExe)) { throw 'Installed executable missing' }
Write-Output 'INSTALL_PASS'

# Verify final frontend resources after actual NSIS extraction.
$sourceRoot = Join-Path $PSScriptRoot '..\frontend\dist'
$installedFrontend = Join-Path $installDir 'resources\zhishi-backend\_internal\frontend\dist'
foreach ($item in Get-ChildItem -LiteralPath $sourceRoot -Recurse -File) {
    $relative = [IO.Path]::GetRelativePath((Resolve-Path -LiteralPath $sourceRoot).Path, $item.FullName)
    $target = Join-Path $installedFrontend $relative
    if ((Get-FileHash -LiteralPath $item.FullName).Hash -ne (Get-FileHash -LiteralPath $target).Hash) {
        throw "Installed frontend mismatch: $relative"
    }
}
Write-Output 'INSTALLED_RESOURCE_HASHES_PASS'

$savedEnv = @{}
foreach ($name in @('ZHISHI_SHELL_USER_DATA_DIR', 'ZHISHI_SHELL_DATA_DIR', 'ZHISHI_SMOKE_STATE', 'ZHISHI_SMOKE_SCREENSHOT', 'ZHISHI_FRONTEND_DIR')) {
    $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
function Run-DesktopCheck([string]$mode, [string]$profile, [string]$label, [bool]$notify = $false) {
    $env:ZHISHI_SHELL_USER_DATA_DIR = $profile
    [Environment]::SetEnvironmentVariable('ZHISHI_SHELL_DATA_DIR', $null, 'Process')
    [Environment]::SetEnvironmentVariable('ZHISHI_FRONTEND_DIR', $null, 'Process')
    $env:ZHISHI_SMOKE_STATE = $mode
    $env:ZHISHI_SMOKE_SCREENSHOT = Join-Path $checkRoot "$label.png"
    $stdout = Join-Path $checkRoot "$label.stdout.log"
    $stderr = Join-Path $checkRoot "$label.stderr.log"
    $arguments = @('--smoke-quit')
    if ($notify) { $arguments += '--notify-selftest' }
    # Hide only the helper console, not the GUI under test: SW_HIDE overrides Electron's first ShowWindow.
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $appExe
    $startInfo.WorkingDirectory = $runDir
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in $arguments) { $startInfo.ArgumentList.Add($argument) }
    $proc = [Diagnostics.Process]::Start($startInfo)
    $outputTask = $proc.StandardOutput.ReadToEndAsync()
    $errorTask = $proc.StandardError.ReadToEndAsync()
    try { Wait-CheckedProcess $proc $label } finally {
        if ($proc.HasExited) {
            [IO.File]::WriteAllText($stdout, $outputTask.GetAwaiter().GetResult())
            [IO.File]::WriteAllText($stderr, $errorTask.GetAwaiter().GetResult())
        }
        Get-Content -LiteralPath $stdout -ErrorAction SilentlyContinue | Write-Host
        Get-Content -LiteralPath $stderr -ErrorAction SilentlyContinue | Write-Host
    }
    $log = Get-Content -LiteralPath $stdout -Raw
    if ($log -notmatch 'SMOKE PASS') { throw "$label did not report SMOKE PASS" }
    return [int]([regex]::Match($log, 'port=(\d+)').Groups[1].Value)
}
try {
    $firstPort = Run-DesktopCheck 'seed' $profileDir 'first-start'
    $secondPort = Run-DesktopCheck 'check' $profileDir 'second-start' $true
    if ($firstPort -eq $secondPort) { throw 'Port collision: restart did not exercise a distinct origin' }
    Write-Output "RESTART_PERSISTENCE_PASS ports=$firstPort,$secondPort"
    # Closed-app full-directory backup and restore into a different isolated profile.
    $restoreProfile = Join-Path $checkRoot 'restored-profile'
    New-Item -ItemType Directory -Path $restoreProfile | Out-Null
    Copy-Item -LiteralPath (Join-Path $profileDir 'data') -Destination (Join-Path $restoreProfile 'data') -Recurse
    $restoredPort = Run-DesktopCheck 'check' $restoreProfile 'restored-start'
    Write-Output "BACKUP_RESTORE_PASS port=$restoredPort"
} finally {
    foreach ($name in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process') }
}

# Uninstall only the exact temporary target just installed by this script.
$resolvedInstall = (Resolve-Path -LiteralPath $installDir).Path
if (-not $resolvedInstall.StartsWith($checkRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Unsafe uninstall target'
}
$uninstaller = Get-ChildItem -LiteralPath $resolvedInstall -Filter 'Uninstall*.exe' -File | Select-Object -First 1
if (-not $uninstaller) { throw 'Uninstaller missing' }
$uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList '/S' -WindowStyle Hidden -PassThru
Wait-CheckedProcess $uninstall 'NSIS uninstall'
for ($i = 0; $i -lt 100 -and (Test-Path -LiteralPath $appExe); $i++) { Start-Sleep -Milliseconds 200 }
if (Test-Path -LiteralPath $appExe) { throw 'Installed executable remains after uninstall' }
if (-not (Test-Path -LiteralPath (Join-Path $profileDir 'data\v2\backend.db'))) { throw 'Uninstall removed user data' }
Write-Output 'UNINSTALL_DATA_PRESERVATION_PASS'
Write-Output "RELEASE_CHECK_PASS evidence=$checkRoot"
