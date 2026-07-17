using System.Collections.ObjectModel;
using System.Text.Json;

using CommunityToolkit.Mvvm.ComponentModel;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.ViewModels;

public sealed partial class RawInputEditorViewModel : ObservableObject
{
    private ModelNode _canonicalNode;

    [ObservableProperty]
    public partial string NameZh { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string NameEn { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string DescriptionZh { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string DescriptionEn { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string Group { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string TagsText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial RawInputFamily? Family { get; set; }

    [ObservableProperty]
    public partial RawResourceRole ResourceRole { get; set; }

    [ObservableProperty]
    public partial string SourceId { get; set; } = string.Empty;

    [ObservableProperty]
    public partial SourceKind SourceKind { get; set; }

    [ObservableProperty]
    public partial string SourceName { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string SourceDescription { get; set; } = string.Empty;

    [ObservableProperty]
    public partial RawModality? RawModality { get; set; }

    [ObservableProperty]
    public partial string ValueType { get; set; } = string.Empty;

    [ObservableProperty]
    public partial PortCardinality Cardinality { get; set; }

    [ObservableProperty]
    public partial TemporalSemantics TemporalSemantics { get; set; }

    [ObservableProperty]
    public partial string Unit { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string SourceDependenciesText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string SchemaId { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string AdapterId { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string ProfileId { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string ClockBinding { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string FieldsJson { get; set; } = "[]";

    [ObservableProperty]
    public partial string UnitsJson { get; set; } = "{}";

    [ObservableProperty]
    public partial string MetadataJson { get; set; } = "{}";

    [ObservableProperty]
    public partial string HelpTextZh { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string HelpTextEn { get; set; } = string.Empty;

    public RawInputEditorViewModel(
        ModelNode node,
        IEnumerable<ModalityStatusItem> sessionAvailability)
    {
        _canonicalNode = node;
        foreach (var item in sessionAvailability)
        {
            SessionAvailability.Add(item);
        }
        ApplyCanonical(node);
    }

    public ObservableCollection<ModalityStatusItem> SessionAvailability { get; } = [];

    public IReadOnlyList<RawInputFamily?> Families { get; } =
        [null, .. Enum.GetValues<RawInputFamily>()];

    public IReadOnlyList<RawResourceRole> ResourceRoles { get; } =
        Enum.GetValues<RawResourceRole>();

    public IReadOnlyList<SourceKind> SourceKinds { get; } = Enum.GetValues<SourceKind>();

    public IReadOnlyList<RawModality?> Modalities { get; } =
        [null, .. Enum.GetValues<RawModality>()];

    public IReadOnlyList<PortCardinality> Cardinalities { get; } =
        Enum.GetValues<PortCardinality>();

    public IReadOnlyList<TemporalSemantics> TemporalOptions { get; } =
        Enum.GetValues<TemporalSemantics>();

    public void ApplyCanonical(ModelNode node)
    {
        ArgumentNullException.ThrowIfNull(node);
        var definition = node.Definition as RawInputNodeDefinition
            ?? throw new ArgumentException("Raw Input editor requires a Raw Input node.");
        _canonicalNode = node;
        var descriptor = definition.SourceDescriptor;
        NameZh = node.NameZh ?? string.Empty;
        NameEn = node.NameEn ?? string.Empty;
        DescriptionZh = node.DescriptionZh ?? string.Empty;
        DescriptionEn = node.DescriptionEn ?? string.Empty;
        Group = node.Group ?? string.Empty;
        TagsText = string.Join(", ", node.Tags);
        Family = definition.Family;
        ResourceRole = definition.ResourceRole;
        SourceId = descriptor.SourceId;
        SourceKind = descriptor.Kind;
        SourceName = descriptor.Name;
        SourceDescription = descriptor.Description;
        RawModality = descriptor.RawModality;
        ValueType = descriptor.DeclaredType.ValueType;
        Cardinality = descriptor.DeclaredType.Cardinality;
        TemporalSemantics = descriptor.DeclaredType.TemporalSemantics;
        Unit = descriptor.DeclaredType.Unit ?? string.Empty;
        SourceDependenciesText = string.Join(Environment.NewLine, descriptor.SourceDependencies);
        SchemaId = StringMetadata(descriptor.Metadata, "schema_id");
        AdapterId = StringMetadata(descriptor.Metadata, "adapter_id");
        ProfileId = StringMetadata(descriptor.Metadata, "profile_id");
        ClockBinding = StringMetadata(descriptor.Metadata, "clock_binding");
        FieldsJson = JsonMetadata(descriptor.Metadata, "fields", "[]");
        UnitsJson = JsonMetadata(descriptor.Metadata, "units", "{}");
        MetadataJson = JsonSerializer.Serialize(
            descriptor.Metadata,
            new JsonSerializerOptions { WriteIndented = true });
        HelpTextZh = definition.HelpTextZh ?? string.Empty;
        HelpTextEn = definition.HelpTextEn ?? string.Empty;
    }

    public ModelNode BuildUpdatedNode()
    {
        var definition = (RawInputNodeDefinition)_canonicalNode.Definition;
        var metadata = ParseMetadata(MetadataJson);
        SetString(metadata, "schema_id", SchemaId);
        SetString(metadata, "adapter_id", AdapterId);
        SetString(metadata, "profile_id", ProfileId);
        SetString(metadata, "clock_binding", ClockBinding);
        SetJson(metadata, "fields", FieldsJson, JsonValueKind.Array);
        SetJson(metadata, "units", UnitsJson, JsonValueKind.Object);
        var descriptor = definition.SourceDescriptor with
        {
            SourceId = SourceId.Trim(),
            Kind = SourceKind,
            Name = SourceName.Trim(),
            Description = SourceDescription.Trim(),
            DeclaredType = new PortType(
                ValueType.Trim(),
                Cardinality,
                TemporalSemantics,
                Normalize(Unit)),
            RawModality = RawModality,
            SourceDependencies = SplitValues(SourceDependenciesText),
            Metadata = metadata,
            ContentHash = new string('0', 64),
        };
        return _canonicalNode with
        {
            NameZh = Normalize(NameZh),
            NameEn = Normalize(NameEn),
            ShortNameZh = Shorten(NameZh),
            ShortNameEn = Shorten(NameEn),
            DescriptionZh = Normalize(DescriptionZh),
            DescriptionEn = Normalize(DescriptionEn),
            Tags = SplitValues(TagsText),
            Group = Normalize(Group),
            Definition = definition with
            {
                Family = Family,
                ResourceRole = ResourceRole,
                SourceDescriptor = descriptor,
                HelpTextZh = Normalize(HelpTextZh),
                HelpTextEn = Normalize(HelpTextEn),
            },
        };
    }

    private static Dictionary<string, JsonElement> ParseMetadata(string json) =>
        JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json)
        ?? throw new JsonException("Raw Input metadata must be a JSON object.");

    private static void SetString(Dictionary<string, JsonElement> metadata, string key, string value)
    {
        if (Normalize(value) is not { } normalized)
        {
            metadata.Remove(key);
            return;
        }
        metadata[key] = JsonSerializer.SerializeToElement(normalized);
    }

    private static void SetJson(
        Dictionary<string, JsonElement> metadata,
        string key,
        string json,
        JsonValueKind expectedKind)
    {
        using var document = JsonDocument.Parse(json);
        if (document.RootElement.ValueKind != expectedKind)
        {
            throw new JsonException($"{key} must be a JSON {expectedKind.ToString().ToLowerInvariant()}.");
        }
        metadata[key] = document.RootElement.Clone();
    }

    private static string StringMetadata(
        IReadOnlyDictionary<string, JsonElement> metadata,
        string key) =>
        metadata.TryGetValue(key, out var value) && value.ValueKind is JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;

    private static string JsonMetadata(
        IReadOnlyDictionary<string, JsonElement> metadata,
        string key,
        string fallback) =>
        metadata.TryGetValue(key, out var value)
            ? JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true })
            : fallback;

    private static string[] SplitValues(string value) => value
        .Split([',', ';', '\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .Distinct(StringComparer.Ordinal)
        .OrderBy(item => item, StringComparer.Ordinal)
        .ToArray();

    private static string? Normalize(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string? Shorten(string? value)
    {
        var normalized = Normalize(value);
        return normalized is { Length: > 96 } ? normalized[..96] : normalized;
    }
}
