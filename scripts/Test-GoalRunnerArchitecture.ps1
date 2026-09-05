[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$config = Join-Path $root '.codex\config.toml'
$skill = Join-Path $root '.agents\skills\goal-runner\SKILL.md'
$goalState = Join-Path $root '.agents\skills\goal-runner\references\goal-state.md'
$ladder = Join-Path $root '.agents\skills\goal-runner\references\laziness-ladder.md'
$handoff = Join-Path $root '.agents\skills\context-handoff\SKILL.md'
$reminder = Join-Path $root '.agents\skills\context-handoff\scripts\context_handoff_reminder.py'
$installer = Join-Path $root 'scripts\Install-GoalRunner.ps1'
$uninstaller = Join-Path $root 'scripts\Uninstall-GoalRunner.ps1'
$acceptanceTemplate = Join-Path $root 'templates\acceptance.goal-runner.json'
$passport = Join-Path $root 'templates\goal-passport.example.json'
$benchmarkFixture = Join-Path $root 'tests\fixtures\hre-001-benchmark.json'
$configFixture = Join-Path $root 'templates\codex.config.fixture.toml'
$goalProgress = Join-Path $root 'goal_progress.py'
$goalOrchestrator = Join-Path $root 'goal_orchestrator.py'
$updateImpact = Join-Path $root 'update_impact.py'
$updateCandidate = Join-Path $root 'templates\update-candidate.example.json'
$updateRadar = Join-Path $root 'update_radar.py'
$updateBatch = Join-Path $root 'templates\update-batch.example.json'
$updateRadarTask = Join-Path $root 'templates\update-radar-task.md'
$updateRadarState = Join-Path $root ('.harness\runtime\architecture-update-radar-{0}.json' -f [guid]::NewGuid().ToString('N'))

$pythonCheck = @'
import json, sys, tomllib
from pathlib import Path
root = Path(sys.argv[1])
cfg = tomllib.loads((root / '.codex/config.toml').read_text(encoding='utf-8'))
agents = cfg.get('agents', {})
assert agents.get('enabled') is True
assert agents.get('max_concurrent_threads_per_session') == 12
assert agents.get('default_subagent_model') == 'gpt-5.6-terra'
roles = {}
for path in sorted((root / '.codex/agents').glob('harness-goal-*.toml')):
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    for key in ('name', 'description', 'model', 'model_reasoning_effort', 'sandbox_mode', 'developer_instructions'):
        assert data.get(key), f'{path.name}: missing {key}'
    assert data['name'] not in roles, f'duplicate agent name {data["name"]}'
    roles[data['name']] = data
expected = {'harness_goal_explorer', 'harness_goal_worker', 'harness_goal_verifier', 'harness_goal_lead'}
assert set(roles) == expected, (set(roles), expected)
assert roles['harness_goal_explorer']['sandbox_mode'] == 'read-only'
assert roles['harness_goal_verifier']['sandbox_mode'] == 'read-only'
assert roles['harness_goal_lead']['sandbox_mode'] == 'read-only'
assert roles['harness_goal_worker']['sandbox_mode'] == 'workspace-write'
fixture = tomllib.loads((root / 'templates/codex.config.fixture.toml').read_text(encoding='utf-8'))
assert fixture.get('features', {}).get('goals') is True
criteria = json.loads((root / 'templates/acceptance.goal-runner.json').read_text(encoding='utf-8'))['criteria']
assert [item['id'] for item in criteria] == ['runtime-tests', 'plan-passport', 'benchmark', 'architecture', 'installer', 'review']
passport = json.loads((root / 'templates/goal-passport.example.json').read_text(encoding='utf-8'))
continuity = passport['chain']
assert all(key in continuity for key in ('canonicalWorkItemPath', 'baselineId', 'treatmentId', 'metricsPath', 'metricsSchemaVersion'))
assert all(isinstance(continuity[key], str) and continuity[key] for key in ('canonicalWorkItemPath', 'baselineId', 'treatmentId', 'metricsPath'))
assert continuity['baselineId'] != continuity['treatmentId']
assert continuity['metricsSchemaVersion'] == 1 and isinstance(continuity['metricsSchemaVersion'], int) and not isinstance(continuity['metricsSchemaVersion'], bool)
benchmark = json.loads((root / 'tests/fixtures/hre-001-benchmark.json').read_text(encoding='utf-8'))
assert benchmark.get('schemaVersion') == 1 and isinstance(benchmark.get('scenarios'), list) and len(benchmark['scenarios']) >= 20
print(json.dumps({'cap': agents['max_concurrent_threads_per_session'], 'roles': sorted(roles)}))
'@

& python -c $pythonCheck $root
if ($LASTEXITCODE -ne 0) { throw 'TOML and acceptance architecture validation failed.' }

foreach ($path in @($config, $skill, $goalState, $ladder, $handoff, $reminder, $installer, $uninstaller, $acceptanceTemplate, $passport, $benchmarkFixture, $configFixture, $goalProgress, $goalOrchestrator, $updateImpact, $updateCandidate, $updateRadar, $updateBatch, $updateRadarTask)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
}

& python (Join-Path $root 'goal_runner_validator.py') check $passport
if ($LASTEXITCODE -ne 0) { throw 'Example executable Goal passport is invalid.' }

& python $goalOrchestrator plan $passport --parent-state running | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Parent Goal action planner rejected the valid example passport.' }

& python $updateImpact classify $updateCandidate | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Update impact radar rejected the valid example candidate.' }

try {
    $firstScan = & python $updateRadar scan $updateBatch --state $updateRadarState | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $firstScan.pendingCount -lt 1) { throw 'Watcher did not preserve the actionable example as pending.' }
    $repeatScan = & python $updateRadar scan $updateBatch --state $updateRadarState | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $repeatScan.stateChanged -or $repeatScan.status -ne 'pending-evaluation') { throw 'Repeated scan lost pending evaluation or wrote duplicate state.' }
    $fixtureHash = (Get-FileHash -LiteralPath $updateBatch -Algorithm SHA256).Hash.ToLowerInvariant()
    foreach ($pending in $firstScan.pending) {
        & python $updateRadar resolve $pending.id --digest $pending.digest --outcome no-benefit --evidence-hash $fixtureHash --state $updateRadarState | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Isolated fixture resolution failed.' }
    }
    $resolvedScan = & python $updateRadar scan $updateBatch --state $updateRadarState | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $resolvedScan.pendingCount -ne 0 -or $resolvedScan.stateChanged) { throw 'Resolved fixture was proposed again.' }
    Write-Host 'PASS isolated radar CLI: pending survives repeat; resolved repeat is quiet.'
} finally {
    if (Test-Path -LiteralPath $updateRadarState) { Remove-Item -LiteralPath $updateRadarState -Force }
}

