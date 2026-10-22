[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$package = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('mycroft-tooling-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($testRoot) | Out-Null
$checks = 0
function Assert([bool]$condition, [string]$message) { if (-not $condition) { throw $message }; $script:checks++ }
function Write-Json($value, [string]$path) { [IO.File]::WriteAllText($path, ($value | ConvertTo-Json -Depth 30), (New-Object Text.UTF8Encoding($false))) }
function Expect-Rejection([scriptblock]$action, [string]$messagePattern) {
    $rejected = $false
    try { & $action | Out-Null } catch { $rejected = $_.Exception.Message -match $messagePattern }
    Assert $rejected "Expected rejection matching: $messagePattern"
}
foreach ($harness in @('codex', 'claude', 'opencode')) {
    $project = Join-Path $testRoot $harness
    [IO.Directory]::CreateDirectory($project) | Out-Null
    $sentinel = Join-Path $project 'provider-settings.txt'
    [IO.File]::WriteAllText($sentinel, 'preserve-existing-provider')
    & (Join-Path $package 'Install-Mycroft.ps1') -Harness $harness -ProjectRoot $project -WhatIf | Out-Null
    Assert (@(Get-ChildItem -LiteralPath $project -File -Recurse -Force).Count -eq 1) "$harness WhatIf wrote files."
    & (Join-Path $package 'Install-Mycroft.ps1') -Harness $harness -ProjectRoot $project | Out-Null
    $agentDirectory = @{ codex = '.codex/agents'; claude = '.claude/agents'; opencode = '.opencode/agents' }[$harness]
    $skillDirectory = if ($harness -eq 'claude') { '.claude/skills' } else { '.agents/skills' }
    Assert (@(Get-ChildItem -LiteralPath (Join-Path $project $agentDirectory) -File).Count -eq 7) "$harness adapters missing."
    Assert (@(Get-ChildItem -LiteralPath (Join-Path $project $skillDirectory) -Directory).Count -eq 3) "$harness skills missing."
    Assert ([IO.File]::ReadAllText($sentinel) -eq 'preserve-existing-provider') "$harness changed provider sentinel."
    Expect-Rejection { & (Join-Path $package 'Install-Mycroft.ps1') -Harness $harness -ProjectRoot $project } 'existing destination'
}
$collisionProject = Join-Path $testRoot 'late-conflict'
$collisionDirectory = Join-Path $collisionProject '.codex/agents'
[IO.Directory]::CreateDirectory($collisionDirectory) | Out-Null
$adapter = Get-ChildItem -LiteralPath (Join-Path $package 'adapters/codex') -File | Select-Object -Last 1
$collision = Join-Path $collisionDirectory $adapter.Name
[IO.File]::WriteAllText($collision, 'existing-agent')
Expect-Rejection { & (Join-Path $package 'Install-Mycroft.ps1') -Harness codex -ProjectRoot $collisionProject } 'existing destination'
Assert (@(Get-ChildItem -LiteralPath $collisionProject -File -Recurse -Force).Count -eq 1) 'Conflict caused partial skill writes.'
Assert ([IO.File]::ReadAllText($collision) -eq 'existing-agent') 'Conflict overwrote existing agent.'
$runDirectory = Join-Path $testRoot 'run'
[IO.Directory]::CreateDirectory((Join-Path $runDirectory 'attempts')) | Out-Null
$runPath = Join-Path $runDirectory 'run.json'
$recordPath = Join-Path $runDirectory 'attempts/t-evidence-1.json'
$run = @{
    schema_version = 'mycroft.run.v1'; run_id = 'tooling-test'; status = 'completed'
    limits = @{ max_tasks = 4; max_dispatches = 8; max_concurrency = 2; max_depth = 1 }
    dispatches_used = 1
    tasks = @(@{ id = 't-evidence'; role = 'mycroft-investigator'; depends_on = @(); required_evidence = $true; depth = 1; status = 'succeeded'; attempts = @(@{ attempt = 1; status = 'succeeded'; result_path = 'attempts/t-evidence-1.json' }) })
}
$record = @{
    schema_version = 'mycroft.worker.v1'; run_id = 'tooling-test'; task_id = 't-evidence'; attempt = 1; status = 'succeeded'
    answer = 'The document states port 8443.'
    sources = @(@{ id = 't-evidence:document'; locator = 'fixture.md'; retrieval_type = 'local_file'; retrieved_at = '2026-10-22T12:00:00Z'; excerpt = 'port=8443'; span = 'L1'; identity = $null })
    claims = @(@{ id = 'port'; text = 'The document states port 8443.'; source_ids = @('t-evidence:document'); support_status = 'supported'; rationale = 'The supplied setting is explicit.' })
    gaps = @(); requests = @(); issues = @()
    coverage = @{ searched = @('fixture.md'); read = @('fixture.md:L1'); unread = @(); limitations = @('Native token usage is unavailable.') }
}
Write-Json $run $runPath
Write-Json $record $recordPath
[IO.File]::WriteAllText((Join-Path $runDirectory 'report.md'), 'The document states port 8443; this is a source assertion.')
Write-Json @{ schema_version = 'mycroft.result.v1'; run_id = 'tooling-test'; status = 'completed'; report_path = 'report.md' } (Join-Path $runDirectory 'result.json')
& (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory | Out-Null
$checks++
$record.claims[0].id = 't-evidence:port'
$record.issues = @(@{ claim_ids = @('t-evidence:port'); severity = 'minor'; description = 'Retain source-reported qualification.'; source_ids = @('t-evidence:document'); remedy = 'Keep qualification.' })
Write-Json $record $recordPath
& (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory | Out-Null
$checks++
$record.claims[0].id = 'port'
Write-Json $record $recordPath
& (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory | Out-Null
$checks++
$record.issues = @()
$record.claims[0].source_ids = @('unknown')
Write-Json $record $recordPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'unknown source'
$record.claims[0].source_ids = @('t-evidence:document')
$record.sources[0].retrieval_type = 'search_snippet'
Write-Json $record $recordPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'discovery-only'
$record.sources[0].retrieval_type = 'local_file'
$record.task_id = 'wrong-task'
Write-Json $record $recordPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'identity does not match'
$record.task_id = 't-evidence'
Write-Json $record $recordPath
$run.dispatches_used = 9
Write-Json $run $runPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'exceeds its cap'
$run.dispatches_used = 2
$run.tasks += @{ id = 't-failed'; role = 'mycroft-alternatives'; depends_on = @(); required_evidence = $true; depth = 1; status = 'failed'; attempts = @(@{ attempt = 1; status = 'failed' }) }
$run.tasks[0].depends_on = @('t-failed')
Write-Json $run $runPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'unsuccessful dependency'
$run.tasks[1].depends_on = @('t-evidence')
Write-Json $run $runPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'graph cycle'
$run.tasks = @($run.tasks[0]); $run.tasks[0].depends_on = @(); $run.dispatches_used = 1
Write-Json $run $runPath
$report = Join-Path $runDirectory 'report.md'
[IO.File]::Move($report, (Join-Path $runDirectory 'report-withheld.md'))
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'no nonempty report'
[IO.File]::Move((Join-Path $runDirectory 'report-withheld.md'), $report)
$resultPath = Join-Path $runDirectory 'result.json'
Write-Json @{ schema_version = 'mycroft.result.v1'; run_id = 'tooling-test'; status = 'succeeded'; report_path = 'report.md' } $resultPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'mismatching schema, run ID or status'
$run.status = 'partial'
$run.gaps = @('A required source is inaccessible.')
$run.tasks += @{ id = 't-failed'; role = 'mycroft-alternatives'; depends_on = @(); required_evidence = $true; depth = 1; status = 'failed'; attempts = @(@{ attempt = 1; status = 'failed' }) }
$run.dispatches_used = 2
Write-Json $run $runPath
Write-Json @{ schema_version = 'mycroft.result.v1'; run_id = 'tooling-test'; status = 'partial'; report_path = 'report.md' } $resultPath
& (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory | Out-Null
$checks++
$run.tasks[0].status = 'partial'
$run.tasks[0].attempts[0].status = 'partial'
$record.status = 'partial'
$record.gaps = @('A required source could not be read.')
$record.coverage.unread = @('missing-source.md')
Write-Json $run $runPath
Write-Json $record $recordPath
& (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory | Out-Null
$checks++
$run.tasks[0].status = 'succeeded'
$run.tasks[0].attempts[0].status = 'succeeded'
$record.status = 'succeeded'; $record.gaps = @(); $record.coverage.unread = @()
Write-Json $record $recordPath
$run.tasks[0].role = 'mycroft-critic'
$run.tasks[0].depends_on = @('t-failed')
$run.tasks[0].allow_partial_dependencies = $true
Write-Json $run $runPath
& (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory | Out-Null
$checks++
$run.tasks[0].allow_partial_dependencies = $false
Write-Json $run $runPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'unsuccessful dependency'
$run.tasks[0].allow_partial_dependencies = $true
$run.Remove('gaps')
Write-Json $run $runPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'must describe gaps'
$run.gaps = @('A required source is inaccessible.')
$run.status = 'failed'
Write-Json $run $runPath
Write-Json @{ schema_version = 'mycroft.result.v1'; run_id = 'tooling-test'; status = 'failed'; report_path = 'report.md' } $resultPath
& (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory | Out-Null
$checks++
$record.sources[0].unexpected = 'extra field'
Write-Json $record $recordPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'unexpected field'
$record.sources[0].Remove('unexpected')
$record.sources[0].id = 't-evidence'
$record.claims[0].source_ids = @('t-evidence')
Write-Json $record $recordPath
Expect-Rejection { & (Join-Path $package 'Test-Run.ps1') -RunDirectory $runDirectory } 'must contain a task namespace'
Write-Output "Tooling regression checks passed: $checks assertions. Artifacts retained in $testRoot. Installation and record checks only; no model or Python launches."
