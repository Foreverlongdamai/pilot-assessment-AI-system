[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("setup", "validate", "diagrams", "build", "render-check", "all")]
    [string]$Action = "all",

    [ValidateSet("draft", "review", "released")]
    [string]$Status = "review",

    [string]$Language,

    [string]$DocumentId
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ToolRoot = $PSScriptRoot
$RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $ToolRoot "..\.."))
$Uv = Join-Path $RepositoryRoot ".tools\uv\uv.exe"
if (-not (Test-Path -LiteralPath $Uv)) {
    throw "Pinned repository uv is missing: $Uv"
}
function Invoke-UvPython {
    param([string]$Script, [string[]]$Arguments)
    & $Uv run --project $ToolRoot --frozen python (Join-Path $ToolRoot $Script) @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Script failed with exit code $LASTEXITCODE"
    }
}

function Find-Pnpm {
    if ($env:PILOT_ASSESSMENT_PNPM) {
        return $env:PILOT_ASSESSMENT_PNPM
    }
    $Command = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }
    throw "pnpm is required only to install the pinned Mermaid documentation renderer. Set PILOT_ASSESSMENT_PNPM or add pnpm.cmd to PATH."
}

function Install-DocumentationTools {
    $Pnpm = Find-Pnpm
    $PreviousSkip = $env:PUPPETEER_SKIP_DOWNLOAD
    try {
        $env:PUPPETEER_SKIP_DOWNLOAD = "true"
        & $Pnpm install --dir $ToolRoot --frozen-lockfile --ignore-scripts
        if ($LASTEXITCODE -ne 0) {
            throw "pnpm install failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        $env:PUPPETEER_SKIP_DOWNLOAD = $PreviousSkip
    }
    & $Uv sync --project $ToolRoot --frozen
    if ($LASTEXITCODE -ne 0) {
        throw "documentation Python toolchain sync failed with exit code $LASTEXITCODE"
    }
}

function Common-Arguments {
    $Arguments = @("--status", $Status)
    if ($Language) {
        $Arguments += @("--language", $Language)
    }
    if ($DocumentId) {
        $Arguments += @("--document-id", $DocumentId)
    }
    return $Arguments
}

switch ($Action) {
    "setup" { Install-DocumentationTools }
    "validate" { Invoke-UvPython "validate_manuals.py" (Common-Arguments) }
    "diagrams" { Invoke-UvPython "render_diagrams.py" @() }
    "build" { Invoke-UvPython "build_manuals.py" (Common-Arguments) }
    "render-check" { Invoke-UvPython "render_manuals.py" (Common-Arguments) }
    "all" {
        Invoke-UvPython "validate_manuals.py" (Common-Arguments)
        Invoke-UvPython "render_diagrams.py" @()
        Invoke-UvPython "build_manuals.py" (Common-Arguments)
        Invoke-UvPython "render_manuals.py" (Common-Arguments)
    }
}
