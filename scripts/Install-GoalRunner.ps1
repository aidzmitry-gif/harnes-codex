[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ConfigPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\config.toml'),
    [string]$GlobalSkillPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.agents\skills\goal-runner'),
    [string]$GlobalContextHandoffPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.agents\skills\context-handoff'),
    [string]$GlobalAgentsPath = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\agents'),
    [string]$ManifestPath = '',
    [switch]$AdoptMatchingLegacyRoles,
    [switch]$AdoptVerifiedLegacyRoles,
    [ValidateSet(12)]
    [int]$MaxConcurrentSubagents = 12,
    [string]$PythonExecutable = 'python'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$sourceSkill = Join-Path $root '.agents\skills\goal-runner'
$sourceContextHandoff = Join-Path $root '.agents\skills\context-handoff'
$sourceAgents = Join-Path $root '.codex\agents'
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

function Assert-Junction([string]$Destination, [string]$Source, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Destination)) { return }
    $item = Get-Item -LiteralPath $Destination -Force
    $actual = if ($item.Target) { [IO.Path]::GetFullPath([string]$item.Target) } else { '' }
    $expected = [IO.Path]::GetFullPath($Source)
    if ($item.LinkType -ne 'Junction' -or $actual -ne $expected) {
        throw "$Label path exists but is not the managed junction: $Destination"
    }
}

