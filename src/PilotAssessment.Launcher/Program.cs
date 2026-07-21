using System.Diagnostics;
using System.Runtime.InteropServices;

namespace PilotAssessment.Launcher;

internal static class Program
{
    private const uint ErrorIcon = 0x00000010;

    [STAThread]
    private static int Main(string[] arguments)
    {
        var productRoot = Path.GetFullPath(AppContext.BaseDirectory);
        var desktopExecutable = Path.Combine(
            productRoot,
            "app",
            "PilotAssessment.Desktop.exe");

        if (!File.Exists(desktopExecutable))
        {
            return Fail(
                "The desktop payload is incomplete. Keep PilotAssessment.exe beside the app, " +
                "backend, system and runtime directories, then extract the full product again.");
        }

        try
        {
            var startInfo = new ProcessStartInfo(desktopExecutable)
            {
                WorkingDirectory = productRoot,
                UseShellExecute = false,
            };
            foreach (var argument in arguments)
            {
                startInfo.ArgumentList.Add(argument);
            }

            using var desktop = Process.Start(startInfo);
            if (desktop is null)
            {
                return Fail("Windows did not start the Pilot Assessment desktop application.");
            }

            desktop.WaitForExit();
            return desktop.ExitCode;
        }
        catch (Exception error)
        {
            return Fail($"Pilot Assessment could not start.\n\n{error.Message}");
        }
    }

    private static int Fail(string message)
    {
        MessageBoxW(nint.Zero, message, "Pilot Assessment", ErrorIcon);
        return 1;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int MessageBoxW(
        nint window,
        string text,
        string caption,
        uint type);
}
