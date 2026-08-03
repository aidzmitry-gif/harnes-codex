[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ConfigPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\config.toml'),
    [string]$GlobalSkillPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.agents\skills\goal-runner'),
    [string]$GlobalAgentsPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\agents'),
    [string]$ManifestPath = '',
    [string]$PythonExecutable = 'python'
)

$ErrorActionPreference = 'Stop'
$beginMarker = '# BEGIN harness goal-runner agents'
$endMarker = '# END harness goal-runner agents'
$allowedRoleNames = @('harness-goal-explorer.toml', 'harness-goal-lead.toml', 'harness-goal-verifier.toml', 'harness-goal-worker.toml')
$configDirectory = Split-Path -Parent $ConfigPath
if (-not $ManifestPath) { $ManifestPath = Join-Path $configDirectory 'goal-runner-install.json' }

function Assert-Toml([string]$Path) {
    & $PythonExecutable -c 'import sys,tomllib; tomllib.load(open(sys.argv[1],chr(98)+chr(114)))' $Path
    if ($LASTEXITCODE -ne 0) { throw "Invalid TOML: $Path" }
}

function Assert-TomlText([string]$Text, [string]$Label) {
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text))
    & $PythonExecutable -c 'import base64,sys,tomllib; tomllib.loads(base64.b64decode(sys.argv[1]).decode(chr(117)+chr(116)+chr(102)+chr(45)+chr(56)))' $encoded
    if ($LASTEXITCODE -ne 0) { throw "Invalid TOML candidate: $Label" }
}

function Get-ContainedAgentPath([string]$Name) {
    if ($allowedRoleNames -notcontains $Name) { throw "Manifest contains a non-allowlisted role name: $Name" }
    $base = [IO.Path]::GetFullPath($GlobalAgentsPath).TrimEnd([char]92) + [char]92
    $destination = [IO.Path]::GetFullPath((Join-Path $GlobalAgentsPath $Name))
    if (-not $destination.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest role path escapes the agents directory: $Name"
    }
    return $destination
}

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { throw "Codex config not found: $ConfigPath" }
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "Goal Runner install manifest not found; refusing provenance-free uninstall: $ManifestPath" }
Assert-Toml $ConfigPath
try { $manifest = [IO.File]::ReadAllText($ManifestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json }
catch { throw "Invalid Goal Runner install manifest: $ManifestPath" }
if ($manifest.schemaVersion -ne 1 -or -not $manifest.roles) { throw "Unsupported Goal Runner install manifest: $ManifestPath" }
if ([IO.Path]::GetFullPath([string]$manifest.configPath) -ne [IO.Path]::GetFullPath($ConfigPath) -or
    [IO.Path]::GetFullPath([string]$manifest.goalRunner.destination) -ne [IO.Path]::GetFullPath($GlobalSkillPath) -or
    [IO.Path]::GetFullPath([string]$manifest.agentsPath) -ne [IO.Path]::GetFullPath($GlobalAgentsPath)) {
    throw 'Install manifest belongs to different destinations; refusing to remove.'
}

$text = [IO.File]::ReadAllText($ConfigPath, [Text.Encoding]::UTF8)
$hasBegin = $text.Contains($beginMarker)
$hasEnd = $text.Contains($endMarker)
if (-not ($hasBegin -and $hasEnd)) { throw 'Managed Goal Runner config markers are absent or incomplete; refusing to edit.' }

if (Test-Path -LiteralPath $GlobalSkillPath) {
    $item = Get-Item -LiteralPath $GlobalSkillPath -Force
    $actual = if ($item.Target) { [IO.Path]::GetFullPath([string]$item.Target) } else { '' }
    $expected = [IO.Path]::GetFullPath([string]$manifest.goalRunner.source)
    if ($item.LinkType -ne 'Junction' -or $actual -ne $expected) {
        throw "Refusing to remove unmanaged Goal Runner path: $GlobalSkillPath (type=$($item.LinkType), actual=$actual, expected=$expected)"
    }
}

$roleRecords = @($manifest.roles.PSObject.Properties)
if ($roleRecords.Count -ne 4) { throw "Expected four installed role records, found $($roleRecords.Count)." }
if (@(Compare-Object -ReferenceObject $allowedRoleNames -DifferenceObject @($roleRecords.Name)).Count -ne 0) {
    throw 'Install manifest role names do not match the exact allowlist.'
}
foreach ($record in $roleRecords) {
    $destination = Get-ContainedAgentPath $record.Name
    if (Test-Path -LiteralPath $destination) {
        if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) { throw "Unmanaged agent path: $destination" }
        if ((Get-FileHash -LiteralPath $destination).Hash -ne [string]$record.Value.sha256) {
            throw "Installed managed role was modified; refusing to remove: $destination"
        }
    }
}

