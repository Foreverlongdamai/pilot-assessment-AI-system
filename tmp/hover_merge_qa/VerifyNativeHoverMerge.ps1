param([int]$ProcessId, [switch]$UseExistingExports)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../scene_v3_qa/RefinementQa.ps1"
$repository = (Resolve-Path "$PSScriptRoot/../..").Path
$demo = Join-Path $repository 'examples/supervisor-demo-2026-09-15/SCN-002'
function Wait-Control([string]$Name, [string]$Type='') {
    for ($attempt=0; $attempt -lt 100; $attempt++) {
        try { return Find-SceneControl (Get-SceneWindow $ProcessId) $Name $Type }
        catch { Start-Sleep -Milliseconds 100 }
    }
    throw "Control not ready: $Name"
}
function Wait-Closed([string]$Name, [string]$Type='') {
    for ($attempt=0; $attempt -lt 100; $attempt++) {
        try { [void](Find-SceneControl (Get-SceneWindow $ProcessId) $Name $Type) }
        catch { Wait-Ready; return }
        Start-Sleep -Milliseconds 100
    }
    throw "Control did not close: $Name"
}
function Wait-Ready {
    for ($attempt=0; $attempt -lt 100; $attempt++) {
        $button=Find-SceneControl (Get-SceneWindow $ProcessId) '保存配置' 'ControlType.Button'
        if ($button.Current.IsEnabled) { return }
        Start-Sleep -Milliseconds 100
    }
    throw 'Application actions did not become ready'
}
function Open-Json([string]$Button, [string]$Path) {
    Invoke-SceneControl (Wait-Control $Button 'ControlType.Button')
    [void](Wait-Control '打开' 'ControlType.Window')
    Complete-SceneFileDialog $ProcessId $Path
    Wait-Closed '打开' 'ControlType.Window'
}
function Save-Json([string]$Button, [string]$Path) {
    if (Test-Path -LiteralPath $Path) { throw "Verification output already exists: $Path" }
    Invoke-SceneControl (Wait-Control $Button 'ControlType.Button')
    [void](Wait-Control '另存为' 'ControlType.Window')
    Complete-SceneFileDialog $ProcessId $Path -Save
    Wait-Closed '另存为' 'ControlType.Window'
    for ($attempt=0; $attempt -lt 100; $attempt++) {
        if (Test-Path -LiteralPath $Path) { return }
        Start-Sleep -Milliseconds 100
    }
    throw "Export did not appear: $Path"
}
function Find-Prefix([string]$Prefix, [string]$Type='') {
    $nodes=@(Get-SceneNodes (Get-SceneWindow $ProcessId) | Where-Object {
        $_.Name.StartsWith($Prefix) -and ($Type -eq '' -or $_.Type -eq $Type)
    })
    if ($nodes.Count -ne 1) { throw "Expected unique prefix '$Prefix', found $($nodes.Count)" }
    return Wait-Control $nodes[0].Name $Type
}
Invoke-SceneControl (Wait-Control '打开场景 SCN-002 双高度悬停任务' 'ControlType.Button')
Open-Json '加载配置' (Join-Path $demo 'configuration.json')
[void](Wait-Control '配置已加载' 'ControlType.Text')
Open-Json '导入帧数据' (Join-Path $demo '03-unqualified.input.json')
Invoke-SceneControl (Wait-Control '开始评估' 'ControlType.Button')
[void](Wait-Control '评估完成' 'ControlType.Text')
[void](Wait-Control '场景评估：U / Fail' 'ControlType.Text')
$nodes = @(Get-SceneNodes (Get-SceneWindow $ProcessId))
if ($nodes.Name -match '^A-S2-01 ·') { throw 'Removed height item is visible' }
[void](Find-Prefix 'A-S2-02 · 定点悬停保持' 'ControlType.Text')
$nodes | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $PSScriptRoot 'scene-ui.json') -Encoding utf8
Write-Output 'SCN-002: merged item visible, old item absent, actual demo evaluates Fail'