$skillText = Get-Content -LiteralPath $skill -Raw
$goalStateText = Get-Content -LiteralPath $goalState -Raw
$ladderText = Get-Content -LiteralPath $ladder -Raw
$handoffText = Get-Content -LiteralPath $handoff -Raw
$reminderText = Get-Content -LiteralPath $reminder -Raw
$installerText = Get-Content -LiteralPath $installer -Raw
$uninstallerText = Get-Content -LiteralPath $uninstaller -Raw

$requiredSkillPatterns = @(
    'requests up to 12 subagents',
    'dependency-aware graph',
    'one writer per checkout or worktree',
    'contract acknowledgement',
    'visible_context_remaining <= 45%',
    'Archive Goal chain',
    'Never silently expand',
    'primary dispatches all workspace-write workers',
    'first sufficient laziness-ladder rung',
    'correctness review',
    'separate simplify review',
    'executable plan snapshot',
    'Before any measured execution, assign explicit bounded baseline and treatment IDs',
    'Immediately before any worker write, validate the current executable plan snapshot',
    'At meaningful run or accepted-subgoal checkpoints only',
    'It does not prove real-world token savings or statistical significance',
    'Acceptance evidence is fresh only for the current relevant repository state',
    'NO_PROGRESS',
    'Control DAG and Graphify are separate',
    'Graphify output is not acceptance evidence by itself',
    'carry only the treatment ID, metrics path/schema',
    'Parent Goal Play/resume control',
    'one native Goal in the primary task',
    'goal_orchestrator.py plan',
    'Update impact radar',
    'update_impact.py classify',
    'update_radar.py scan',
    'run-local-evaluation',
    'API-only feature',
    'Use Luna'
)
foreach ($pattern in $requiredSkillPatterns) {
    if (-not $skillText.Contains($pattern)) { throw "Goal Runner contract missing: $pattern" }
}
if ($skillText.Contains('TODO')) { throw 'Goal Runner skill still contains TODO.' }

$readmeText = Get-Content -LiteralPath (Join-Path $root 'README.md') -Raw
foreach ($pattern in @('goal_progress.py check', 'NO_PROGRESS', 'control DAG', 'Graphify', 'acceptance evidence', 'goal_orchestrator.py plan', 'update_impact.py classify', 'update_radar.py scan', 'run-local-evaluation', 'API-only', 'no-meaningful-updates')) {
    if (-not $readmeText.Contains($pattern)) { throw "README control-evidence contract missing: $pattern" }
}

