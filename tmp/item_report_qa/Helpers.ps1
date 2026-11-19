$ErrorActionPreference='Stop'
. "$PSScriptRoot/../scene_v3_qa/RefinementQa.ps1"
function Wait-Ui($Root,[string]$Name,[string]$Type='') {
    for($i=0;$i -lt 80;$i++) {
        try { return Find-SceneControl $Root $Name $Type } catch { Start-Sleep -Milliseconds 100 }
    }
    throw "Not found: $Name"
}
function Wait-Ready($Root) {
    for($i=0;$i -lt 100;$i++) {
        try {
            $button=Find-SceneControl $Root '保存配置' 'ControlType.Button'
            if($button.Current.IsEnabled) { return }
        } catch { }
        Start-Sleep -Milliseconds 100
    }
    throw 'Actions not ready'
}
function Get-PilotWindows([int]$ProcessId) {
    $condition=[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$ProcessId)
    $windows=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,$condition)
    foreach($window in $windows) { $window }
}
function Wait-ResultWindow([int]$ProcessId,[string]$Prefix) {
    for($i=0;$i -lt 100;$i++) {
        foreach($window in @(Get-PilotWindows $ProcessId)) {
            if($window.Current.Name.StartsWith($Prefix) -and $window.Current.Name.EndsWith('评估结果')) { return $window }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Result window not found: $Prefix"
}
function Import-Json($Root,[string]$Button,[string]$Path) {
    if (-not [System.IO.Path]::IsPathFullyQualified($Path)) {
        throw 'QA file picker requires an absolute path; resolve and verify it before opening the dialog.'
    }
    $Path = (Get-Item -LiteralPath $Path -ErrorAction Stop).FullName
    Wait-Ready $Root
    Invoke-SceneControl (Wait-Ui $Root $Button 'ControlType.Button')
    $dialog=Wait-Ui $Root '打开' 'ControlType.Window'
    $children=@(Get-SceneDialogWindows $dialog.Current.NativeWindowHandle)
    $edit=@($children|Where-Object { $_.Class -eq 'Edit' -and $_.Id -eq 1148 })
    $ok=@($children|Where-Object { $_.Class -eq 'Button' -and $_.Id -eq 1 })
    if($edit.Count -ne 1 -or $ok.Count -ne 1) { throw 'File dialog controls mismatch' }
    [void][SceneQaNative]::SendMessage([IntPtr]$edit[0].Handle,12,[IntPtr]::Zero,$Path)
    [void][SceneQaNative]::PostMessage([IntPtr]$ok[0].Handle,245,[IntPtr]::Zero,[IntPtr]::Zero)
    for($i=0;$i -lt 100;$i++) {
        try { [void](Find-SceneControl $Root '打开' 'ControlType.Window') }
        catch { Wait-Ready $Root; return }
        Start-Sleep -Milliseconds 100
    }
    throw 'File dialog did not finish'
}
function Save-Ui($Root,[string]$Name) {
    @(Get-SceneNodes $Root) | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $PSScriptRoot $Name) -Encoding utf8
}
function Capture-Ui($Root,[string]$Name) {
    $Root.SetFocus()
    $bounds=$Root.Current.BoundingRectangle
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.Cursor]::Position=[System.Drawing.Point]::new([int]$bounds.X+100,[int]$bounds.Y+15)
    $region='{0},{1},{2},{3}' -f [int]$bounds.X,[int]$bounds.Y,[int]$bounds.Width,[int]$bounds.Height
    & 'C:/Users/long/.codex/skills/screenshot/scripts/take_screenshot.ps1' -Region $region -Path (Join-Path $PSScriptRoot $Name)
}
