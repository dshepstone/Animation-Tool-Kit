<#
.SYNOPSIS
    Packages an Animation Tool Kit (ATK) release for GitHub.

.DESCRIPTION
    1. Syncs the release files from the repo root into dist\ (the same
       layout as previous releases), leaving out __pycache__ and *.pyc.
    2. Builds dist\AnimationToolKit_v<version>.zip from dist\ with
       forward-slash entry names, so it unzips correctly on Windows,
       macOS and Linux.
    3. Prints the zip size, file count and SHA-256, plus the git and
       GitHub commands to publish the release.

    Works in Windows PowerShell 5.1 and PowerShell 7+.

.PARAMETER Version
    Release version, for example 1.1.5.

.PARAMETER SkipDistSync
    Zip dist\ as it is, without copying the repo root files into it first.

.PARAMETER Force
    Overwrite an existing zip for the same version.

.EXAMPLE
    .\package_atk_release.ps1 -Version 1.1.5

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\package_atk_release.ps1 -Version 1.1.5 -Force
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [switch]$SkipDistSync,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$RepoRoot = $PSScriptRoot
$DistDir  = Join-Path $RepoRoot 'dist'
$ZipName  = "AnimationToolKit_v$($Version -replace '\.', '_').zip"
$ZipPath  = Join-Path $DistDir $ZipName

# Everything that ships in the release zip (relative to the repo root).
$ReleaseFiles = @(
    'ATK_LICENSE.md',
    'README.md',
    'THIRD_PARTY_NOTICES.md',
    'install_atk_toolbar.mel'
)
$ReleaseFolders = @(
    'animation tool kit scripts',
    'atk_toolbar'
)

# Never shipped.
$ExcludeDirs  = @('__pycache__', '.git')
$ExcludeFiles = @('*.pyc', '*.pyo', '.DS_Store', 'Thumbs.db')

function Test-Excluded([System.IO.FileInfo]$File, [string]$Root) {
    $relative = $File.FullName.Substring($Root.Length).TrimStart('\', '/')
    foreach ($part in ($relative -split '[\\/]')) {
        if ($ExcludeDirs -contains $part) { return $true }
    }
    foreach ($pattern in $ExcludeFiles) {
        if ($File.Name -like $pattern) { return $true }
    }
    return $false
}

Write-Host ''
Write-Host "Packaging Animation Tool Kit v$Version" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
foreach ($item in $ReleaseFiles + $ReleaseFolders) {
    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot $item))) {
        throw "Missing release item: $item (run this script from the repo root)."
    }
}

if ((Test-Path -LiteralPath $ZipPath) -and -not $Force) {
    throw "$ZipName already exists. Use -Force to overwrite it."
}

$notes = Join-Path $RepoRoot "Animation_Tool_Kit_v$($Version)_Release_Notes.md"
if (-not (Test-Path -LiteralPath $notes)) {
    Write-Warning "No release notes found at $(Split-Path $notes -Leaf)."
    $notes = $null
}

if (Get-Command git -ErrorAction SilentlyContinue) {
    $dirty = git -C $RepoRoot status --porcelain -- $ReleaseFiles $ReleaseFolders 2>$null
    if ($dirty) {
        Write-Warning 'Release files have uncommitted changes; the zip will include them:'
        $dirty | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    }
}

# ---------------------------------------------------------------------------
# 1. Sync repo root -> dist\
# ---------------------------------------------------------------------------
if (-not $SkipDistSync) {
    Write-Host ''
    Write-Host 'Syncing release files into dist\ ...' -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

    foreach ($file in $ReleaseFiles) {
        Copy-Item -LiteralPath (Join-Path $RepoRoot $file) -Destination $DistDir -Force
        Write-Host "  $file"
    }

    foreach ($folder in $ReleaseFolders) {
        $src = Join-Path $RepoRoot $folder
        $dst = Join-Path $DistDir  $folder

        # Mirror the folder so files removed from the repo are removed from dist too.
        if (Test-Path -LiteralPath $dst) {
            Remove-Item -LiteralPath $dst -Recurse -Force
        }
        $srcRoot = (Resolve-Path -LiteralPath $src).Path
        $count = 0
        Get-ChildItem -LiteralPath $src -Recurse -File -Force |
            Where-Object { -not (Test-Excluded $_ $srcRoot) } |
            ForEach-Object {
                $relative = $_.FullName.Substring($srcRoot.Length).TrimStart('\', '/')
                $target   = Join-Path $dst $relative
                New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $target -Force
                $count++
            }
        Write-Host "  $folder\ ($count files)"
    }
}

# ---------------------------------------------------------------------------
# 2. Build the zip from dist\
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host "Creating $ZipName ..." -ForegroundColor Cyan

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

$distRoot = (Resolve-Path -LiteralPath $DistDir).Path
$entries = @()
foreach ($item in $ReleaseFiles + $ReleaseFolders) {
    $path = Join-Path $distRoot $item
    if (-not (Test-Path -LiteralPath $path)) {
        throw "dist\ is missing $item. Run without -SkipDistSync."
    }
    if (Test-Path -LiteralPath $path -PathType Container) {
        $entries += Get-ChildItem -LiteralPath $path -Recurse -File -Force |
            Where-Object { -not (Test-Excluded $_ $distRoot) }
    } else {
        $entries += Get-Item -LiteralPath $path
    }
}

$zip = [System.IO.Compression.ZipFile]::Open($ZipPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in $entries) {
        # Zip entries must use forward slashes to extract correctly everywhere.
        $entryName = $file.FullName.Substring($distRoot.Length).TrimStart('\', '/') -replace '\\', '/'
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip, $file.FullName, $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
}
finally {
    $zip.Dispose()
}

# ---------------------------------------------------------------------------
# 3. Summary
# ---------------------------------------------------------------------------
$zipInfo = Get-Item -LiteralPath $ZipPath
$hash    = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash
$sizeMB  = [math]::Round($zipInfo.Length / 1MB, 2)

Write-Host ''
Write-Host 'Release package ready' -ForegroundColor Green
Write-Host "  File:    $ZipPath"
Write-Host "  Size:    $sizeMB MB"
Write-Host "  Files:   $($entries.Count)"
Write-Host "  SHA-256: $hash"

$tag = "ATK_$Version"
$notesArg = if ($notes) { "--notes-file `"$(Split-Path $notes -Leaf)`"" } else { '--generate-notes' }
Write-Host ''
Write-Host 'Next steps to publish on GitHub:' -ForegroundColor Cyan
Write-Host "  git add dist"
Write-Host "  git commit -m `"Release v$Version`""
Write-Host "  git tag $tag"
Write-Host "  git push origin main --tags"
Write-Host ''
Write-Host '  Then either upload the zip at https://github.com/dshepstone/Animation-Tool-Kit/releases/new'
Write-Host '  or, with the GitHub CLI:'
Write-Host "  gh release create $tag `"dist/$ZipName`" --title `"Animation Tool Kit v$Version`" $notesArg"
Write-Host ''