$updateRadarTaskText = Get-Content -LiteralPath $updateRadarTask -Raw
foreach ($pattern in @('https://learn.chatgpt.com/docs/changelog', 'https://developers.openai.com/api/docs/changelog', 'https://developers.openai.com/api/docs/deprecations', 'https://developers.openai.com/api/docs/guides/latest-model', 'report-only', 'commit, push')) {
    if (-not $updateRadarTaskText.Contains($pattern)) { throw "Update radar task contract missing: $pattern" }
}

$requiredStatePatterns = @(
    'Project root:',
    'Data owner:',
    'Risk class:',
    'External-side-effect boundary:',
    'Approved passport revision:',
    'Approval provenance:',
    'Checkout/worktree policy:',
    'Current verified subgoal:',
    'Next minimal slice and acceptance check:',
    'Standing authorization scope:',
    'Commit policy:',
    'Last accepted commit:',
    'Current laziness-ladder rung:',
    'Rejected lower rungs:',
    'Retained exceptions / ponytail triggers:',
    'Executable plan snapshot:',
    'Last validated plan snapshot/hash:',
    'Measurement treatment IDs:',
    'Metrics path/schema:'
)
foreach ($pattern in $requiredStatePatterns) {
    if (-not $goalStateText.Contains($pattern)) { throw "Goal state schema missing: $pattern" }
}

$requiredLadderPatterns = @(
    'Do nothing (YAGNI)',
    'Standard library or language feature',
    'Native platform primitive',
    'Existing project dependency',
    'One direct expression or line',
    'Minimum working code',
    'validation at trust boundaries',
    'ponytail:',
    'Correctness pass',
    'Simplify pass'
)
foreach ($pattern in $requiredLadderPatterns) {
    if (-not $ladderText.Contains($pattern)) { throw "Laziness ladder contract missing: $pattern" }
}

$workerText = Get-Content -LiteralPath (Join-Path $root '.codex\agents\harness-goal-worker.toml') -Raw
$verifierText = Get-Content -LiteralPath (Join-Path $root '.codex\agents\harness-goal-verifier.toml') -Raw
foreach ($pattern in @('YAGNI', 'native platform', 'ponytail triggers')) {
    if (-not $workerText.Contains($pattern)) { throw "Worker laziness-ladder contract missing: $pattern" }
}
foreach ($pattern in @('two ordered passes', 'correctness', 'laziness ladder', 'safety floor')) {
    if (-not $verifierText.Contains($pattern)) { throw "Verifier two-pass review contract missing: $pattern" }
}

$requiredHandoffPatterns = @(
    'Goal-chain mode',
    'standing chain authorization',
    'idle-pending-review',
    'Never archive a Goal chain',
    'validator-readable executable plan snapshot',
    'the last validated executable plan snapshot and hash',
    'Do not copy telemetry rows'
)
foreach ($pattern in $requiredHandoffPatterns) {
    if (-not $handoffText.Contains($pattern)) { throw "Context Handoff chain contract missing: $pattern" }
}

if (-not $reminderText.Contains('standing chain authorization')) {
    throw 'Compact reminder does not route approved Goal-chain handoffs.'
}
foreach ($pattern in @('Approval provenance', 'Standing authorization scope', 'bounded continuation', 'successor creation')) {
    if (-not $reminderText.Contains($pattern)) { throw "Compact reminder authorization contract missing: $pattern" }
}

foreach ($pattern in @('[ValidateSet(12)]', 'GlobalContextHandoffPath', 'goal-runner-install.json', 'schemaVersion', 'Unmanaged agent file already exists', 'AdoptMatchingLegacyRoles', 'AdoptVerifiedLegacyRoles', 'Legacy role identity does not match', 'transactionRoot', 'Copy-Item -LiteralPath $originalConfig')) {
    if (-not $installerText.Contains($pattern)) { throw "Transactional installer contract missing: $pattern" }
}
foreach ($pattern in @('goal-runner-install.json', 'allowedRoleNames', 'Get-ContainedAgentPath', 'OrdinalIgnoreCase', 'manifest.roles.PSObject.Properties', 'record.Value.sha256')) {
    if (-not $uninstallerText.Contains($pattern)) { throw "Manifest-based uninstaller contract missing: $pattern" }
}
if ($uninstallerText.Contains('$sourceAgents')) { throw 'Uninstaller must not derive installed role hashes from the mutable source tree.' }
if ($installerText.Contains('goal-runner-candidate-{0}.toml') -or $uninstallerText.Contains('goal-runner-uninstall-{0}.toml')) { throw 'WhatIf validation must not depend on temporary candidate files.' }

Write-Host 'PASS Goal Runner architecture contract is internally consistent.' -ForegroundColor Green
