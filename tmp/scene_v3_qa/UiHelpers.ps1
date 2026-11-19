Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Get-SceneWindow([int]$ProcessId) {
    $process = Get-Process -Id $ProcessId
    $window = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
    if ($null -eq $window) { throw 'Application window is not ready.' }
    return $window
}

function Get-SceneNodes($Root) {
    $nodes = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($node in $nodes) {
        if ($node.Current.Name) {
            [pscustomobject]@{ Type=$node.Current.ControlType.ProgrammaticName; Name=$node.Current.Name; Id=$node.Current.AutomationId }
        }
    }
}

function Find-SceneControl($Root, [string]$Name, [string]$Type='') {
    $nodes = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($node in $nodes) {
        if ($node.Current.Name -eq $Name -and ($Type -eq '' -or $node.Current.ControlType.ProgrammaticName -eq $Type)) { return $node }
    }
    throw "Control not found: $Name ($Type)"
}

function Invoke-SceneControl($Control) {
    $pattern = $Control.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $pattern.Invoke()
}