$templatePath=Join-Path $PSScriptRoot 'native-export-input-template.json'
if (-not $UseExistingExports) {
    Save-Json '导出空白输入模板' $templatePath
    [void](Wait-Control '空白输入模板已导出' 'ControlType.Text')
}
$template=Get-Content -LiteralPath $templatePath -Raw | ConvertFrom-Json
if (@($template.items.PSObject.Properties).Count -ne 2) { throw 'Template item count mismatch' }
if ($template.items.'A-S2-01') { throw 'Template retained old item' }
$fields=@($template.items.'A-S2-02'.frames | ForEach-Object { $_.values.PSObject.Properties.Name })
foreach ($field in @('hover_lower_height_m','hover_upper_height_m','hover_vz_mps')) {
    if ($fields -notcontains $field) { throw "Template missing $field" }
}
$reportPath=Join-Path $PSScriptRoot 'native-export-report.json'
if (-not $UseExistingExports) {
    Save-Json '导出评估报告' $reportPath
    [void](Wait-Control '报告已导出' 'ControlType.Text')
}
$report=Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
if ($report.items.Count -ne 2) { throw 'Report item count mismatch' }
$hover=@($report.items | Where-Object item_id -eq 'A-S2-02')[0]
if ($hover.checkpoints.Count -ne 4 -or $hover.skill_quantification.evidence_count -ne 4) { throw 'Report should use four checkpoint evidences' }
if (@($hover.skill_quantification.local_traces | Where-Object checkpoint_id -eq 'A-S2-02-04').Count -ne 1) { throw 'Report omitted height local trace' }
Write-Output 'Native exports: two items; height raw fields in merged frames; four checkpoint reports and height trace'

Invoke-SceneControl (Wait-Control '打开全局 Model Studio' 'ControlType.Button')
$node=Find-Prefix 'SCN-002，ITEM，定点悬停保持，' 'ControlType.Button'
Invoke-SceneControl $node
$nodes=@(Get-SceneNodes (Get-SceneWindow $ProcessId))
if ($nodes.Name -match '^SCN-002，ITEM，悬停高度保持，') { throw 'Model Studio retained standalone height item' }
foreach ($name in @('水平位置保持','悬停高度保持','航向保持','激光指向保持')) {
    [void](Find-Prefix "SCN-002，CHECKPOINT，$name，" 'ControlType.Button')
}
$nodes | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $PSScriptRoot 'model-studio-ui.json') -Encoding utf8
Invoke-SceneControl (Wait-Control '编辑演示先验、分值与 CPT' 'ControlType.Button')
foreach ($name in @('水平位置保持','悬停高度保持','航向保持','激光指向保持')) {
    $field=Wait-Control "$name，高技能，U 概率" 'ControlType.Edit'
    if ($field.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value -ne '0.001') {
        throw "Unexpected high-state U CPT: $name"
    }
}
@(Get-SceneNodes (Get-SceneWindow $ProcessId)) | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $PSScriptRoot 'four-cpt-editor-ui.json') -Encoding utf8
Invoke-SceneControl (Wait-Control '取消' 'ControlType.Button')
Wait-Closed '取消' 'ControlType.Button'
Write-Output 'Model Studio: merged item, four checkpoint nodes, four CPT editors with exact 0.001 readback'

Invoke-SceneControl (Wait-Control '编辑此 item 的目标和偏差范围' 'ControlType.Button')
[void](Wait-Control '下方悬停实际高度' 'ControlType.Text')
[void](Wait-Control '上方悬停实际高度' 'ControlType.Text')
[void](Wait-Control '悬停高度保持' 'ControlType.Text')
@(Get-SceneNodes (Get-SceneWindow $ProcessId)) | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $PSScriptRoot 'height-parameter-editor-ui.json') -Encoding utf8
Invoke-SceneControl (Wait-Control '取消' 'ControlType.Button')
Wait-Closed '取消' 'ControlType.Button'
Write-Output 'Merged item parameter editor exposes both lower and upper height targets'

Invoke-SceneControl (Wait-Control '打开场景 SCN-002 双高度悬停任务' 'ControlType.Button')
$label=Find-Prefix 'A-S2-02 · 定点悬停保持' 'ControlType.Text'
$parent=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($label)
$parent.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
$cp=Wait-Control '悬停高度保持 · 局部表现 · 近 3 秒 · 演示未标定' 'ControlType.Button'
$cp.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
$plot=Wait-Control '检查点局部演示分时序图，纵轴0至100，阶段和缺失处断开，完整数值见明细'
$plot.GetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern).ScrollIntoView()
@(Get-SceneNodes (Get-SceneWindow $ProcessId)) | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $PSScriptRoot 'final-height-curve-ui.json') -Encoding utf8
Write-Output "Native verification complete; process $ProcessId remains showing height local trace"
