[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Test-Package.ps1')
& (Join-Path $PSScriptRoot 'Build-Adapters.ps1') -Check
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'plugin.json') -Raw | ConvertFrom-Json
if ($manifest.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid package version.' }
$dist = Join-Path $PSScriptRoot 'dist'
[IO.Directory]::CreateDirectory($dist) | Out-Null
$archive = Join-Path $dist ("mycroft-{0}.zip" -f $manifest.version)
$hashPath = "$archive.sha256"
if ((Test-Path -LiteralPath $archive) -or (Test-Path -LiteralPath $hashPath)) { throw "Build refuses existing archive or hash sidecar: $archive" }
$files = @()
foreach ($name in @('README.md', 'plugin.json')) { $files += Get-Item -LiteralPath (Join-Path $PSScriptRoot $name) }
$files += Get-ChildItem -LiteralPath $PSScriptRoot -File -Filter '*.ps1'
foreach ($name in @('skills', 'adapters', 'docs', 'tests')) {
    $files += Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot $name) -File -Recurse
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stream = [IO.File]::Open($archive, [IO.FileMode]::CreateNew)
$zip = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Create, $false)
try {
    foreach ($file in $files | Sort-Object FullName -Unique) {
        $relative = $file.FullName.Substring($PSScriptRoot.Length).TrimStart([char[]]@('/', '\')).Replace('\', '/')
        if ($relative -match '(^|/)(dist|\.mycroft)(/|$)' -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Excluded or linked archive entry: $relative"
        }
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $relative, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally { $zip.Dispose(); $stream.Dispose() }
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($hashPath, "$hash  $([IO.Path]::GetFileName($archive))`n", (New-Object Text.UTF8Encoding($false)))
Write-Output "Created $archive ($($files.Count) allowlisted files); SHA256 $hash"
