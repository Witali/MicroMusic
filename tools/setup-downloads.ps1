[CmdletBinding()]
param([string[]]$Id, [switch]$Offline, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildPrefix = [IO.Path]::GetFullPath((Join-Path $repo 'build')) + [IO.Path]::DirectorySeparatorChar
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'downloads.json') -Raw | ConvertFrom-Json
if ($manifest.schema -ne 'micromusic-downloads-v1') { throw 'Unknown download manifest schema.' }
foreach ($requested in $Id) {
    if ($requested -notin $manifest.assets.id) { throw "Unknown download ID: $requested" }
}

function Assert-DownloadHash([string]$Path, $Asset) {
    if ((Get-Item -LiteralPath $Path).Length -ne $Asset.bytes) { throw "Size mismatch: $($Asset.id)" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Asset.sha256) { throw "SHA-256 mismatch: $($Asset.id)" }
}

foreach ($asset in $manifest.assets) {
    if ($Id -and $asset.id -notin $Id) { continue }
    $uri = [Uri]$asset.url
    if (-not $uri.IsAbsoluteUri -or $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Query) {
        throw "Expected a canonical HTTPS URL without credentials or query parameters: $($asset.id)"
    }
    if ($asset.sha256 -notmatch '^[0-9a-f]{64}$' -or $asset.bytes -le 0) { throw "Invalid hash/size: $($asset.id)" }
    $file = [IO.Path]::GetFullPath((Join-Path $repo $asset.path))
    if (-not $file.StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Download must stay in build/: $($asset.id)" }
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        if ($Offline -or $CheckOnly) { throw "Download is not cached: $($asset.id)" }
        New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($file)) | Out-Null
        $partial = $file + '.partial'
        Write-Host "Downloading $($asset.id) $($asset.version)..."
        Invoke-WebRequest -Uri $uri -OutFile $partial -UseBasicParsing -TimeoutSec 1800
        Assert-DownloadHash $partial $asset
        Move-Item -LiteralPath $partial -Destination $file
    }
    Assert-DownloadHash $file $asset
    Write-Host "$($asset.id) $($asset.version): verified"
}
