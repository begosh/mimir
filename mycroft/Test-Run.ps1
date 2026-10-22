[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$RunDirectory)
$ErrorActionPreference = 'Stop'
$problems = New-Object 'Collections.Generic.List[string]'
function Fail([string]$message) { $problems.Add($message) }
function Is-Object($value) { return ($null -ne $value -and $value -is [pscustomobject]) }
function Is-Integer($value) { return ($value -is [int] -or $value -is [long]) }
function Check-Fields($value, [string[]]$fields, [string]$label, [switch]$Exact) {
    if (-not (Is-Object $value)) { Fail "$label must be an object."; return $false }
    foreach ($field in $fields) {
        if ($value.PSObject.Properties.Name -notcontains $field) { Fail "$label lacks $field." }
    }
    if ($Exact) { foreach ($field in $value.PSObject.Properties.Name) { if ($fields -notcontains $field) { Fail "$label has unexpected field: $field" } } }
    return $true
}
function Check-Strings($value, [string]$label) {
    if ($value -isnot [array]) { Fail "$label must be an array."; return $false }
    foreach ($item in $value) { if ($item -isnot [string] -or -not $item.Trim()) { Fail "$label contains an empty or non-string entry." } }
    return $true
}
function Read-Json([string]$path) {
    try {
        $text = Get-Content -LiteralPath $path -Raw
        if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) { return ($text | ConvertFrom-Json -DateKind String) }
        return ($text | ConvertFrom-Json)
    } catch { Fail "Invalid or missing JSON: $path"; return $null }
}
$runRoot = [IO.Path]::GetFullPath($RunDirectory)
$run = Read-Json (Join-Path $runRoot 'run.json')
if (-not (Check-Fields $run @('schema_version', 'run_id', 'status', 'limits', 'dispatches_used', 'tasks') 'run')) { throw ($problems -join "`n") }
if ($run.schema_version -ne 'mycroft.run.v1') { Fail 'Unsupported run schema.' }
if ($run.run_id -isnot [string] -or -not $run.run_id.Trim()) { Fail 'run_id must be a nonempty string.' }
if ($run.status -notin @('planned', 'running', 'partial', 'failed', 'completed', 'cancelled', 'interrupted')) { Fail 'Invalid run status.' }
if (Check-Fields $run.limits @('max_tasks', 'max_dispatches', 'max_concurrency') 'limits') {
    foreach ($name in @('max_tasks', 'max_dispatches', 'max_concurrency')) {
        if (-not (Is-Integer $run.limits.$name) -or $run.limits.$name -lt 1) { Fail "limits.$name must be a positive integer." }
    }
}
if ($run.limits.PSObject.Properties.Name -contains 'max_depth' -and (-not (Is-Integer $run.limits.max_depth) -or $run.limits.max_depth -lt 1)) { Fail 'limits.max_depth must be a positive integer.' }
if (-not (Is-Integer $run.dispatches_used) -or $run.dispatches_used -lt 0 -or $run.dispatches_used -gt $run.limits.max_dispatches) { Fail 'Dispatch counter is invalid or exceeds its cap.' }
if ($run.tasks -isnot [array] -or $run.tasks.Count -gt $run.limits.max_tasks) { Fail 'Tasks must be an array within the task cap.' }
$tasks = @{}; $attemptTotal = 0; $active = 0
foreach ($task in $run.tasks) {
    if (-not (Check-Fields $task @('id', 'role', 'depends_on', 'required_evidence', 'depth', 'status', 'attempts') 'task')) { continue }
    if ($task.id -isnot [string] -or $task.id -notmatch '^[a-zA-Z0-9][a-zA-Z0-9._-]*$' -or $tasks.ContainsKey($task.id)) { Fail "Invalid or duplicate task ID: $($task.id)"; continue }
    $tasks[$task.id] = $task
    if ($task.role -isnot [string] -or -not $task.role.Trim()) { Fail "Task $($task.id) has no role." }
    $null = Check-Strings $task.depends_on "Task $($task.id) dependencies"
    if (@($task.depends_on | Sort-Object -Unique).Count -ne $task.depends_on.Count) { Fail "Task $($task.id) repeats a dependency." }
    if ($task.required_evidence -isnot [bool]) { Fail "Task $($task.id) required_evidence must be boolean." }
    if (-not (Is-Integer $task.depth) -or $task.depth -lt 1 -or ($run.limits.PSObject.Properties.Name -contains 'max_depth' -and $task.depth -gt $run.limits.max_depth)) { Fail "Task $($task.id) has an invalid depth." }
    if ($task.status -notin @('planned', 'pending', 'ready', 'running', 'succeeded', 'partial', 'failed', 'blocked', 'invalid', 'cancelled', 'interrupted', 'pruned')) { Fail "Task $($task.id) has an invalid status." }
    if ($task.status -eq 'running') { $active++ }
    if (Is-Integer $task.attempts) {
        if ($task.attempts -lt 0) { Fail "Task $($task.id) has negative attempts." }
        $attemptTotal += $task.attempts
    } elseif ($task.attempts -is [array]) {
        $attemptTotal += $task.attempts.Count
        $receiptNumber = 0
        foreach ($receipt in $task.attempts) {
            $receiptNumber++
            if ($receipt -is [string]) {
                if ($receipt -notmatch '(^|[/\\])[^/\\]+\.json$') { Fail "Task $($task.id) attempt receipt must name a JSON path." }
            } elseif (Is-Object $receipt) {
                if (-not (Is-Integer $receipt.attempt) -or $receipt.attempt -ne $receiptNumber) { Fail "Task $($task.id) attempt receipt number is invalid." }
                if ($receipt.PSObject.Properties.Name -contains 'status' -and $receipt.status -notin @('reserved', 'running', 'succeeded', 'partial', 'failed', 'invalid', 'cancelled', 'interrupted')) { Fail "Task $($task.id) has invalid attempt receipt status." }
            } else { Fail "Task $($task.id) attempt receipt must be a path or object." }
        }
    } else { Fail "Task $($task.id) attempts must be a count or array." }
}
if ($attemptTotal -gt $run.dispatches_used) { Fail 'Recorded task attempts exceed dispatches_used.' }
if ($active -gt $run.limits.max_concurrency) { Fail 'Running tasks exceed max_concurrency.' }
foreach ($task in $tasks.Values) {
    foreach ($dependency in $task.depends_on) {
        if (-not $tasks.ContainsKey($dependency)) { Fail "Task $($task.id) has unknown dependency: $dependency"; continue }
        if ($dependency -eq $task.id) { Fail "Task $($task.id) depends on itself." }
        if ($task.status -in @('running', 'succeeded') -and $tasks[$dependency].status -ne 'succeeded') {
            $allowedPartial = $task.PSObject.Properties.Name -contains 'allow_partial_dependencies' -and $task.allow_partial_dependencies -eq $true -and $task.role -match 'critic' -and $tasks[$dependency].status -in @('partial', 'failed', 'invalid', 'cancelled', 'interrupted', 'blocked')
            if (-not $allowedPartial) { Fail "Task $($task.id) advanced with unsuccessful dependency: $dependency" }
        }
    }
}
$visited = @{}
function Visit([string]$id) {
    if ($visited[$id] -eq 'visiting') { Fail "Task graph cycle at $id"; return }
    if ($visited[$id] -eq 'done' -or -not $tasks.ContainsKey($id)) { return }
    $visited[$id] = 'visiting'
    foreach ($dependency in $tasks[$id].depends_on) { Visit $dependency }
    $visited[$id] = 'done'
}
foreach ($id in @($tasks.Keys)) { Visit $id }
if ($run.status -eq 'completed') {
    foreach ($task in $tasks.Values) {
        if (($task.required_evidence -and $task.status -ne 'succeeded') -or $task.status -notin @('succeeded', 'pruned')) { Fail "Completed run contains unsatisfied task: $($task.id)" }
    }
}
if ($run.status -in @('completed', 'partial', 'failed')) {
    $reportPath = Join-Path $runRoot 'report.md'
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf) -or -not (Get-Content -LiteralPath $reportPath -Raw).Trim()) { Fail 'Final run has no nonempty report.md.' }
    $result = Read-Json (Join-Path $runRoot 'result.json')
    if (Check-Fields $result @('schema_version', 'run_id', 'status', 'report_path') 'result') {
        if ($result.schema_version -ne 'mycroft.result.v1' -or $result.run_id -ne $run.run_id -or $result.status -cne $run.status) { Fail 'Final result has mismatching schema, run ID or status.' }
        if ($result.report_path -isnot [string] -or -not $result.report_path.Trim()) { Fail 'Result report_path must be nonempty.'
        } else {
            $resolvedReport = [IO.Path]::GetFullPath((Join-Path $runRoot $result.report_path))
            if ($resolvedReport -ne [IO.Path]::GetFullPath($reportPath)) { Fail 'Result report_path differs from published report.md.' }
        }
        if ($run.status -in @('partial', 'failed')) {
            $gapCount = 0
            foreach ($gapContainer in @($run, $result)) {
                if ($gapContainer.PSObject.Properties.Name -contains 'gaps') {
                    $null = Check-Strings $gapContainer.gaps 'Final publication gaps'
                    $gapCount += $gapContainer.gaps.Count
                }
            }
            if ($gapCount -eq 0) { Fail 'Partial or failed publication must describe gaps in run or result.' }
        }
    }
}
$records = @{}; $sourceIdentity = @{}; $claims = @{}; $storedCounts = @{}
$attemptFiles = @(Get-ChildItem -LiteralPath (Join-Path $runRoot 'attempts') -File -Filter '*.json' -ErrorAction SilentlyContinue)
foreach ($file in $attemptFiles) {
    $record = Read-Json $file.FullName
    if (-not (Check-Fields $record @('schema_version', 'run_id', 'task_id', 'attempt', 'status', 'answer', 'sources', 'claims', 'gaps', 'requests', 'issues', 'coverage') $file.Name -Exact)) { continue }
    if ($record.schema_version -ne 'mycroft.worker.v1') { Fail "Unsupported schema: $($file.Name)" }
    if ($record.run_id -ne $run.run_id -or $record.task_id -isnot [string] -or -not $tasks.ContainsKey($record.task_id) -or -not (Is-Integer $record.attempt) -or $record.attempt -lt 1) { Fail "Record identity does not match run/task: $($file.Name)"; continue }
    $key = "$($record.task_id)/$($record.attempt)"
    if ($records.ContainsKey($key)) { Fail "Duplicate task attempt: $key"; continue }
    $records[$key] = $record
    if (-not $storedCounts.ContainsKey($record.task_id)) { $storedCounts[$record.task_id] = 0 }
    $storedCounts[$record.task_id]++
    if ($file.BaseName -ne "$($record.task_id)-$($record.attempt)") { Fail "Attempt filename differs from record identity: $($file.Name)" }
    if ($record.status -notin @('succeeded', 'partial', 'failed')) { Fail "Invalid record status: $key" }
    if ($record.answer -isnot [string] -or ($record.status -eq 'succeeded' -and -not $record.answer.Trim())) { Fail "Invalid or empty successful answer: $key" }
    foreach ($field in @('sources', 'claims', 'gaps', 'requests', 'issues')) { if ($record.$field -isnot [array]) { Fail "$key.$field must be an array." } }
    $null = Check-Strings $record.gaps "$key gaps"
    if ($record.status -in @('partial', 'failed') -and $record.gaps.Count -eq 0) { Fail "$key must describe incomplete or failed work in gaps." }
    if (Check-Fields $record.coverage @('searched', 'read', 'unread', 'limitations') "$key coverage" -Exact) {
        foreach ($field in @('searched', 'read', 'unread', 'limitations')) { $null = Check-Strings $record.coverage.$field "$key coverage.$field" }
        if ($record.status -eq 'succeeded' -and $record.coverage.unread.Count -gt 0) { Fail "$key succeeded despite explicit unread scope." }
    }
    $sourceIds = @{}
    foreach ($source in $record.sources) {
        if (-not (Check-Fields $source @('id', 'locator', 'retrieval_type', 'retrieved_at', 'excerpt', 'span', 'identity') "$key source" -Exact)) { continue }
        if ($source.id -isnot [string] -or -not $source.id.Trim() -or $sourceIds.ContainsKey($source.id)) { Fail "$key has invalid or duplicate source ID."; continue }
        $sourceIds[$source.id] = $source
        if ($source.id -notmatch '^[^:]+:.+$') { Fail "$key source ID must contain a task namespace and local ID." }
        $namespace = ($source.id -split ':', 2)[0]
        if (-not $tasks.ContainsKey($namespace)) { Fail "$key source ID has unknown task namespace: $($source.id)" }
        if ($source.locator -isnot [string] -or -not $source.locator.Trim() -or $source.excerpt -isnot [string] -or -not $source.excerpt.Trim() -or $source.span -isnot [string] -or -not $source.span.Trim()) { Fail "$key source lacks locator, exact excerpt or span." }
        if ($source.retrieval_type -notin @('local_file', 'primary_document', 'web_page', 'search_snippet', 'abstract', 'worker_report')) { Fail "$key has invalid source retrieval type." }
        if ($null -eq $source.retrieved_at) { if ($record.gaps.Count -eq 0) { Fail "$key has unknown retrieval time without a gap." }
        } else {
            $timestamp = [DateTimeOffset]::MinValue
            if ($source.retrieved_at -isnot [string] -or $source.retrieved_at -notmatch '(Z|[+-]\d\d:\d\d)$' -or -not [DateTimeOffset]::TryParse($source.retrieved_at, [ref]$timestamp)) { Fail "$key has invalid retrieval timestamp." }
        }
        if ($null -ne $source.identity -and ($source.identity -isnot [string] -or -not $source.identity.Trim())) { Fail "$key has invalid source identity." }
        $identity = $source | ConvertTo-Json -Depth 20 -Compress
        if ($sourceIdentity.ContainsKey($source.id) -and $sourceIdentity[$source.id] -ne $identity) { Fail "Source ID reused with different record: $($source.id)" } else { $sourceIdentity[$source.id] = $identity }
    }
    $claimIds = @{}
    foreach ($claim in $record.claims) {
        if (-not (Check-Fields $claim @('id', 'text', 'source_ids', 'support_status', 'rationale') "$key claim" -Exact)) { continue }
        if ($claim.id -isnot [string] -or -not $claim.id.Trim() -or $claimIds.ContainsKey($claim.id)) { Fail "$key has invalid or duplicate claim ID."; continue }
        $claimIds[$claim.id] = $true
        $scopedClaimId = if ($claim.id.StartsWith("$($record.task_id):", [StringComparison]::Ordinal)) { $claim.id } else { "$($record.task_id):$($claim.id)" }
        $claims[$scopedClaimId] = $true
        if ($claim.text -isnot [string] -or -not $claim.text.Trim() -or $claim.rationale -isnot [string] -or -not $claim.rationale.Trim()) { Fail "$key has empty claim text or rationale." }
        $null = Check-Strings $claim.source_ids "$key claim sources"
        if ($claim.support_status -notin @('supported', 'inference', 'contradicted', 'unsupported')) { Fail "$key has invalid claim support status." }
        if ($claim.support_status -ne 'unsupported' -and $claim.source_ids.Count -eq 0) { Fail "$key claim requires source links." }
        $primary = $false
        foreach ($sourceId in $claim.source_ids) {
            if (-not $sourceIds.ContainsKey($sourceId)) { Fail "$key claim references unknown source: $sourceId"; continue }
            if ($sourceIds[$sourceId].retrieval_type -in @('local_file', 'primary_document', 'web_page')) { $primary = $true }
        }
        if ($claim.support_status -eq 'supported' -and -not $primary) { Fail "$key supported claim has discovery-only or absent evidence." }
    }
    foreach ($request in $record.requests) {
        if (Check-Fields $request @('question', 'source_scope', 'reason', 'stop_condition') "$key request" -Exact) {
            foreach ($field in @('question', 'reason', 'stop_condition')) { if ($request.$field -isnot [string] -or -not $request.$field.Trim()) { Fail "$key request.$field must be nonempty." } }
            $null = Check-Strings $request.source_scope "$key request source_scope"
        }
    }
    foreach ($issue in $record.issues) {
        if (Check-Fields $issue @('claim_ids', 'severity', 'description', 'source_ids', 'remedy') "$key issue" -Exact) {
            $null = Check-Strings $issue.claim_ids "$key issue claim_ids"
            $null = Check-Strings $issue.source_ids "$key issue source_ids"
            if ($issue.severity -notin @('material', 'minor') -or $issue.description -isnot [string] -or -not $issue.description.Trim() -or $issue.remedy -isnot [string] -or -not $issue.remedy.Trim()) { Fail "$key has invalid critic issue." }
            foreach ($sourceId in $issue.source_ids) { if (-not $sourceIds.ContainsKey($sourceId)) { Fail "$key issue references unknown source: $sourceId" } }
        }
    }
}
foreach ($record in $records.Values) {
    foreach ($issue in $record.issues) { foreach ($claimId in $issue.claim_ids) { if (-not $claims.ContainsKey($claimId)) { Fail "Issue references unknown claim: $claimId" } } }
}
foreach ($task in $tasks.Values) {
    $declared = if (Is-Integer $task.attempts) { $task.attempts } elseif ($task.attempts -is [array]) { $task.attempts.Count } else { 0 }
    if ($storedCounts[$task.id] -gt $declared) { Fail "Stored attempts exceed declared attempts for $($task.id)." }
    foreach ($key in @($records.Keys)) {
        $candidate = $records[$key]
        if ($candidate.task_id -eq $task.id -and $candidate.attempt -gt $declared) { Fail "Stored attempt number exceeds declared attempts: $key" }
    }
    if ($task.attempts -is [array]) {
        $receiptNumber = 0
        foreach ($receipt in $task.attempts) {
            $receiptNumber++
            $resultPath = if ($receipt -is [string]) { $receipt } elseif ($receipt.PSObject.Properties.Name -contains 'result_path') { $receipt.result_path } else { $null }
            if ($null -ne $resultPath) {
                if ($resultPath -isnot [string] -or -not $resultPath.Trim()) { Fail "Task $($task.id) has invalid attempt result_path."; continue }
                $resolved = [IO.Path]::GetFullPath((Join-Path $runRoot $resultPath))
                $expected = [IO.Path]::GetFullPath((Join-Path $runRoot "attempts/$($task.id)-$receiptNumber.json"))
                if ($resolved -ne $expected -or -not (Test-Path -LiteralPath $resolved -PathType Leaf)) { Fail "Task $($task.id) attempt result_path differs from assigned identity or is missing." }
            }
        }
    }
    if ($task.status -in @('succeeded', 'partial')) {
        $latest = "$($task.id)/$declared"
        if (-not $records.ContainsKey($latest) -or $records[$latest].status -ne $task.status) { Fail "Task $($task.id) lacks a matching latest admitted attempt." }
    }
}
if ($problems.Count) { throw ("Run structural validation failed:`n- " + ($problems -join "`n- ")) }
Write-Output "Run structural checks passed: $($tasks.Count) tasks, $($records.Count) stored attempts and $($run.dispatches_used) dispatches. Scope: JSON structure, identities, DAG, declared dispatch/depth/concurrency budgets, publication and source links; raw worker input/output character bounds are unavailable and were not checked. No source retrieval, snapshot comparison, excerpt verification, citation entailment, factual truth or live-agent cleanup checks."
