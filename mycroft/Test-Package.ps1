[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$problems = New-Object 'Collections.Generic.List[string]'
function Fail([string]$message) { $problems.Add($message) }
$root = $PSScriptRoot
$skills = @('mycroft', 'mycroft-corpus', 'mycroft-optimize')
foreach ($name in $skills) {
    $path = Join-Path $root "skills/$name/SKILL.md"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { Fail "Missing skill: $name"; continue }
    $content = Get-Content -LiteralPath $path -Raw
    if ($content -notmatch '(?s)\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)') { Fail "Invalid skill frontmatter: $name"; continue }
    $frontmatter = $Matches[1]
    if ($frontmatter -notmatch "(?m)^name:\s*$([regex]::Escape($name))\s*$") { Fail "Incorrect skill name: $name" }
    if ($frontmatter -notmatch '(?m)^description:\s*\S.+$') { Fail "Missing skill description: $name" }
}
$actualSkills = @(Get-ChildItem -LiteralPath (Join-Path $root 'skills') -Directory -ErrorAction SilentlyContinue)
if ($actualSkills.Count -ne 3) { Fail 'Package must contain exactly three skills.' }
$files = @(Get-ChildItem -LiteralPath $root -File | Where-Object { $_.Extension -in @('.md', '.json', '.ps1') })
foreach ($directory in @('skills', 'adapters', 'docs', 'tests')) {
    $path = Join-Path $root $directory
    if (-not (Test-Path -LiteralPath $path -PathType Container)) { Fail "Missing package directory: $directory"; continue }
    $files += Get-ChildItem -LiteralPath $path -File -Recurse
}
foreach ($file in $files) {
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Fail "Linked package file: $($file.FullName)"; continue }
    $content = Get-Content -LiteralPath $file.FullName -Raw
    if ($content -match '(?i)(?:[A-Z]:[\\/]Users[\\/]\w|/home/[a-zA-Z0-9]|/Users/[a-zA-Z0-9])') { Fail "Machine-specific path in $($file.Name)" }
    if ($file.Extension -eq '.json') {
        try { $null = $content | ConvertFrom-Json } catch { Fail "Invalid JSON: $($file.FullName)" }
    }
    if ($file.Extension -eq '.ps1') {
        $tokens = $null; $parseErrors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$parseErrors)
        foreach ($error in $parseErrors) { Fail "PowerShell parse error in $($file.Name): $($error.Message)" }
        foreach ($command in $ast.FindAll({ param($node) $node -is [Management.Automation.Language.CommandAst] }, $true)) {
            $commandName = $command.GetCommandName()
            if ($commandName -and ([IO.Path]::GetFileName($commandName) -match '^(?i:python[0-9.]*|py|codex|claude|opencode|dspy|mimir)(?:\.exe)?$' -or $commandName -in @('Start-Process', 'Invoke-Expression'))) {
                Fail "External model, Python or dynamic process launcher in $($file.Name): $commandName"
            }
        }
    }
    if ($file.Extension -eq '.md') {
        foreach ($match in [regex]::Matches($content, '\]\(([^)\r\n]+)\)')) {
            $target = $match.Groups[1].Value.Trim()
            if ($target.StartsWith('<')) { $target = $target.Trim([char[]]@('<', '>')) }
            if ($target -match '^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|#)' -or $target -match '\$|<|>') { continue }
            $target = ($target -split '#', 2)[0]
            if (-not $target) { continue }
            try {
                $resolved = [IO.Path]::GetFullPath((Join-Path $file.DirectoryName ([Uri]::UnescapeDataString($target))))
                if (-not (Test-Path -LiteralPath $resolved)) { Fail "Broken link in $($file.Name): $target" }
            } catch { Fail "Invalid link in $($file.Name): $target" }
        }
    }
}
foreach ($harness in @('codex', 'claude', 'opencode')) {
    $extension = if ($harness -eq 'codex') { '.toml' } else { '.md' }
    $adapters = @(Get-ChildItem -LiteralPath (Join-Path $root "adapters/$harness") -File -Filter "*$extension" -ErrorAction SilentlyContinue)
    if ($adapters.Count -ne 7) { Fail "$harness must supply seven role adapters." }
}
if ($problems.Count) { throw ("Package validation failed:`n- " + ($problems -join "`n- ")) }
Write-Output "Package structural checks passed: three skills, JSON, local Markdown links, PowerShell syntax and seven adapters per harness. No live harness or evidence-entailment checks performed."