$pattern = [regex]::Escape($beginMarker) + '.*?' + [regex]::Escape($endMarker) + '(\r?\n)?'
$candidate = [regex]::Replace($text, $pattern, '', [Text.RegularExpressions.RegexOptions]::Singleline)
Assert-TomlText $candidate 'Goal Runner uninstall config'

$approveConfig = $PSCmdlet.ShouldProcess($ConfigPath, 'Remove managed Goal Runner [agents] block')
$approveSkill = $PSCmdlet.ShouldProcess($GlobalSkillPath, 'Remove managed Goal Runner skill junction')
$approveAgents = $PSCmdlet.ShouldProcess($GlobalAgentsPath, 'Remove four manifest-owned Goal Runner agent files')
$approveManifest = $PSCmdlet.ShouldProcess($ManifestPath, 'Remove Goal Runner install manifest')
if (-not ($approveConfig -and $approveSkill -and $approveAgents -and $approveManifest)) { return }

$transactionRoot = Join-Path $configDirectory ('.goal-runner-uninstall-' + [guid]::NewGuid().ToString('N'))
$transactionAgents = Join-Path $transactionRoot 'agents'
$originalConfig = Join-Path $transactionRoot 'config.toml.original'
$originalManifest = Join-Path $transactionRoot 'manifest.json.original'
$backupPath = Join-Path $configDirectory 'config.toml.bak-goal-runner-uninstall'
$removedSkill = $false

New-Item -ItemType Directory -Path $transactionAgents -Force | Out-Null
Copy-Item -LiteralPath $ConfigPath -Destination $originalConfig
Copy-Item -LiteralPath $ManifestPath -Destination $originalManifest
foreach ($record in $roleRecords) {
    $destination = Get-ContainedAgentPath $record.Name
    if (Test-Path -LiteralPath $destination) { Copy-Item -LiteralPath $destination -Destination (Join-Path $transactionAgents $record.Name) }
}

try {
    if (-not (Test-Path -LiteralPath $backupPath)) { Copy-Item -LiteralPath $ConfigPath -Destination $backupPath }
    [IO.File]::WriteAllText($ConfigPath, $candidate, [Text.UTF8Encoding]::new($false))
    Assert-Toml $ConfigPath
    if (Test-Path -LiteralPath $GlobalSkillPath) {
        [IO.Directory]::Delete($GlobalSkillPath)
        $removedSkill = $true
    }
    foreach ($record in $roleRecords) {
        $destination = Get-ContainedAgentPath $record.Name
        if (Test-Path -LiteralPath $destination -PathType Leaf) { Remove-Item -LiteralPath $destination -Force }
    }
    Remove-Item -LiteralPath $ManifestPath -Force
} catch {
    $failure = $_
    Copy-Item -LiteralPath $originalConfig -Destination $ConfigPath -Force
    if ($removedSkill -and -not (Test-Path -LiteralPath $GlobalSkillPath)) {
        New-Item -ItemType Junction -Path $GlobalSkillPath -Target ([string]$manifest.goalRunner.source) | Out-Null
    }
    foreach ($record in $roleRecords) {
        $saved = Join-Path $transactionAgents $record.Name
        if (Test-Path -LiteralPath $saved) { Copy-Item -LiteralPath $saved -Destination (Get-ContainedAgentPath $record.Name) -Force }
    }
    if (-not (Test-Path -LiteralPath $ManifestPath)) { Copy-Item -LiteralPath $originalManifest -Destination $ManifestPath -Force }
    throw $failure
} finally {
    $resolvedTransaction = [IO.Path]::GetFullPath($transactionRoot)
    $resolvedConfigDirectory = [IO.Path]::GetFullPath($configDirectory).TrimEnd([char]92) + [char]92
    if ($resolvedTransaction.StartsWith($resolvedConfigDirectory) -and (Test-Path -LiteralPath $resolvedTransaction)) {
        Remove-Item -LiteralPath $resolvedTransaction -Recurse -Force
    }
}

Write-Host 'PASS Goal Runner removed from its durable manifest. Shared Context Handoff remains installed.' -ForegroundColor Green
