<#
.SYNOPSIS
    M Í M I R // Agent Skill Installer for Windows PowerShell
.DESCRIPTION
    Installs Mímir into OpenAI Codex CLI, Antigravity CLI, Claude Code, and skills.sh
    either globally (~/.codex, ~/.gemini, ~/.agents) or project-locally.
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
    [ValidateSet("all", "codex", "antigravity", "claude", "agents")]
    [string]$Target = "all",
    [switch]$Link,
    [switch]$SkipPip
)

$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/begosh/mimir.git"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path 2>$null
$TempDir = $null

try {
    if ($ScriptDir -and (Test-Path (Join-Path $ScriptDir "scripts\install.py"))) {
        $Installer = Join-Path $ScriptDir "scripts\install.py"
    } else {
        Write-Host "[*] Fetching Mímir repository..." -ForegroundColor Cyan
        $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("mimir_install_" + [System.Guid]::NewGuid().ToString("N"))
        git clone --depth 1 $RepoUrl $TempDir | Out-Null
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

    if ($Project) {
        $ArgsList += @("--project", $Project)
    } elseif ($Global) {
        $ArgsList += "--global"
    }

    if ($Target) {
        $ArgsList += @("--target", $Target)
    }

    if ($Link) {
        $ArgsList += "--link"
    }

    if ($SkipPip) {
        $ArgsList += "--skip-pip"
    }

    & $PyBin $ArgsList
}
finally {
    if ($TempDir -and (Test-Path $TempDir)) {
        Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue
    }
}