function Read-InstallManifest([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { $data = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json }
    catch { throw "Invalid Goal Runner install manifest: $Path" }
    if ($data.schemaVersion -ne 1 -or -not $data.roles) { throw "Unsupported Goal Runner install manifest: $Path" }
    return $data
}

function Get-ManifestRole($Manifest, [string]$Name) {
    if (-not $Manifest) { return $null }
    $property = $Manifest.roles.PSObject.Properties | Where-Object Name -eq $Name | Select-Object -First 1
    if (-not $property -or -not $property.Value.sha256) { throw "Manifest is missing role provenance: $Name" }
    return $property.Value
}

foreach ($required in @($ConfigPath, $sourceSkill, $sourceContextHandoff, $sourceAgents)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required source not found: $required" }
}
Assert-Toml $ConfigPath
$roleSources = @(Get-ChildItem -LiteralPath $sourceAgents -Filter 'harness-goal-*.toml' -File)
if ($roleSources.Count -ne 4) { throw "Expected four Goal Runner roles, found $($roleSources.Count)." }
if (@(Compare-Object -ReferenceObject $allowedRoleNames -DifferenceObject @($roleSources.Name)).Count -ne 0) {
    throw 'Goal Runner source role names do not match the exact allowlist.'
}
$roleSources | ForEach-Object { Assert-Toml $_.FullName }

$manifest = Read-InstallManifest $ManifestPath
if ($manifest) {
    if ([IO.Path]::GetFullPath([string]$manifest.configPath) -ne [IO.Path]::GetFullPath($ConfigPath) -or
        [IO.Path]::GetFullPath([string]$manifest.goalRunner.destination) -ne [IO.Path]::GetFullPath($GlobalSkillPath) -or
        [IO.Path]::GetFullPath([string]$manifest.contextHandoff.destination) -ne [IO.Path]::GetFullPath($GlobalContextHandoffPath) -or
        [IO.Path]::GetFullPath([string]$manifest.agentsPath) -ne [IO.Path]::GetFullPath($GlobalAgentsPath)) {
        throw 'Install manifest belongs to different destinations; refusing to overwrite.'
    }
}

Assert-Junction $GlobalSkillPath $sourceSkill 'Global Goal Runner'
Assert-Junction $GlobalContextHandoffPath $sourceContextHandoff 'Global Context Handoff'
$legacyAdopted = @{}
foreach ($source in $roleSources) {
    $destination = Join-Path $GlobalAgentsPath $source.Name
    if (Test-Path -LiteralPath $destination -PathType Container) {
        throw "Agent destination is a directory, expected a file: $destination"
    }
    if (Test-Path -LiteralPath $destination -PathType Leaf) {
        $actualHash = (Get-FileHash -LiteralPath $destination).Hash
        if ($manifest) {
            $installedRole = Get-ManifestRole $manifest $source.Name
            if ($actualHash -ne [string]$installedRole.sha256) {
                throw "Installed managed role was modified; refusing to overwrite: $destination"
            }
        } elseif ($actualHash -ne (Get-FileHash -LiteralPath $source.FullName).Hash) {
            if (-not $AdoptVerifiedLegacyRoles) {
                throw "Unmanaged agent file already exists; refusing to overwrite: $destination"
            }
            Assert-Toml $destination
            $expectedAgentName = (($source.BaseName -replace '-', '_'))
            $destinationText = [IO.File]::ReadAllText($destination, [Text.Encoding]::UTF8)
            if ($destinationText -notmatch ('(?m)^\s*name\s*=\s*"' + [regex]::Escape($expectedAgentName) + '"\s*$')) {
                throw "Legacy role identity does not match its allowlisted filename: $destination"
            }
            $legacyAdopted[$source.Name] = $true
        } elseif (-not ($AdoptMatchingLegacyRoles -or $AdoptVerifiedLegacyRoles)) {
            throw "Matching role exists without install provenance; rerun with -AdoptMatchingLegacyRoles only after confirming it is a prior Goal Runner install: $destination"
        } else {
            $legacyAdopted[$source.Name] = $true
        }
    }
}

$configText = [IO.File]::ReadAllText($ConfigPath, [Text.Encoding]::UTF8)
$hasBegin = $configText.Contains($beginMarker)
$hasEnd = $configText.Contains($endMarker)
if ($hasBegin -xor $hasEnd) { throw 'Managed Goal Runner config markers are incomplete; refusing to edit.' }

$block = @"
$beginMarker
[agents]
enabled = true
max_concurrent_threads_per_session = $MaxConcurrentSubagents
default_subagent_model = "gpt-5.6-terra"
default_subagent_reasoning_effort = "medium"
$endMarker
"@

if ($hasBegin) {
    $pattern = [regex]::Escape($beginMarker) + '.*?' + [regex]::Escape($endMarker)
    $candidate = [regex]::Replace($configText, $pattern, $block, [Text.RegularExpressions.RegexOptions]::Singleline)
} else {
    if ($configText -match '(?m)^\s*\[agents\]\s*$') {
        throw 'An unmanaged [agents] table already exists. Merge the four Goal Runner keys manually or adopt managed markers.'
    }
    $lf = [string][char]10
    $crlf = [string][char]13 + [char]10
    $separator = if ($configText.EndsWith($lf)) { $lf } else { $crlf + $crlf }
    $candidate = $configText + $separator + $block.TrimStart([char]13, [char]10) + $crlf
}

Assert-TomlText $candidate 'managed Goal Runner config'

$needsSkill = -not (Test-Path -LiteralPath $GlobalSkillPath)
$needsContext = -not (Test-Path -LiteralPath $GlobalContextHandoffPath)
$approveConfig = $PSCmdlet.ShouldProcess($ConfigPath, "Set Goal Runner subagent cap to $MaxConcurrentSubagents")
$approveSkill = if ($needsSkill) { $PSCmdlet.ShouldProcess($GlobalSkillPath, 'Create Goal Runner skill junction') } else { $true }
$approveContext = if ($needsContext) { $PSCmdlet.ShouldProcess($GlobalContextHandoffPath, 'Create Context Handoff dependency junction') } else { $true }
$approveAgents = $PSCmdlet.ShouldProcess($GlobalAgentsPath, 'Install four managed Goal Runner custom agents')
$approveManifest = $PSCmdlet.ShouldProcess($ManifestPath, 'Write durable Goal Runner install provenance')

if (-not ($approveConfig -and $approveSkill -and $approveContext -and $approveAgents -and $approveManifest)) {
    if ($WhatIfPreference) { Write-Host "WHATIF Goal Runner would request exactly $MaxConcurrentSubagents subagents." -ForegroundColor Yellow }
    else { Write-Host 'CANCELLED Goal Runner installation was not fully approved.' -ForegroundColor Yellow }
    return
}

$transactionRoot = Join-Path $configDirectory ('.goal-runner-transaction-' + [guid]::NewGuid().ToString('N'))
$transactionAgents = Join-Path $transactionRoot 'agents'
$originalConfig = Join-Path $transactionRoot 'config.toml.original'
$candidateConfig = Join-Path $transactionRoot 'config.toml.candidate'
$originalManifest = Join-Path $transactionRoot 'manifest.json.original'
$backupPath = Join-Path $configDirectory 'config.toml.bak-goal-runner'
$createdSkill = $false
$createdContext = $false
$configWritten = $false
$manifestWritten = $false
$manifestExisted = Test-Path -LiteralPath $ManifestPath -PathType Leaf
$roleState = @{}

New-Item -ItemType Directory -Path $transactionAgents -Force | Out-Null
Copy-Item -LiteralPath $ConfigPath -Destination $originalConfig
if ($manifestExisted) { Copy-Item -LiteralPath $ManifestPath -Destination $originalManifest }
[IO.File]::WriteAllText($candidateConfig, $candidate, [Text.UTF8Encoding]::new($false))
Assert-Toml $candidateConfig

foreach ($source in $roleSources) {
    $destination = Join-Path $GlobalAgentsPath $source.Name
    $existed = Test-Path -LiteralPath $destination -PathType Leaf
    $roleState[$source.Name] = $existed
    if ($existed) { Copy-Item -LiteralPath $destination -Destination (Join-Path $transactionAgents $source.Name) }
}

try {
    if (-not (Test-Path -LiteralPath $backupPath)) { Copy-Item -LiteralPath $ConfigPath -Destination $backupPath }
    Copy-Item -LiteralPath $candidateConfig -Destination $ConfigPath -Force
    $configWritten = $true
    Assert-Toml $ConfigPath

    if ($needsSkill) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $GlobalSkillPath) -Force | Out-Null
        New-Item -ItemType Junction -Path $GlobalSkillPath -Target $sourceSkill | Out-Null
        $createdSkill = $true
    }
    if ($needsContext) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $GlobalContextHandoffPath) -Force | Out-Null
        New-Item -ItemType Junction -Path $GlobalContextHandoffPath -Target $sourceContextHandoff | Out-Null
        $createdContext = $true
    }

    New-Item -ItemType Directory -Path $GlobalAgentsPath -Force | Out-Null
    foreach ($source in $roleSources) {
        Copy-Item -LiteralPath $source.FullName -Destination (Join-Path $GlobalAgentsPath $source.Name) -Force
    }

    $installedRoles = [ordered]@{}
    foreach ($source in $roleSources) {
        $destination = Join-Path $GlobalAgentsPath $source.Name
        $priorRole = if ($manifest) { Get-ManifestRole $manifest $source.Name } else { $null }
        $ownership = if ($priorRole -and $priorRole.ownership) { [string]$priorRole.ownership } elseif ($legacyAdopted[$source.Name]) { 'adopted-explicit' } else { 'managed' }
        $installedRoles[$source.Name] = [ordered]@{ sha256 = (Get-FileHash -LiteralPath $destination).Hash; ownership = $ownership }
    }
    $manifestData = [ordered]@{
        schemaVersion = 1
        configPath = [IO.Path]::GetFullPath($ConfigPath)
        agentsPath = [IO.Path]::GetFullPath($GlobalAgentsPath)
        goalRunner = [ordered]@{ source = [IO.Path]::GetFullPath($sourceSkill); destination = [IO.Path]::GetFullPath($GlobalSkillPath) }
        contextHandoff = [ordered]@{ source = [IO.Path]::GetFullPath($sourceContextHandoff); destination = [IO.Path]::GetFullPath($GlobalContextHandoffPath) }
        roles = $installedRoles
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $ManifestPath) -Force | Out-Null
    [IO.File]::WriteAllText($ManifestPath, (($manifestData | ConvertTo-Json -Depth 6) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
    $manifestWritten = $true
} catch {
    $failure = $_
    if ($configWritten -and (Test-Path -LiteralPath $originalConfig)) { Copy-Item -LiteralPath $originalConfig -Destination $ConfigPath -Force }
    foreach ($source in $roleSources) {
        $destination = Join-Path $GlobalAgentsPath $source.Name
        if ($roleState[$source.Name]) {
            Copy-Item -LiteralPath (Join-Path $transactionAgents $source.Name) -Destination $destination -Force
        } elseif (Test-Path -LiteralPath $destination -PathType Leaf) {
            Remove-Item -LiteralPath $destination -Force
        }
    }
    if ($createdSkill -and (Test-Path -LiteralPath $GlobalSkillPath)) { [IO.Directory]::Delete($GlobalSkillPath) }
    if ($createdContext -and (Test-Path -LiteralPath $GlobalContextHandoffPath)) { [IO.Directory]::Delete($GlobalContextHandoffPath) }
    if ($manifestExisted -and (Test-Path -LiteralPath $originalManifest)) {
        Copy-Item -LiteralPath $originalManifest -Destination $ManifestPath -Force
    } elseif ($manifestWritten -and (Test-Path -LiteralPath $ManifestPath)) {
        Remove-Item -LiteralPath $ManifestPath -Force
    }
    throw $failure
} finally {
    $resolvedTransaction = [IO.Path]::GetFullPath($transactionRoot)
    $resolvedConfigDirectory = [IO.Path]::GetFullPath($configDirectory).TrimEnd([char]92) + [char]92
    if ($resolvedTransaction.StartsWith($resolvedConfigDirectory) -and (Test-Path -LiteralPath $resolvedTransaction)) {
        Remove-Item -LiteralPath $resolvedTransaction -Recurse -Force
    }
}

Write-Host "PASS Goal Runner installed with a requested cap of exactly $MaxConcurrentSubagents subagents and a durable manifest." -ForegroundColor Green
Write-Host 'Restart Codex or start a new app session before testing the new cap and roles.' -ForegroundColor Yellow
