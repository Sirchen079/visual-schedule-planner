param([string]$ShellRoot = 'E:\知时\electron-v2', [string]$Executable = '')
$ErrorActionPreference = 'Stop'
$checkDir = Join-Path $PSScriptRoot ('..\release\widget-check-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $checkDir | Out-Null
$checkDir = (Resolve-Path -LiteralPath $checkDir).Path
$env:ZHISHI_SHELL_USER_DATA_DIR = Join-Path $checkDir 'profile'
$env:ZHISHI_SHELL_DATA_DIR = Join-Path $checkDir 'data'
$env:ZHISHI_WIDGET_SCREENSHOT = Join-Path $checkDir 'widget.png'
$launch = [Diagnostics.ProcessStartInfo]::new()
if ($Executable) {
    $launch.FileName = $Executable
    $launch.Arguments = '--smoke-quit --widget-selftest'
} else {
    $launch.FileName = Join-Path $ShellRoot 'node_modules\electron\dist\electron.exe'
    $launch.Arguments = '"' + $ShellRoot + '" --smoke-quit --widget-selftest'
}
$launch.UseShellExecute = $false
$launch.CreateNoWindow = $true
$launch.RedirectStandardOutput = $true
$launch.RedirectStandardError = $true
$widgetProc = [Diagnostics.Process]::Start($launch)
Write-Output "CHECK_ROOT=$checkDir PID=$($widgetProc.Id)"
$outTask = $widgetProc.StandardOutput.ReadToEndAsync()
$errTask = $widgetProc.StandardError.ReadToEndAsync()
$widgetProc.WaitForExit()
$widgetOut = $outTask.GetAwaiter().GetResult()
$widgetErr = $errTask.GetAwaiter().GetResult()
[IO.File]::WriteAllText((Join-Path $checkDir 'stdout.log'), $widgetOut)
[IO.File]::WriteAllText((Join-Path $checkDir 'stderr.log'), $widgetErr)
Write-Output $widgetOut
Write-Output $widgetErr
if ($widgetProc.ExitCode -ne 0) { exit $widgetProc.ExitCode }
if ($widgetOut -notmatch 'SMOKE PASS') { throw 'Smoke did not report completion' }
