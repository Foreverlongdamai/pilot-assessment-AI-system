using Windows.Storage.Pickers;

using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Services.Preferences;

public sealed class FolderPickerService : IProjectFolderPicker
{
    public async Task<string?> PickFolderAsync(
        string purpose,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var picker = new FolderPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = purpose,
        };
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, App.WindowHandle);
        var folder = await picker.PickSingleFolderAsync();
        cancellationToken.ThrowIfCancellationRequested();
        return folder?.Path;
    }
}
