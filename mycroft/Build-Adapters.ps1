[CmdletBinding()]
param([switch]$Check)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$roles = @{
    'investigator' = 'Investigate primary evidence and current behavior within a bounded question.'
    'alternatives' = 'Investigate competing explanations, constraints and evidence-backed alternatives.'
    'corpus-worker' = 'Analyze assigned corpus slices with exact source spans and coverage.'
    'critic' = 'Challenge admitted material claims against underlying evidence.'
    'reconciler' = 'Reconcile admitted claims and critique when explicitly delegated by the host.'
    'evaluator' = 'Investigate a blinded evaluation case without expected answers or grader access.'
    'evolver' = 'Propose a data-only instruction change from train/dev feedback only.'
}
foreach ($role in @($roles.Keys | Sort-Object)) {
    $promptPath = Join-Path $PSScriptRoot "skills/mycroft/references/roles/$role.md"
    $prompt = [IO.File]::ReadAllText($promptPath).Replace("`r`n", "`n").TrimEnd()
    $name = "mycroft-$role"
    $description = $roles[$role]
    $toml = "name = `"$name`"`ndescription = `"$description`"`ndeveloper_instructions = '''`n$prompt`n'''`n"
    $claude = "---`nname: $name`ndescription: $description`nmodel: inherit`n---`n`n$prompt`n"
    $opencode = "---`ndescription: $description`nmode: subagent`npermission:`n  edit: deny`n  task: deny`n---`n`n$prompt`n"
    foreach ($entry in @(@('codex', 'toml', $toml), @('claude', 'md', $claude), @('opencode', 'md', $opencode))) {
        $destination = Join-Path $PSScriptRoot "adapters/$($entry[0])/$name.$($entry[1])"
        if ($Check) {
            if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) { throw "Missing adapter: $destination" }
            $actual = [IO.File]::ReadAllText($destination).Replace("`r`n", "`n")
            if ($actual -cne $entry[2]) { throw "Adapter drift: $destination" }
        } else {
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
            [IO.File]::WriteAllText($destination, $entry[2], $utf8)
        }
    }
}
if ($Check) { Write-Output 'All 21 adapters match the seven canonical role prompts.' }
else { Write-Output 'Generated 21 adapters from seven canonical role prompts.' }
