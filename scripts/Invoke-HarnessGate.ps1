[CmdletBinding()]
param(
    [ValidateSet('prechange', 'postchange', 'release')]
    [string]$Stage = 'postchange',
    [switch]$RunFullChecks,
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$failures = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

function Add-Failure([string]$Message) { $script:failures.Add($Message) }
function Add-Warning([string]$Message) { $script:warnings.Add($Message) }
function Test-Command([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

$config = @{ protectedPaths = @('.env', '.env.*', 'secrets/', 'infra/production/'); allowedChangeRoots = @(); fastChecks = @(); fullChecks = @(); requiredWorkItemFor = @('prechange', 'postchange', 'release') }
if (Test-Path 'harness.config.json') {
    try {
        $loaded = Get-Content 'harness.config.json' -Raw | ConvertFrom-Json
        foreach ($property in $loaded.PSObject.Properties) { $config[$property.Name] = $property.Value }
    } catch { Add-Failure "Cannot read harness.config.json: $($_.Exception.Message)" }
} else { Add-Warning 'No harness.config.json; safe defaults are in use.' }

$isGit = Test-Path '.git'
$changed = @()
if ($isGit -and (Test-Command git)) {
    $changed = @(git diff --name-only; git diff --cached --name-only) | Sort-Object -Unique
    $untracked = @(git ls-files --others --exclude-standard)
    $changed = @($changed + $untracked) | Sort-Object -Unique
    if ($Stage -eq 'prechange' -and $changed.Count -gt 0) { Add-Warning "Working tree already contains changes: $($changed -join ', ')" }
} elseif ($Stage -ne 'prechange') { Add-Warning 'Git repository not found; diff scope cannot be checked.' }

if ($config.requiredWorkItemFor -contains $Stage) {
    $workItems = @(Get-ChildItem '.harness/work' -Filter '*.md' -File -ErrorAction SilentlyContinue)
    if ($workItems.Count -eq 0) { Add-Failure 'No work item in .harness/work/. Create one from templates/work-item.md.' }
}

foreach ($file in $changed) {
    foreach ($pattern in $config.protectedPaths) {
        if ($file -like $pattern -or $file.StartsWith($pattern.TrimEnd('/'))) { Add-Failure "Protected path changed: $file" }
    }
    if ($config.allowedChangeRoots.Count -gt 0 -and -not ($config.allowedChangeRoots | Where-Object { $file.StartsWith($_) })) {
        Add-Failure "File is outside the allowed change scope: $file"
    }
}

if ($changed.Count -gt 0 -and $isGit -and (Test-Command git)) {
    $headPath = git rev-parse --git-path HEAD
    $headValue = if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $headPath)) { Get-Content -LiteralPath $headPath -Raw } else { '' }
    if ($headValue -match '^ref:\s+(.+?)\s*$') {
        git show-ref --verify --quiet $Matches[1]
        $hasHead = $LASTEXITCODE -eq 0
    } else {
        $hasHead = [bool]$headValue.Trim()
    }
    $diffText = if ($hasHead) {
        git -c core.safecrlf=false diff HEAD -- . ':!*.lock' 2>$null
    } else {
        git -c core.safecrlf=false diff --cached -- . ':!*.lock' 2>$null
    }
    $secretPattern = '(?im)(api[_-]?key|secret|password|token)\s*[:=]\s*\S{16,}'
    if ($diffText -match $secretPattern) { Add-Failure 'Diff appears to contain a secret. Remove it and use secure configuration.' }
}

$commands = @($config.fastChecks)
if ($RunFullChecks -or $Stage -eq 'release') { $commands += @($config.fullChecks) }
if ($commands.Count -eq 0) {
    Add-Warning 'No checks configured. Add fastChecks/fullChecks to harness.config.json.'
} else {
    foreach ($check in $commands) {
        Write-Host "RUN  $check" -ForegroundColor Cyan
        Invoke-Expression $check
        if ($LASTEXITCODE -ne 0) { Add-Failure "Check failed: $check" }
    }
}

foreach ($warning in $warnings) { Write-Host "WARN $warning" -ForegroundColor Yellow }
foreach ($failure in $failures) { Write-Host "FAIL $failure" -ForegroundColor Red }
if ($failures.Count -gt 0 -or ($Strict -and $warnings.Count -gt 0)) { exit 1 }
Write-Host "PASS Harness gate '$Stage' passed." -ForegroundColor Green
