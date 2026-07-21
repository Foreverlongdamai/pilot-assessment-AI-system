namespace PilotAssessment.Desktop.Core.State;

public static class DesktopAssetLocator
{
    public static string AppIconPath(string baseDirectory)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(baseDirectory);
        return Path.GetFullPath(Path.Combine(baseDirectory, "Assets", "AppIcon.ico"));
    }
}
