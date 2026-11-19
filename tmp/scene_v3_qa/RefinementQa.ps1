. $PSScriptRoot/UiHelpers.ps1
. $PSScriptRoot/NativeDialog.ps1

function Complete-SceneFileDialog([int]$ProcessId, [string]$Path, [switch]$Save) {
    $window = Get-SceneWindow $ProcessId
    $name = if ($Save) { '另存为' } else { '打开' }
    $dialog = Find-SceneControl $window $name 'ControlType.Window'
    $children = @(Get-SceneDialogWindows $dialog.Current.NativeWindowHandle)
    $editId = if ($Save) { 1001 } else { 1148 }
    $edit = @($children | Where-Object { $_.Class -eq 'Edit' -and $_.Id -eq $editId })
    $button = @($children | Where-Object { $_.Class -eq 'Button' -and $_.Id -eq 1 })
    if ($edit.Count -ne 1 -or $button.Count -ne 1) { throw 'Expected native file dialog controls were not found.' }
    [void][SceneQaNative]::SendMessage([IntPtr]$edit[0].Handle, 12, [IntPtr]::Zero, $Path)
    [void][SceneQaNative]::PostMessage([IntPtr]$button[0].Handle, 245, [IntPtr]::Zero, [IntPtr]::Zero)
}
