[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][ValidateSet('codex', 'claude', 'opencode')][string]$Harness,
    [Parameter(Mandatory = $true)][string]$ProjectRoot
)
$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
$project = [IO.Path]::GetFullPath($ProjectRoot)
if (-not (Test-Path -LiteralPath $project -PathType Container)) {
    throw "ProjectRoot must be an existing project directory: $project"
}
$separator = [IO.Path]::DirectorySeparatorChar
$projectPrefix = $project.TrimEnd([char[]]@('/', '\')) + $separator
$skillTarget = if ($Harness -eq 'claude') { '.claude/skills' } else { '.agents/skills' }
$adapterTarget = @{ codex = '.codex/agents'; claude = '.claude/agents'; opencode = '.opencode/agents' }[$Harness]
$copies = @()
foreach ($pair in @(@('skills', $skillTarget), @("adapters/$Harness", $adapterTarget))) {
    $sourceRoot = Join-Path $packageRoot $pair[0]
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) { throw "Missing package directory: $sourceRoot" }
    foreach ($file in Get-ChildItem -LiteralPath $sourceRoot -File -Recurse) {
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Linked package file rejected: $($file.FullName)" }
        $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart([char[]]@('/', '\'))
        $destination = [IO.Path]::GetFullPath((Join-Path (Join-Path $project $pair[1]) $relative))
        if (-not $destination.StartsWith($projectPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Destination escapes ProjectRoot: $destination" }
        if (Test-Path -LiteralPath $destination) { throw "Installation refuses an existing destination: $destination" }
        $ancestor = Split-Path -Parent $destination
        while ($ancestor.Length -ge $project.Length) {
            if (Test-Path -LiteralPath $ancestor) {
                $item = Get-Item -LiteralPath $ancestor -Force
                if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "Destination ancestor is a file or link: $ancestor"
                }
            }
            if ($ancestor -eq $project) { break }
            $ancestor = Split-Path -Parent $ancestor
        }
        $copies += [pscustomobject]@{ Source = $file.FullName; Destination = $destination }
    }
}
if (-not $copies.Count) { throw 'Package has no installable files.' }
if ($PSCmdlet.ShouldProcess($project, "Copy $($copies.Count) Mycroft files for $Harness (no overwrite)")) {
    foreach ($copy in $copies) {
        [IO.Directory]::CreateDirectory((Split-Path -Parent $copy.Destination)) | Out-Null
        [IO.File]::Copy($copy.Source, $copy.Destination, $false)
    }
    Write-Output "Installed $($copies.Count) Mycroft files for $Harness into $project. Copy installation is not atomic; provider configuration was not edited."
}
