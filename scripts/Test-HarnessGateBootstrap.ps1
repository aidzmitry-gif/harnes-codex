[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$gate = Join-Path $root 'scripts\Invoke-HarnessGate.ps1'
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("harness-gate-bootstrap-{0}" -f [guid]::NewGuid().ToString('N'))

try {
    New-Item -ItemType Directory -Path (Join-Path $tempRoot 'scripts') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tempRoot '.harness\work') -Force | Out-Null
    Copy-Item -LiteralPath $gate -Destination (Join-Path $tempRoot 'scripts\Invoke-HarnessGate.ps1')
    Set-Content -LiteralPath (Join-Path $tempRoot '.harness\work\bootstrap.md') -Value '# bootstrap' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $tempRoot 'sample.txt') -Value 'safe content' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $tempRoot 'harness.config.json') -Value '{"fastChecks":[],"fullChecks":[],"requiredWorkItemFor":["prechange"]}' -Encoding UTF8

    & git -C $tempRoot init -b main | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize temporary Git repository.' }

    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $tempRoot 'scripts\Invoke-HarnessGate.ps1') -Stage prechange
    if ($LASTEXITCODE -ne 0) { throw 'Prechange gate failed in a Git repository without HEAD.' }

    Write-Host 'PASS Harness gate supports a new Git repository before its first commit.' -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        [IO.Directory]::Delete($tempRoot, $true)
    }
}
