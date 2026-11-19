Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class SceneQaNative {
 public delegate bool EnumProc(IntPtr h, IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc fn, IntPtr p);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll")] public static extern int GetDlgCtrlID(IntPtr h);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, string l);
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
}
'@
function Get-SceneDialogWindows([IntPtr]$WindowHandle) {
 $found = [System.Collections.Generic.List[object]]::new()
 $callback = [SceneQaNative+EnumProc]{ param($handle, $parameter)
  $class = [System.Text.StringBuilder]::new(256)
  $title = [System.Text.StringBuilder]::new(512)
  [void][SceneQaNative]::GetClassName($handle, $class, 256)
  [void][SceneQaNative]::GetWindowText($handle, $title, 512)
  $found.Add([pscustomobject]@{Handle=$handle.ToInt64(); Class=$class.ToString(); Name=$title.ToString(); Id=[SceneQaNative]::GetDlgCtrlID($handle)})
  return $true
 }
 [void][SceneQaNative]::EnumChildWindows($WindowHandle, $callback, [IntPtr]::Zero)
 return $found
}
