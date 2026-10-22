<#
.SYNOPSIS
    M Í M I R // Agent Skill Installer for Windows PowerShell
.DESCRIPTION
    Installs one shared Mímir package under .agents/skills and creates directory
    junctions for the CLI skill locations, globally or project-locally.
.EXAMPLE
    .\install.ps1 -Global
.EXAMPLE
    .\install.ps1 -Project "C:\path\to\my-project"
.EXAMPLE
    irm https://raw.githubusercontent.com/begosh/mimir/main/install.ps1 | iex
#>

[CmdletBinding()]
param(
    [switch]$Global = $true,
    [string]$Project,
    [ValidateSet("all", "codex", "antigravity", "claude", "opencode", "agents")]
    [string]$Target = "all",
    [switch]$Link,
    [switch]$Research,
    [switch]$SkipPip
)

$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/begosh/mimir.git"
$ScriptDir = $null
$TempDir = $null
$InstallerExitCode = 1

try {
    # Invoke-Expression of downloaded script text has no command file path.
    # Resolve local execution only when a path exists, within failure handling.
    if ($MyInvocation.MyCommand.Path) {
        $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    if ($ScriptDir -and (Test-Path (Join-Path $ScriptDir "scripts\install.py"))) {
        $Installer = Join-Path $ScriptDir "scripts\install.py"
    } else {
        Write-Host "[*] Fetching Mímir repository..." -ForegroundColor Cyan
        $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("mimir_install_" + [System.Guid]::NewGuid().ToString("N"))
        git clone --depth 1 $RepoUrl $TempDir | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not fetch the Mímir repository." }
        $Installer = Join-Path $TempDir "scripts\install.py"
    }

    $PyBin = $null
    $PyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($PyCmd) {
        $PyBin = $PyCmd.Source
    } else {
        $PyCmd = Get-Command py -ErrorAction SilentlyContinue
        if ($PyCmd) {
            $PyBin = $PyCmd.Source
        }
    }

    if (-not $PyBin) {
        Write-Error "Python 3 is required to install Mímir but was not found in PATH."
        exit 1
    }

    $ArgsList = @($Installer)
    if ($Research) { $ArgsList += "--research" }

    if ($Project) {
        $ArgsList += @("--project", $Project)
    } elseif ($Global) {
        $ArgsList += "--global"
    }

    if ($Target) {
        $ArgsList += @("--target", $Target)
    }

    if ($Link) {
        if ($TempDir) { throw "-Link requires a persistent local checkout; downloaded temporary files cannot be linked." }
        $ArgsList += "--link"
    }

    if ($SkipPip) {
        $ArgsList += "--skip-pip"
    }

    & $PyBin $ArgsList
    $InstallerExitCode = $LASTEXITCODE
}
finally {
    if ($TempDir -and (Test-Path $TempDir)) {
        $ResolvedTempDir = (Resolve-Path -LiteralPath $TempDir).Path
        $ExpectedTempParent = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\')
        if ((Split-Path -Parent $ResolvedTempDir).TrimEnd('\') -eq $ExpectedTempParent -and
            (Split-Path -Leaf $ResolvedTempDir) -like 'mimir_install_*') {
            Remove-Item -LiteralPath $ResolvedTempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
exit $InstallerExitCode
