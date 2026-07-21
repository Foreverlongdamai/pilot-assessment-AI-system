using System.Globalization;
using System.Text;
using System.Text.Json;

using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

/// <summary>
/// Produces stable, human-readable English labels for model content without exposing
/// UUID/hash-backed technical identities in ordinary product surfaces.
/// </summary>
public static class ModelDisplayNameResolver
{
    private static readonly string[] MetadataNameKeys =
    [
        "display_name",
        "name",
        "label",
        "competency_name",
        "sub_skill_name",
        "task_name",
        "scenario_name",
        "title",
    ];

    private static readonly HashSet<string> TechnicalTokens = new(StringComparer.OrdinalIgnoreCase)
    {
        "model",
        "node",
        "modelnode",
        "raw",
        "input",
        "rawinput",
        "evidence",
        "bn",
        "task",
        "scheme",
        "taskscheme",
        "user",
        "current",
        "version",
        "component",
    };

    public static string ForNode(ModelNode node, bool preferShort = true)
    {
        ArgumentNullException.ThrowIfNull(node);
        var savedName = preferShort
            ? FirstNonBlank(node.ShortNameEn, node.NameEn)
            : FirstNonBlank(node.NameEn, node.ShortNameEn);
        if (savedName is not null)
        {
            return savedName;
        }

        var semanticName = node.Definition switch
        {
            RawInputNodeDefinition raw => ResolveRawInput(raw),
            EvidenceNodeDefinition evidence => FirstNonBlank(
                evidence.Recipe.Anchor.Name,
                evidence.Recipe.Documentation.Summary),
            BnNodeDefinition bn => ResolveBn(node, bn),
            _ => null,
        };
        return FirstNonBlank(semanticName)
            ?? HumanizeIdentifier(node.NodeId, KindFallback(node));
    }

    public static string ForScheme(TaskScheme scheme)
    {
        ArgumentNullException.ThrowIfNull(scheme);
        var savedName = FirstNonBlank(scheme.NameEn);
        if (savedName is not null)
        {
            return savedName;
        }

        var bindingName = ReadMetadataName(scheme.TaskBindings);
        if (bindingName is not null)
        {
            return EnsureSchemeSuffix(bindingName);
        }

        var group = FirstNonBlank(scheme.Group);
        if (group is not null)
        {
            return EnsureSchemeSuffix(HumanizePhrase(group));
        }

        var tag = scheme.Tags.FirstOrDefault(IsSemanticToken);
        if (tag is not null)
        {
            return EnsureSchemeSuffix(HumanizePhrase(tag));
        }

        return HumanizeIdentifier(scheme.SchemeId, "Assessment Scheme");
    }

