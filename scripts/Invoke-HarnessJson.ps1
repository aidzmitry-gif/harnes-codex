[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet('compress', 'retrieve')][string]$Action,
    [Parameter(Mandatory=$true, Position=1)][string]$InputValue
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pointer = Join-Path $root '.harness/runtime/headroom-python.txt'
$runtime = 'python'
if (Test-Path -LiteralPath $pointer) {
    $configured = (Get-Content -LiteralPath $pointer -Raw -Encoding UTF8).Trim()
    if (Test-Path -LiteralPath $configured -PathType Leaf) { $runtime = $configured }
}
& $runtime (Join-Path $root 'harness_json.py') $Action $InputValue
exit $LASTEXITCODE
