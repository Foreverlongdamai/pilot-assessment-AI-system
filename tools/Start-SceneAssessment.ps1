param(
    [switch]$Build,
    [switch]$LegacyWorkbench
)

$ErrorActionPreference = 'Stop'
$taskRepository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskProject = Join-Path $taskRepository 'src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj'
$taskOutput = Join-Path $taskRepository 'src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio'
$taskExecutable = Join-Path $taskOutput 'PilotAssessment.Desktop.exe'

if ($Build -or -not (Test-Path -LiteralPath $taskExecutable)) {
    & dotnet build $taskProject -c Debug -p:Platform=x64 "-p:OutDir=$taskOutput/" --nologo
    if ($LASTEXITCODE -ne 0) {
        throw '桌面程序构建失败，请查看上方输出。'
    }
}

if (-not (Test-Path -LiteralPath $taskExecutable)) {
    throw "未找到桌面程序：$taskExecutable"
}

# This script is an interactive launcher, intentionally showing the requested app.
$taskLaunch = @{
    FilePath = $taskExecutable
    WorkingDirectory = $taskRepository
    WindowStyle = 'Normal'
    PassThru = $true
}
if ($LegacyWorkbench) {
    $taskLaunch.ArgumentList = @('--legacy-workbench')
}
$taskProcess = Start-Process @taskLaunch
Write-Output "已启动 Pilot Assessment，进程 $($taskProcess.Id)。"
