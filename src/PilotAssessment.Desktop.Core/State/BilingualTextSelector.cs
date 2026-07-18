using System.ComponentModel;
using System.Globalization;

namespace PilotAssessment.Desktop.Core.State;

public interface ILocalizationLookup
{
    string CurrentLanguage { get; }

    string this[string key] { get; }

    event EventHandler? LanguageChanged;

    string GetString(string key);

    string Format(string key, params object?[] arguments);
}

/// <summary>
/// Shared notification boundary for localization providers. The desktop MRT provider
/// supplies the strings; tests can use a small dictionary-backed provider without WinUI.
/// </summary>
public abstract class ObservableLocalizationLookup : ILocalizationLookup, INotifyPropertyChanged
{
    private string _currentLanguage;

    protected ObservableLocalizationLookup(string initialLanguage)
    {
        _currentLanguage = NormalizeLanguage(initialLanguage);
    }

    public string CurrentLanguage => _currentLanguage;

    public string this[string key] => GetString(key);

    public event EventHandler? LanguageChanged;

    public event PropertyChangedEventHandler? PropertyChanged;

    public abstract string GetString(string key);

    public string Format(string key, params object?[] arguments) =>
        string.Format(CultureInfo.CurrentCulture, GetString(key), arguments);

    protected bool SetCurrentLanguage(string language, bool forceNotification = false)
    {
        var normalized = NormalizeLanguage(language);
        if (!forceNotification && string.Equals(normalized, _currentLanguage, StringComparison.Ordinal))
        {
            return false;
        }

        _currentLanguage = normalized;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(CurrentLanguage)));
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs("Item[]"));
        LanguageChanged?.Invoke(this, EventArgs.Empty);
        return true;
    }

    public static string NormalizeLanguage(string? language) =>
        language?.StartsWith("zh", StringComparison.OrdinalIgnoreCase) is true
            ? "zh-CN"
            : "en-US";
}

/// <summary>
/// Selects localized model metadata without changing the canonical model object.
/// Missing translations remain visible through an explicit fallback marker.
/// </summary>
public static class BilingualTextSelector
{
    public const string EnglishFallbackMarker = " [EN fallback]";
    public const string ChineseFallbackMarker = " [中文回退]";
    public const string IdentifierFallbackMarker = " [ID fallback]";

    public static string Select(
        string? language,
        string? textZh,
        string? textEn,
        string stableIdentifier)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(stableIdentifier);
        var preferChinese = ObservableLocalizationLookup
            .NormalizeLanguage(language)
            .StartsWith("zh", StringComparison.OrdinalIgnoreCase);

        if (preferChinese)
        {
            if (!string.IsNullOrWhiteSpace(textZh))
            {
                return textZh.Trim();
            }

            if (!string.IsNullOrWhiteSpace(textEn))
            {
                return textEn.Trim() + EnglishFallbackMarker;
            }
        }
        else
        {
            if (!string.IsNullOrWhiteSpace(textEn))
            {
                return textEn.Trim();
            }

            if (!string.IsNullOrWhiteSpace(textZh))
            {
                return textZh.Trim() + ChineseFallbackMarker;
            }
        }

        return stableIdentifier + IdentifierFallbackMarker;
    }

    public static string SelectShortOrFull(
        string? language,
        string? shortZh,
        string? shortEn,
        string? fullZh,
        string? fullEn,
        string stableIdentifier) => Select(
            language,
            FirstNonBlank(shortZh, fullZh),
            FirstNonBlank(shortEn, fullEn),
            stableIdentifier);

    private static string? FirstNonBlank(params string?[] values) =>
        values.FirstOrDefault(value => !string.IsNullOrWhiteSpace(value));
}
