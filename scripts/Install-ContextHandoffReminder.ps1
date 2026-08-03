[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ConfigPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\config.toml'),
    [string]$HookScriptPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.agents\skills\context-handoff\scripts\context_handoff_reminder.py'),
    [string]$PythonExecutable = 'python'
)

$ErrorActionPreference = 'Stop'
$beginMarker = '# BEGIN context-handoff compact reminder'
$endMarker = '# END context-handoff compact reminder'

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Codex config not found: $ConfigPath"
}
if (-not (Test-Path -LiteralPath $HookScriptPath -PathType Leaf)) {
    throw "Reminder hook not found: $HookScriptPath"
}

& $PythonExecutable -c 'import sys,tomllib; tomllib.load(open(sys.argv[1],chr(98)+chr(114)))' $ConfigPath
if ($LASTEXITCODE -ne 0) {
    throw "Existing Codex config is not valid TOML: $ConfigPath"
}

$configText = [IO.File]::ReadAllText($ConfigPath, [Text.Encoding]::UTF8)
$hasBegin = $configText.Contains($beginMarker)
$hasEnd = $configText.Contains($endMarker)

if ($hasBegin -xor $hasEnd) {
    throw 'Managed context-handoff hook markers are incomplete; refusing to edit.'
}
if ($hasBegin -and $hasEnd) {
    Write-Host 'PASS Context-handoff compact reminder is already installed.' -ForegroundColor Green
    exit 0
}
if ($configText.Contains('context_handoff_reminder.py')) {
    throw 'An unmanaged context-handoff reminder already exists; refusing to duplicate it.'
}

$pythonForCommand = (Resolve-Path -LiteralPath $PythonExecutable -ErrorAction SilentlyContinue).Path
if (-not $pythonForCommand) {
    $pythonForCommand = (Get-Command $PythonExecutable -ErrorAction Stop).Source
}
$hookForCommand = (Resolve-Path -LiteralPath $HookScriptPath).Path

if ($pythonForCommand.Contains("'") -or $hookForCommand.Contains("'")) {
    throw 'Hook command paths containing single quotes are not supported.'
}

$command = ('"{0}" "{1}"' -f $pythonForCommand, $hookForCommand)
$block = @"
$beginMarker
[[hooks.SessionStart]]
matcher = "^compact$"

[[hooks.SessionStart.hooks]]
type = "command"
command = '$command'
command_windows = '$command'
timeout = 5
statusMessage = "Checking context handoff"
additionalContextLimit = 250
$endMarker
"@

$separator = if ($configText.EndsWith("`n")) { "`n" } else { "`r`n`r`n" }
$candidate = $configText + $separator + $block.TrimStart("`r", "`n") + "`r`n"
$configDirectory = Split-Path -Parent $ConfigPath
$temporaryPath = Join-Path $configDirectory 'config.toml.context-handoff-reminder.tmp'
$backupPath = Join-Path $configDirectory 'config.toml.bak-context-handoff-reminder'

if (-not $PSCmdlet.ShouldProcess($ConfigPath, 'Install SessionStart compact reminder hook')) {
    Write-Host "WHATIF Would add one SessionStart matcher '^compact$' hook." -ForegroundColor Yellow
    exit 0
}

try {
    [IO.File]::WriteAllText($temporaryPath, $candidate, [Text.UTF8Encoding]::new($false))
    & $pythonForCommand -c 'import sys,tomllib; tomllib.load(open(sys.argv[1],chr(98)+chr(114)))' $temporaryPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Candidate Codex config failed TOML validation.'
    }
    if (-not (Test-Path -LiteralPath $backupPath)) {
        Copy-Item -LiteralPath $ConfigPath -Destination $backupPath
    }
    Move-Item -LiteralPath $temporaryPath -Destination $ConfigPath -Force
} finally {
    if (Test-Path -LiteralPath $temporaryPath) {
        Remove-Item -LiteralPath $temporaryPath
    }
}

Write-Host "PASS Installed context-handoff compact reminder. Backup: $backupPath" -ForegroundColor Green
