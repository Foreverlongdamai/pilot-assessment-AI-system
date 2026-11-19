$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../scene_v3_qa/RefinementQa.ps1"
$repository = (Resolve-Path "$PSScriptRoot/../..").Path
Start-Process -FilePath 'C:\Users\long\Desktop\PilotAssessment.Desktop.exe - 快捷方式.lnk' -WindowStyle Normal
$process = $null
for ($attempt=0; $attempt -lt 60; $attempt++) {
    $process = Get-Process PilotAssessment.Desktop -ErrorAction SilentlyContinue
    if ($process -and $process.MainWindowHandle -ne 0) { break }
    Start-Sleep -Milliseconds 100
}
if (-not $process) { throw 'Application did not start' }
$processId = $process.Id
function Wait-Control([string]$Name, [string]$Type='') {
    for ($attempt=0; $attempt -lt 100; $attempt++) {
        try { return Find-SceneControl (Get-SceneWindow $processId) $Name $Type } catch { Start-Sleep -Milliseconds 100 }
    }
    throw "Control not ready: $Name"
}
function Open-DemoFile([string]$Button, [string]$Path) {
    Invoke-SceneControl (Wait-Control $Button 'ControlType.Button')
    [void](Wait-Control '打开' 'ControlType.Window')
    Complete-SceneFileDialog $processId $Path
    for ($attempt=0; $attempt -lt 100; $attempt++) {
        try { [void](Find-SceneControl (Get-SceneWindow $processId) '打开' 'ControlType.Window') }
        catch { return }
        Start-Sleep -Milliseconds 100
    }
    throw 'File dialog did not close'
}
foreach ($scene in @(@{Id='SCN-001';Name='加速减速任务'},@{Id='SCN-002';Name='双高度悬停任务'})) {
    Invoke-SceneControl (Wait-Control "打开场景 $($scene.Id) $($scene.Name)" 'ControlType.Button')
    $directory = Join-Path $repository "examples/supervisor-demo-2026-09-15/$($scene.Id)"
    Open-DemoFile '加载配置' (Join-Path $directory 'configuration.json')
    [void](Wait-Control '配置已加载' 'ControlType.Text')
    Open-DemoFile '导入帧数据' (Join-Path $directory '03-unqualified.input.json')
    Invoke-SceneControl (Wait-Control '开始评估' 'ControlType.Button')
    [void](Wait-Control '评估完成' 'ControlType.Text')
    $nodes = @(Get-SceneNodes (Get-SceneWindow $processId))
    if (-not ($nodes.Name -contains '场景评估：U / Fail')) { throw 'Expected Fail is absent' }
    $nodes | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $PSScriptRoot "$($scene.Id)-final-ui.json") -Encoding utf8
    Write-Output "$($scene.Id): final build load/evaluate PASS"
}
Invoke-SceneControl (Wait-Control '打开全局 Model Studio' 'ControlType.Button')
Invoke-SceneControl (Wait-Control 'SCN-002，ITEM，悬停定点保持，U · Fail   演示·未标定 87.0' 'ControlType.Button')
$nodes=@(Get-SceneNodes (Get-SceneWindow $processId))
if ($nodes.Name -match '不输出未校准分数') {throw 'Contradictory pending description remains'}
Invoke-SceneControl (Wait-Control '编辑演示先验、分值与 CPT' 'ControlType.Button')
$cpt = Wait-Control '水平位置保持，高技能，U 概率' 'ControlType.Edit'
if ($cpt.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value -ne '0.001') {throw 'CPT mismatch'}
Invoke-SceneControl (Wait-Control '取消' 'ControlType.Button')
for ($attempt=0; $attempt -lt 100; $attempt++) {
    try { [void](Find-SceneControl (Get-SceneWindow $processId) '取消' 'ControlType.Button') }
    catch { break }
    Start-Sleep -Milliseconds 100
}
Write-Output 'Model Studio and CPT editor: current methods and 0.001 CPT readback PASS'
Invoke-SceneControl (Wait-Control '打开场景 SCN-002 双高度悬停任务' 'ControlType.Button')
$label=Wait-Control 'A-S2-02 · 悬停定点保持    U / Fail' 'ControlType.Text'
$parent=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($label)
$parent.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
$cp=Wait-Control '激光指向保持 · 局部表现 · 近 3 秒 · 演示未标定' 'ControlType.Button'
$cp.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
$plot=Wait-Control '检查点局部演示分时序图，纵轴0至100，阶段和缺失处断开，完整数值见明细'
$plot.GetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern).ScrollIntoView()
Write-Output "Final running process: $processId"
