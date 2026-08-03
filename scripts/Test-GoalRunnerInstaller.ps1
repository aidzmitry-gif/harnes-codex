[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $root 'scripts\Install-GoalRunner.ps1'
$uninstaller = Join-Path $root 'scripts\Uninstall-GoalRunner.ps1'
$fixture = Join-Path $root 'templates\codex.config.fixture.toml'
$tempBase = [IO.Path]::GetTempPath()
$tempRoot = Join-Path $tempBase ('goal-runner-test-' + [guid]::NewGuid().ToString('N'))

function Assert-TestRoot([string]$Path) {
    $resolved = [IO.Path]::GetFullPath($Path)
    $prefix = [IO.Path]::GetFullPath($tempBase).TrimEnd([char]92) + [char]92 + 'goal-runner-test-'
    if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing operation outside exact test root: $resolved"
    }
}

Assert-TestRoot $tempRoot
New-Item -ItemType Directory -Path $tempRoot | Out-Null

try {
    $configDir = Join-Path $tempRoot 'config-home'
    $configPath = Join-Path $configDir 'config.toml'
    $skillPath = Join-Path $tempRoot 'agents-skills\goal-runner'
    $contextPath = Join-Path $tempRoot 'agents-skills\context-handoff'
    $rolesPath = Join-Path $tempRoot 'codex-agents'
    New-Item -ItemType Directory -Path $configDir | Out-Null
    Copy-Item -LiteralPath $fixture -Destination $configPath

    $installArgs = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $installer,
        '-ConfigPath', $configPath,
        '-GlobalSkillPath', $skillPath,
        '-GlobalContextHandoffPath', $contextPath,
        '-GlobalAgentsPath', $rolesPath,
        '-MaxConcurrentSubagents', '12'
    )
    & powershell @installArgs
    if ($LASTEXITCODE -ne 0) { throw 'First isolated install failed.' }
    $manifestPath = Join-Path $configDir 'goal-runner-install.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Installer did not create a durable manifest.' }
    $firstConfigHash = (Get-FileHash -LiteralPath $configPath).Hash
    $firstManifestHash = (Get-FileHash -LiteralPath $manifestPath).Hash
    & powershell @installArgs
    if ($LASTEXITCODE -ne 0) { throw 'Second isolated install was not idempotent.' }
    if ((Get-FileHash -LiteralPath $configPath).Hash -ne $firstConfigHash) { throw 'Second install changed an already-current config.' }
    if ((Get-FileHash -LiteralPath $manifestPath).Hash -ne $firstManifestHash) { throw 'Second install changed an already-current manifest.' }

    $configText = Get-Content -LiteralPath $configPath -Raw
    if (([regex]::Matches($configText, [regex]::Escape('# BEGIN harness goal-runner agents')).Count) -ne 1) { throw 'Managed config block is duplicated.' }
    if (([regex]::Matches($configText, [regex]::Escape('# END harness goal-runner agents')).Count) -ne 1) { throw 'Managed config end marker is duplicated.' }
    if ((Get-ChildItem -LiteralPath $rolesPath -Filter 'harness-goal-*.toml' -File).Count -ne 4) { throw 'Four role files were not installed.' }
    foreach ($junction in @($skillPath, $contextPath)) {
        $item = Get-Item -LiteralPath $junction -Force
        if ($item.LinkType -ne 'Junction') { throw "Expected junction: $junction" }
    }
    & python -c "import sys,tomllib; d=tomllib.load(open(sys.argv[1],'br')); assert d['agents']['max_concurrent_threads_per_session']==12" $configPath
    if ($LASTEXITCODE -ne 0) { throw 'Installed TOML has the wrong cap.' }

    $failureDir = Join-Path $tempRoot 'failure-home'
    $failureConfig = Join-Path $failureDir 'config.toml'
    $blockedSkill = Join-Path $tempRoot 'blocked-skill'
    New-Item -ItemType Directory -Path $failureDir | Out-Null
    New-Item -ItemType Directory -Path $blockedSkill | Out-Null
    Copy-Item -LiteralPath $fixture -Destination $failureConfig
    $beforeHash = (Get-FileHash -LiteralPath $failureConfig).Hash
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installer -ConfigPath $failureConfig -GlobalSkillPath $blockedSkill -GlobalContextHandoffPath (Join-Path $tempRoot 'unused-context') -GlobalAgentsPath (Join-Path $tempRoot 'unused-roles') -MaxConcurrentSubagents 12 2>$null
    $failureExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($failureExitCode -eq 0) { throw 'Installer unexpectedly accepted an unmanaged skill directory.' }
    $afterHash = (Get-FileHash -LiteralPath $failureConfig).Hash
    if ($beforeHash -ne $afterHash) { throw 'Preflight failure changed config despite rollback contract.' }

    $conflictDir = Join-Path $tempRoot 'conflict-home'
    $conflictConfig = Join-Path $conflictDir 'config.toml'
    $conflictRoles = Join-Path $tempRoot 'conflict-roles'
    New-Item -ItemType Directory -Path $conflictDir | Out-Null
    New-Item -ItemType Directory -Path $conflictRoles | Out-Null
    Copy-Item -LiteralPath $fixture -Destination $conflictConfig
    Copy-Item -LiteralPath $fixture -Destination (Join-Path $conflictRoles 'harness-goal-explorer.toml')
    $conflictBeforeHash = (Get-FileHash -LiteralPath $conflictConfig).Hash
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installer -ConfigPath $conflictConfig -GlobalSkillPath (Join-Path $tempRoot 'conflict-skill') -GlobalContextHandoffPath (Join-Path $tempRoot 'conflict-context') -GlobalAgentsPath $conflictRoles -MaxConcurrentSubagents 12 2>$null
    $conflictExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($conflictExitCode -eq 0) { throw 'Installer overwrote an unmanaged same-name role file.' }
    if ((Get-FileHash -LiteralPath $conflictConfig).Hash -ne $conflictBeforeHash) { throw 'Role conflict changed config before refusing.' }

    $legacyDir = Join-Path $tempRoot 'legacy-home'
    $legacyConfig = Join-Path $legacyDir 'config.toml'
    $legacyRoles = Join-Path $tempRoot 'legacy-roles'
    New-Item -ItemType Directory -Path $legacyDir | Out-Null
    New-Item -ItemType Directory -Path $legacyRoles | Out-Null
    Copy-Item -LiteralPath $fixture -Destination $legacyConfig
    Copy-Item -LiteralPath (Join-Path $root '.codex\agents\harness-goal-explorer.toml') -Destination (Join-Path $legacyRoles 'harness-goal-explorer.toml')
    $legacyBeforeHash = (Get-FileHash -LiteralPath $legacyConfig).Hash
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installer -ConfigPath $legacyConfig -GlobalSkillPath (Join-Path $tempRoot 'legacy-skill') -GlobalContextHandoffPath (Join-Path $tempRoot 'legacy-context') -GlobalAgentsPath $legacyRoles -MaxConcurrentSubagents 12 2>$null
    $legacyExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($legacyExitCode -eq 0) { throw 'Installer silently adopted a matching role without provenance.' }
    if ((Get-FileHash -LiteralPath $legacyConfig).Hash -ne $legacyBeforeHash) { throw 'Legacy adoption refusal changed config.' }

    $rollbackDir = Join-Path $tempRoot 'rollback-home'
    $rollbackConfig = Join-Path $rollbackDir 'config.toml'
    $rollbackSkill = Join-Path $tempRoot 'rollback-skill'
    $rollbackContext = Join-Path $tempRoot 'rollback-context'
    $blockedAgentsPath = Join-Path $tempRoot 'agents-path-is-file'
    New-Item -ItemType Directory -Path $rollbackDir | Out-Null
    Copy-Item -LiteralPath $fixture -Destination $rollbackConfig
    Copy-Item -LiteralPath $fixture -Destination $blockedAgentsPath
    $rollbackBeforeHash = (Get-FileHash -LiteralPath $rollbackConfig).Hash
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installer -ConfigPath $rollbackConfig -GlobalSkillPath $rollbackSkill -GlobalContextHandoffPath $rollbackContext -GlobalAgentsPath $blockedAgentsPath -MaxConcurrentSubagents 12 2>$null
    $rollbackExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($rollbackExitCode -eq 0) { throw 'Installer unexpectedly succeeded despite a post-config agent-path failure.' }
    if ((Get-FileHash -LiteralPath $rollbackConfig).Hash -ne $rollbackBeforeHash) { throw 'Transactional failure did not restore the original config.' }
    if (Test-Path -LiteralPath $rollbackSkill) { throw 'Transactional failure left the Goal Runner junction.' }
    if (Test-Path -LiteralPath $rollbackContext) { throw 'Transactional failure left the Context Handoff junction.' }
    if (Test-Path -LiteralPath (Join-Path $rollbackDir 'goal-runner-install.json')) { throw 'Transactional failure left an install manifest.' }

    $manifestBytes = [IO.File]::ReadAllBytes($manifestPath)
    $tamperedManifest = [Text.Encoding]::UTF8.GetString($manifestBytes) | ConvertFrom-Json
    $tamperedRole = $tamperedManifest.roles.PSObject.Properties['harness-goal-explorer.toml'].Value
    $tamperedManifest.roles.PSObject.Properties.Remove('harness-goal-explorer.toml')
    $tamperedManifest.roles | Add-Member -NotePropertyName '..\escape.toml' -NotePropertyValue $tamperedRole
    [IO.File]::WriteAllText($manifestPath, (($tamperedManifest | ConvertTo-Json -Depth 6) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
    $beforeTamperReject = (Get-FileHash -LiteralPath $configPath).Hash
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $uninstaller -ConfigPath $configPath -GlobalSkillPath $skillPath -GlobalAgentsPath $rolesPath 2>$null
    $tamperExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    [IO.File]::WriteAllBytes($manifestPath, $manifestBytes)
    if ($tamperExitCode -eq 0) { throw 'Uninstaller accepted a manifest path traversal role name.' }
    if ((Get-FileHash -LiteralPath $configPath).Hash -ne $beforeTamperReject) { throw 'Tampered manifest refusal changed config.' }

    & powershell -NoProfile -ExecutionPolicy Bypass -File $uninstaller -ConfigPath $configPath -GlobalSkillPath $skillPath -GlobalAgentsPath $rolesPath
    if ($LASTEXITCODE -ne 0) { throw 'Isolated uninstall failed.' }
    $afterUninstall = Get-Content -LiteralPath $configPath -Raw
    if ($afterUninstall.Contains('# BEGIN harness goal-runner agents')) { throw 'Uninstaller left the managed config block.' }
    if (Test-Path -LiteralPath $skillPath) { throw 'Uninstaller left the Goal Runner junction.' }
    if ((Get-ChildItem -LiteralPath $rolesPath -Filter 'harness-goal-*.toml' -File -ErrorAction SilentlyContinue).Count -ne 0) { throw 'Uninstaller left role files.' }
    if (-not (Test-Path -LiteralPath $contextPath)) { throw 'Uninstaller removed the shared Context Handoff dependency.' }
    if (Test-Path -LiteralPath $manifestPath) { throw 'Uninstaller left the install manifest.' }

    Write-Host 'PASS Goal Runner installer is idempotent, rejects unmanaged paths, rolls back safely, and uninstalls cleanly.' -ForegroundColor Green
} finally {
    Assert-TestRoot $tempRoot
    foreach ($junction in @(
        (Join-Path $tempRoot 'agents-skills\goal-runner'),
        (Join-Path $tempRoot 'agents-skills\context-handoff'),
        (Join-Path $tempRoot 'unused-context'),
        (Join-Path $tempRoot 'rollback-skill'),
        (Join-Path $tempRoot 'rollback-context')
    )) {
        if (Test-Path -LiteralPath $junction) {
            $item = Get-Item -LiteralPath $junction -Force
            if ($item.LinkType -eq 'Junction') { [IO.Directory]::Delete($junction) }
        }
    }
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}