    public static string HumanizeIdentifier(string stableIdentifier, string semanticFallback)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(stableIdentifier);
        ArgumentException.ThrowIfNullOrWhiteSpace(semanticFallback);
        var tokens = stableIdentifier
            .Split(['.', '-', '_', '/', '\\', ':', ' '], StringSplitOptions.RemoveEmptyEntries)
            .Where(IsSemanticToken)
            .Select(HumanizeToken)
            .Where(token => token.Length > 0)
            .ToArray();
        return tokens.Length == 0
            ? semanticFallback.Trim()
            : string.Join(" ", tokens);
    }

    private static string? ResolveRawInput(RawInputNodeDefinition definition)
    {
        var sourceName = FirstNonBlank(definition.SourceDescriptor.Name);
        if (sourceName is not null && !LooksLikeTechnicalIdentity(sourceName))
        {
            return sourceName;
        }

        return definition.SourceDescriptor.RawModality switch
        {
            RawModality.X => "Flight State",
            RawModality.U => "Control Input",
            RawModality.I => "Visual Scene",
            RawModality.G => "Gaze Tracking",
            RawModality.Eeg => "EEG Signal",
            RawModality.Ecg => "ECG Signal",
            RawModality.PilotCamera => "Pilot Camera",
            _ => definition.Family switch
            {
                RawInputFamily.X => "Flight State",
                RawInputFamily.U => "Control Input",
                RawInputFamily.I => "Visual Scene",
                RawInputFamily.G => "Gaze Tracking",
                RawInputFamily.P => "Physiology",
                RawInputFamily.PilotCamera => "Pilot Camera",
                _ => null,
            },
        };
    }

    private static string ResolveBn(ModelNode node, BnNodeDefinition definition)
    {
        var metadataName = ReadMetadataName(definition.ReportingMetadata);
        if (metadataName is not null)
        {
            return metadataName;
        }

        var group = FirstNonBlank(node.Group);
        if (group is not null && !LooksLikeTechnicalIdentity(group))
        {
            var groupName = HumanizePhrase(group);
            return definition.NodeRole switch
            {
                BnNodeRole.AggregateCompetency when !ContainsWord(groupName, "Competency") =>
                    $"{groupName} Competency",
                BnNodeRole.SubSkill when !ContainsWord(groupName, "Skill") => $"{groupName} Skill",
                _ => groupName,
            };
        }

        var documentationName = FirstSentenceFragment(definition.Documentation);
        if (documentationName is not null)
        {
            return documentationName;
        }

        return definition.NodeRole switch
        {
            BnNodeRole.AggregateCompetency => "Aggregate Competency",
            BnNodeRole.SubSkill => "Pilot Sub-skill",
            BnNodeRole.Latent => "Latent Pilot Skill",
            BnNodeRole.Derived => "Derived Pilot Skill",
            _ => "Pilot Skill",
        };
    }

    private static string? ReadMetadataName(IReadOnlyDictionary<string, JsonElement> metadata)
    {
        foreach (var key in MetadataNameKeys)
        {
            if (metadata.TryGetValue(key, out var value) &&
                value.ValueKind is JsonValueKind.String &&
                FirstNonBlank(value.GetString()) is { } text &&
                !LooksLikeTechnicalIdentity(text))
            {
                return text;
            }
        }

        return null;
    }

    private static string? FirstSentenceFragment(string? value)
    {
        var text = FirstNonBlank(value);
        if (text is null || LooksLikeTechnicalIdentity(text))
        {
            return null;
        }

        var end = text.IndexOfAny(['.', ';', '\r', '\n']);
        var fragment = (end > 0 ? text[..end] : text).Trim();
        if (fragment.Length is 0 or > 72 || fragment.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length > 9)
        {
            return null;
        }

        return fragment;
    }

    private static string KindFallback(ModelNode node) => node.Definition switch
    {
        RawInputNodeDefinition => "Raw Input",
        EvidenceNodeDefinition => "Evidence",
        BnNodeDefinition { NodeRole: BnNodeRole.AggregateCompetency } => "Aggregate Competency",
        BnNodeDefinition { NodeRole: BnNodeRole.SubSkill } => "Pilot Sub-skill",
        BnNodeDefinition => "Pilot Skill",
        _ => node.NodeKind switch
        {
            ModelNodeKind.RawInput => "Raw Input",
            ModelNodeKind.Evidence => "Evidence",
            _ => "Pilot Skill",
        },
    };

    private static string EnsureSchemeSuffix(string name) =>
        ContainsWord(name, "Scheme") ? name : $"{name} Assessment Scheme";

    private static bool ContainsWord(string text, string word) =>
        text.Contains(word, StringComparison.OrdinalIgnoreCase);

    private static bool IsSemanticToken(string token)
    {
        var value = token.Trim();
        return value.Length > 0 &&
               !TechnicalTokens.Contains(value) &&
               !LooksLikeRandomIdentity(value) &&
               !string.Equals(value, "v1", StringComparison.OrdinalIgnoreCase) &&
               !string.Equals(value, "v2", StringComparison.OrdinalIgnoreCase);
    }

    private static bool LooksLikeTechnicalIdentity(string value) =>
        value.Contains("model-node", StringComparison.OrdinalIgnoreCase) ||
        value.Contains("task-scheme", StringComparison.OrdinalIgnoreCase) ||
        value.Split(['.', '-', '_'], StringSplitOptions.RemoveEmptyEntries)
            .Any(LooksLikeRandomIdentity);

    private static bool LooksLikeRandomIdentity(string token)
    {
        var compact = token.Replace("-", string.Empty, StringComparison.Ordinal);
        if (Guid.TryParse(token, out _) || compact.Length >= 24 && compact.All(Uri.IsHexDigit))
        {
            return true;
        }

        return compact.Length >= 12 && compact.All(char.IsDigit);
    }

    private static string HumanizePhrase(string value)
    {
        var tokens = value
            .Split(['.', '-', '_', '/', '\\'], StringSplitOptions.RemoveEmptyEntries)
            .Select(HumanizeToken);
        return string.Join(" ", tokens);
    }

    private static string HumanizeToken(string token)
    {
        if (token.All(char.IsUpper) && token.Length <= 6)
        {
            return token;
        }

        var builder = new StringBuilder(token.Length + 4);
        for (var index = 0; index < token.Length; index++)
        {
            var character = token[index];
            if (index > 0 && char.IsUpper(character) && char.IsLower(token[index - 1]))
            {
                builder.Append(' ');
            }

            builder.Append(character);
        }

        var words = builder.ToString().Trim().ToLowerInvariant();
        return CultureInfo.InvariantCulture.TextInfo.ToTitleCase(words) switch
        {
            "Eeg" => "EEG",
            "Ecg" => "ECG",
            "Aoi" => "AOI",
            "Vr" => "VR",
            "Bn" => "BN",
            "Cpt" => "CPT",
            "Tpx" => "TPX",
            var result => result,
        };
    }

    private static string? FirstNonBlank(params string?[] values) =>
        values.FirstOrDefault(value => !string.IsNullOrWhiteSpace(value))?.Trim();
}
