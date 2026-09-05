[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$RegistryPath,
    [switch]$Apply,
    [switch]$IdleConfirmed,
    [string]$PythonExecutable = 'python'
)

$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $sourceRoot 'harness_distribution.py'
if ($Apply -and -not $IdleConfirmed) { throw '-Apply requires -IdleConfirmed after reviewing project instructions and active tasks.' }
function Invoke-Distribution([string[]]$Arguments) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        # UTF-8 is explicit for both sides; Unicode registry paths must round-trip.
        $lines = @(& $PythonExecutable -X utf8 $tool @Arguments 2>&1)
        $code = $LASTEXITCODE
        $value = ($lines -join [Environment]::NewLine) | ConvertFrom-Json
        return @{ code = $code; value = $value }
    } finally { $ErrorActionPreference = $previousPreference }
}
$previousOutputEncoding = [Console]::OutputEncoding
try {
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$validated = Invoke-Distribution -Arguments @('registry', '--path', (Resolve-Path -LiteralPath $RegistryPath).Path)
if ($validated.code -ne 0) { throw "Invalid registry: $($validated.value.error)" }
$registry = $validated.value
$failed = $false
foreach ($project in $registry.projects) {
    if ($project.path -eq $sourceRoot) {
        [pscustomobject]@{ project = $project.name; status = 'source-checkout'; path = $project.path } | ConvertTo-Json -Compress
        continue
    }
    if ($project.deferredReason) {
        [pscustomobject]@{ project = $project.name; status = 'deferred'; reason = $project.deferredReason } | ConvertTo-Json -Compress
        $failed = $true
        continue
    }
    $preview = Invoke-Distribution -Arguments @('plan', '--source', $sourceRoot, '--project', $project.path)
    $plan = $preview.value
    if ($preview.code -ne 0) {
        $status = if ($plan.canApply -eq $false) { 'conflict' } else { 'unavailable' }
        $detail = if ($status -eq 'conflict') { @($plan.files | Where-Object action -eq 'conflict' | ForEach-Object path) } else { $plan.error }
        [pscustomobject]@{ project = $project.name; status = $status; detail = $detail } | ConvertTo-Json -Compress
        $failed = $true
        continue
    }
    if (-not $Apply -or -not $PSCmdlet.ShouldProcess($project.path, "Apply reviewed Harness release $($plan.releaseId)")) {
        [pscustomobject]@{ project = $project.name; status = 'planned'; releaseId = $plan.releaseId; planHash = $plan.planHash; profileConfigured = $plan.profileConfigured; files = $plan.files } | ConvertTo-Json -Compress -Depth 5
        continue
    }
    # Each child rechecks its preview hash and acquires its own exclusive lock.
    $applied = Invoke-Distribution -Arguments @('apply', '--source', $sourceRoot, '--project', $project.path, '--plan-hash', $plan.planHash, '--idle-confirmed')
    if ($applied.code -ne 0) {
        [pscustomobject]@{ project = $project.name; status = 'unavailable'; detail = $applied.value.error } | ConvertTo-Json -Compress
        $failed = $true
    } else {
        $status = if ($applied.value.changed) { 'installed' } else { 'current' }
        [pscustomobject]@{ project = $project.name; status = $status; evidence = $applied.value } | ConvertTo-Json -Compress -Depth 5
    }
}
if ($failed) { exit 2 }
} finally { [Console]::OutputEncoding = $previousOutputEncoding }
