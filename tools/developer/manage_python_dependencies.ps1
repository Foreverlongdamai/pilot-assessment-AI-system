[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("list", "add", "remove", "sync")]
    [string]$Action = "list",

    [Parameter(Position = 1)]
    [string]$Package
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProductRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$BackendRoot = Join-Path $ProductRoot "backend"
$Python = Join-Path $ProductRoot "runtime\python\python.exe"
$SitePackages = Join-Path $ProductRoot "runtime\site-packages"
$Uv = Join-Path $PSScriptRoot "uv.exe"

foreach ($RequiredPath in @(
    $Python,
    $Uv,
    (Join-Path $BackendRoot "pyproject.toml"),
    (Join-Path $BackendRoot "uv.lock"),
    $SitePackages
)) {
    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        throw "This tool must run from an unpacked Pilot Assessment product: missing $RequiredPath"
    }
}

function Invoke-Uv {
    param([string[]]$UvArguments)

    & $Uv --quiet @UvArguments
    if ($LASTEXITCODE -ne 0) {
        throw "uv failed with exit code $LASTEXITCODE"
    }
}

function Invoke-DependencySync {
    $Requirements = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) ("pilot-assessment-runtime-{0}.txt" -f [guid]::NewGuid().ToString("N"))
    try {
        Invoke-Uv @(
            "export",
            "--project", $BackendRoot,
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--format", "requirements.txt",
            "--output-file", $Requirements,
            "--no-python-downloads"
        )
        Invoke-Uv @(
            "pip", "sync",
            "--target", $SitePackages,
            "--python-version", "3.11",
            "--python-platform", "x86_64-pc-windows-msvc",
            "--require-hashes",
            "--no-python-downloads",
            $Requirements
        )
    }
    finally {
        Remove-Item -LiteralPath $Requirements -Force -ErrorAction SilentlyContinue
    }
}

switch ($Action) {
    "list" {
        & $Python -I -B -X utf8 -c @"
import importlib.metadata
for distribution in sorted(importlib.metadata.distributions(), key=lambda item: (item.metadata.get('Name') or '').casefold()):
    name = distribution.metadata.get('Name')
    if name:
        print(f'{name}=={distribution.version}')
"@
        if ($LASTEXITCODE -ne 0) {
            throw "private Python dependency listing failed with exit code $LASTEXITCODE"
        }
    }
    "add" {
        if ([string]::IsNullOrWhiteSpace($Package)) {
            throw "add requires a package requirement, for example: add 'package-name>=1,<2'"
        }
        Invoke-Uv @(
            "add",
            "--project", $BackendRoot,
            "--python", $Python,
            "--no-sync",
            "--no-python-downloads",
            $Package
        )
        Invoke-DependencySync
        Write-Host "Dependency added and private runtime synchronized. Restart the application."
    }
    "remove" {
        if ([string]::IsNullOrWhiteSpace($Package)) {
            throw "remove requires the project dependency name"
        }
        Invoke-Uv @(
            "remove",
            "--project", $BackendRoot,
            "--python", $Python,
            "--no-sync",
            "--no-python-downloads",
            $Package
        )
        Invoke-DependencySync
        Write-Host "Dependency removed and private runtime synchronized. Restart the application."
    }
    "sync" {
        Invoke-DependencySync
        Write-Host "Private runtime synchronized with backend/uv.lock. Restart the application."
    }
}
