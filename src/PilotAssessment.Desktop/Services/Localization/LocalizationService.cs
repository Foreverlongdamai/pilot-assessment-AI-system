using System.Globalization;

using Microsoft.Windows.ApplicationModel.Resources;

using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Services.Localization;

/// <summary>
/// Reads the WinUI MRT Core resources through an explicit language-qualified context.
/// Updating the language replaces that context and notifies every indexer binding, so
/// already-open windows refresh without recreating their model or sending backend writes.
/// </summary>
public sealed class LocalizationService : ObservableLocalizationLookup
{
    private readonly ResourceManager _resourceManager;
    private readonly ResourceMap _resources;
    private ResourceContext _context;

    public LocalizationService(string initialLanguage = "en-US")
        : base(initialLanguage)
    {
        var executablePath = Environment.ProcessPath;
        var priPath = string.IsNullOrWhiteSpace(executablePath)
            ? null
            : Path.ChangeExtension(executablePath, ".pri");
        _resourceManager = priPath is not null && File.Exists(priPath)
            ? new ResourceManager(priPath)
            : new ResourceManager();
        _resources = _resourceManager.MainResourceMap.GetSubtree("Resources");
        _context = CreateContext(CurrentLanguage);
        ApplyCulture(CurrentLanguage);
    }

    public void ChangeLanguage(string language)
    {
        var normalized = NormalizeLanguage(language);
        _context = CreateContext(normalized);
        ApplyCulture(normalized);
        SetCurrentLanguage(normalized, forceNotification: true);
    }

    public override string GetString(string key)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(key);
        try
        {
            var candidate = _resources.GetValue(key, _context);
            var value = candidate?.ValueAsString;
            return string.IsNullOrWhiteSpace(value) ? $"⟦{key}⟧" : value;
        }
        catch
        {
            // A missing UI key must stay visible during expert work rather than silently
            // falling back to a stale language or crashing an editor window.
            return $"⟦{key}⟧";
        }
    }

    private ResourceContext CreateContext(string language)
    {
        var context = _resourceManager.CreateResourceContext();
        context.QualifierValues["Language"] = language;
        return context;
    }

    private static void ApplyCulture(string language)
    {
        CultureInfo.CurrentUICulture = CultureInfo.GetCultureInfo(language);
        CultureInfo.DefaultThreadCurrentUICulture = CultureInfo.GetCultureInfo(language);
    }
}
