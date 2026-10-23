[CmdletBinding()]
param([switch]$Offline, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ([Environment]::OSVersion.Platform -ne 'Win32NT' -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'This setup installs Windows x64 tools.'
}
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$toolRoot = Join-Path $repo 'build/toolchains'
$cache = Join-Path $toolRoot 'downloads'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'toolchains-windows-x64.json') -Raw | ConvertFrom-Json
if ($manifest.schema -ne 'micromusic-toolchains-v1') { throw 'Unknown toolchain manifest schema' }
if (-not $CheckOnly) { New-Item -ItemType Directory -Force -Path $cache | Out-Null }
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Get-VerifiedArchive($Package) {
    $file = Join-Path $cache $Package.archiveName
    if (-not (Test-Path -LiteralPath $file)) {
        if ($Offline) { throw "Archive is not cached: $file" }
        Write-Host "Downloading $($Package.name) $($Package.version)..."
        $partial = $file + '.partial'
        Invoke-WebRequest -Uri $Package.url -OutFile $partial -UseBasicParsing -TimeoutSec 1800
        $actual = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $Package.sha256) { throw "SHA-256 mismatch: $partial" }
        Move-Item -LiteralPath $partial -Destination $file
    }
    $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Package.sha256) { throw "SHA-256 mismatch: $file; remove this archive and retry." }
    return $file
}
function Expand-VerifiedArchive([string]$Archive, [string]$Destination, [string]$ArchiveRoot) {
    $absolute = [IO.Path]::GetFullPath($Destination)
    if (-not $absolute.StartsWith($toolRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Destination is outside build/toolchains: $absolute"
    }
    New-Item -ItemType Directory -Force -Path $absolute | Out-Null
    $prefix = if ($ArchiveRoot) { $ArchiveRoot + '/' } else { '' }
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('\','/')
            if ($name -match '^[/\\]|^[A-Za-z]:' -or ($name.Split('/') -contains '..')) { throw "Unsafe archive path: $name" }
            if ($prefix) {
                if (-not $name.StartsWith($prefix, [StringComparison]::Ordinal)) { throw "Unexpected archive root: $name" }
                $name = $name.Substring($prefix.Length)
            }
            if (-not $name) { continue }
            $target = [IO.Path]::GetFullPath((Join-Path $absolute $name))
            if (-not $target.StartsWith($absolute + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe target: $target" }
            if ($name.EndsWith('/')) { New-Item -ItemType Directory -Force -Path $target | Out-Null; continue }
            New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($target)) | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $true)
        }
    } finally { $zip.Dispose() }
}
foreach ($package in $manifest.packages) {
    $destination = Join-Path $toolRoot $package.install
    $stamp = Join-Path $destination 'micromusic-package.json'
    $installed = $false
    if (Test-Path -LiteralPath $stamp) {
        $saved = Get-Content -LiteralPath $stamp -Raw | ConvertFrom-Json
        $installed = $saved.sha256 -eq $package.sha256
        foreach ($required in $package.required) { if (-not (Test-Path -LiteralPath (Join-Path $destination $required))) { $installed = $false } }
    }
    if (-not $installed) {
        if ($CheckOnly) { throw "Toolchain is not installed: $($package.name)" }
        $archive = Get-VerifiedArchive $package
        Write-Host "Extracting $($package.name) $($package.version)..."
        Expand-VerifiedArchive $archive $destination $package.archiveRoot
        foreach ($required in $package.required) {
            if (-not (Test-Path -LiteralPath (Join-Path $destination $required))) { throw "Missing toolchain file: $required" }
        }
        $package | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $stamp -Encoding UTF8
    }
    Write-Host "$($package.name) $($package.version): ready"
}
if (-not $CheckOnly) {
    # The embedded Python distribution needs the repository's tools directory.
    Set-Content -LiteralPath (Join-Path $toolRoot 'python-3.13.3/python313._pth') -Encoding ASCII -Value @(
        'python313.zip', '.', '../../../tools', 'import site'
    )
    $envSource = @'
$taskToolchainRoot = $PSScriptRoot
$env:EMSDK = Join-Path $taskToolchainRoot 'emscripten-6.0.12'
$taskToolBins = @(
    (Join-Path $taskToolchainRoot 'node-22.22.3'),
    (Join-Path $taskToolchainRoot 'python-3.13.3'),
    (Join-Path $taskToolchainRoot 'avr-7.3.0/bin'),
    (Join-Path $env:EMSDK 'upstream/bin')
)
$env:PATH = ($taskToolBins -join [IO.Path]::PathSeparator) + [IO.Path]::PathSeparator + $env:PATH
'@
    Set-Content -LiteralPath (Join-Path $toolRoot 'env.ps1') -Value $envSource -Encoding UTF8
}
. (Join-Path $toolRoot 'env.ps1')
& (Join-Path $toolRoot 'node-22.22.3/node.exe') (Join-Path $PSScriptRoot 'verify-toolchains.mjs') --root $toolRoot
if ($LASTEXITCODE -ne 0) { throw 'Toolchain verification failed.' }
Write-Host "Ready. In a new PowerShell, run: . ./build/toolchains/env.ps1"
