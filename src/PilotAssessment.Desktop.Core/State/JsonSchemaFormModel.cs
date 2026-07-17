using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;

using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

public enum JsonSchemaFieldKind
{
    Text,
    Number,
    Integer,
    Boolean,
    Enum,
    Array,
    Object,
    Unsupported,
}

public sealed record JsonSchemaFormField(
    string Path,
    string Label,
    string GroupId,
    JsonSchemaFieldKind Kind,
    bool IsRequired,
    bool IsReadOnly,
    string HelpText,
    string? Unit,
    IReadOnlyList<string> Options,
    double? Minimum,
    double? Maximum,
    JsonNode? Value,
    string RawSchemaJson)
{
    public string ValueText => JsonSchemaFormModel.FormatValue(Value);
}

public sealed class JsonSchemaFormModel
{
    private readonly JsonObject _parameters;
    private readonly List<JsonSchemaFormField> _fields;

    private JsonSchemaFormModel(JsonObject parameters, List<JsonSchemaFormField> fields)
    {
        _parameters = parameters;
        _fields = fields;
    }

    public IReadOnlyList<JsonSchemaFormField> Fields => _fields;

    public static JsonSchemaFormModel Create(
        OperatorDefinition definition,
        IReadOnlyDictionary<string, JsonNode?> parameters)
    {
        ArgumentNullException.ThrowIfNull(definition);
        ArgumentNullException.ThrowIfNull(parameters);

        var values = new JsonObject();
        foreach (var pair in parameters)
        {
            values[pair.Key] = pair.Value?.DeepClone();
        }

        var schema = ToObject(definition.ParameterSchema);
        var hints = definition.ParameterUi.ToDictionary(
            hint => hint.ParameterPath,
            StringComparer.Ordinal);
        var fields = new List<JsonSchemaFormField>();
        BuildObjectFields(schema, values, string.Empty, hints, fields);
        return new JsonSchemaFormModel(values, fields);
    }

    public bool TrySetValue(string path, string? text, out string? error)
    {
        var index = _fields.FindIndex(field =>
            string.Equals(field.Path, path, StringComparison.Ordinal));
        if (index < 0)
        {
            error = $"Unknown parameter path {path}.";
            return false;
        }

        var field = _fields[index];
        if (field.IsReadOnly)
        {
            error = $"Parameter {path} is preserved as read-only because its schema is unsupported.";
            return false;
        }

        if (!TryParse(field, text, out var value, out error))
        {
            return false;
        }

        SetAtPointer(_parameters, path, value);
        _fields[index] = field with { Value = value?.DeepClone() };
        return true;
    }

    public IReadOnlyDictionary<string, JsonNode?> BuildParameters() =>
        _parameters.ToDictionary(
            pair => pair.Key,
            pair => pair.Value?.DeepClone(),
            StringComparer.Ordinal);

    internal static string FormatValue(JsonNode? value)
    {
        if (value is null)
        {
            return string.Empty;
        }

        if (value is JsonValue jsonValue && jsonValue.TryGetValue<string>(out var text))
        {
            return text;
        }

        if (value is JsonValue boolValue && boolValue.TryGetValue<bool>(out var flag))
        {
            return flag ? "true" : "false";
        }

        return value.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
    }

    private static void BuildObjectFields(
        JsonObject schema,
        JsonObject values,
        string parentPath,
        IReadOnlyDictionary<string, ParameterUiDefinition> hints,
        List<JsonSchemaFormField> fields)
    {
        var required = schema["required"] is JsonArray requiredArray
            ? requiredArray
                .Select(item => item?.GetValue<string>())
                .OfType<string>()
                .ToHashSet(StringComparer.Ordinal)
            : new HashSet<string>(StringComparer.Ordinal);
        var properties = schema["properties"] as JsonObject ?? new JsonObject();

        foreach (var property in properties)
        {
            var propertySchema = property.Value as JsonObject ?? new JsonObject();
            var path = $"{parentPath}/{Escape(property.Key)}";
            values.TryGetPropertyValue(property.Key, out var value);
            var type = SchemaType(propertySchema);
            if (type == "object" && propertySchema["properties"] is JsonObject)
            {
                var childValues = value as JsonObject;
                if (childValues is null)
                {
                    childValues = new JsonObject();
                    values[property.Key] = childValues;
                }

                BuildObjectFields(propertySchema, childValues, path, hints, fields);
                continue;
            }

            hints.TryGetValue(path, out var hint);
            var kind = Kind(propertySchema, hint);
            var options = EnumOptions(propertySchema);
            fields.Add(new JsonSchemaFormField(
                path,
                hint?.Label ?? Humanize(property.Key),
                hint?.GroupId ?? "parameters",
                kind,
                required.Contains(property.Key),
                kind is JsonSchemaFieldKind.Unsupported,
                hint?.HelpText ?? propertySchema["description"]?.GetValue<string>() ?? string.Empty,
                hint?.Unit,
                options,
                Number(propertySchema, "minimum"),
                Number(propertySchema, "maximum"),
                value?.DeepClone(),
                propertySchema.ToJsonString()));
        }

        foreach (var value in values)
        {
            if (properties.ContainsKey(value.Key))
            {
                continue;
            }

            var path = $"{parentPath}/{Escape(value.Key)}";
            fields.Add(new JsonSchemaFormField(
                path,
                Humanize(value.Key),
                "preserved",
                JsonSchemaFieldKind.Unsupported,
                false,
                true,
                "This value is not described by the installed operator schema. It is preserved without interpretation.",
                null,
                [],
                null,
                null,
                value.Value?.DeepClone(),
                "{}"));
        }
    }

    private static bool TryParse(
        JsonSchemaFormField field,
        string? text,
        out JsonNode? value,
        out string? error)
    {
        text ??= string.Empty;
        try
        {
            switch (field.Kind)
            {
                case JsonSchemaFieldKind.Text:
                    value = JsonValue.Create(text);
                    break;
                case JsonSchemaFieldKind.Number:
                    if (!double.TryParse(
                            text,
                            NumberStyles.Float,
                            CultureInfo.InvariantCulture,
                            out var number) || !double.IsFinite(number))
                    {
                        throw new FormatException("Enter a finite number using '.' as the decimal separator.");
                    }

                    if (field.Minimum is double minimum && number < minimum ||
                        field.Maximum is double maximum && number > maximum)
                    {
                        throw new FormatException(
                            $"Value must be between {field.Minimum?.ToString(CultureInfo.InvariantCulture) ?? "-∞"} and {field.Maximum?.ToString(CultureInfo.InvariantCulture) ?? "+∞"}.");
                    }

                    value = JsonValue.Create(number);
                    break;
                case JsonSchemaFieldKind.Integer:
                    if (!long.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var integer))
                    {
                        throw new FormatException("Enter a whole number.");
                    }

                    if (field.Minimum is double integerMinimum && integer < integerMinimum ||
                        field.Maximum is double integerMaximum && integer > integerMaximum)
                    {
                        throw new FormatException("The whole number is outside the schema range.");
                    }

                    value = JsonValue.Create(integer);
                    break;
                case JsonSchemaFieldKind.Boolean:
                    if (!bool.TryParse(text, out var flag))
                    {
                        throw new FormatException("Enter true or false.");
                    }

                    value = JsonValue.Create(flag);
                    break;
                case JsonSchemaFieldKind.Enum:
                    if (!field.Options.Contains(text, StringComparer.Ordinal))
                    {
                        throw new FormatException("Choose a value supplied by the operator schema.");
                    }

                    value = JsonValue.Create(text);
                    break;
                case JsonSchemaFieldKind.Array:
                    value = JsonNode.Parse(text);
                    if (value is not JsonArray)
                    {
                        throw new FormatException("Enter a JSON array.");
                    }
                    break;
                case JsonSchemaFieldKind.Object:
                    value = JsonNode.Parse(text);
                    if (value is not JsonObject)
                    {
                        throw new FormatException("Enter a JSON object.");
                    }
                    break;
                default:
                    throw new FormatException("This schema shape is read-only.");
            }
        }
        catch (JsonException exception)
        {
            value = null;
            error = exception.Message;
            return false;
        }
        catch (FormatException exception)
        {
            value = null;
            error = exception.Message;
            return false;
        }

        error = null;
        return true;
    }

    private static JsonSchemaFieldKind Kind(
        JsonObject schema,
        ParameterUiDefinition? hint)
    {
        if (schema.ContainsKey("oneOf") || schema.ContainsKey("anyOf") || schema.ContainsKey("allOf"))
        {
            return JsonSchemaFieldKind.Unsupported;
        }

        if (schema["enum"] is JsonArray)
        {
            return JsonSchemaFieldKind.Enum;
        }

        if (hint is not null)
        {
            var hinted = hint.Control switch
            {
                ParameterControlKind.Number or ParameterControlKind.Slider => JsonSchemaFieldKind.Number,
                ParameterControlKind.Text or ParameterControlKind.Formula => JsonSchemaFieldKind.Text,
                ParameterControlKind.Select => JsonSchemaFieldKind.Enum,
                ParameterControlKind.MultiSelect => JsonSchemaFieldKind.Array,
                ParameterControlKind.Checkbox => JsonSchemaFieldKind.Boolean,
                _ => JsonSchemaFieldKind.Unsupported,
            };
            if (hinted is not JsonSchemaFieldKind.Enum || schema["enum"] is JsonArray)
            {
                return hinted;
            }
        }

        return SchemaType(schema) switch
        {
            "string" => JsonSchemaFieldKind.Text,
            "number" => JsonSchemaFieldKind.Number,
            "integer" => JsonSchemaFieldKind.Integer,
            "boolean" => JsonSchemaFieldKind.Boolean,
            "array" => JsonSchemaFieldKind.Array,
            "object" => JsonSchemaFieldKind.Object,
            _ => JsonSchemaFieldKind.Unsupported,
        };
    }

    private static IReadOnlyList<string> EnumOptions(JsonObject schema) =>
        schema["enum"] is JsonArray options
            ? options.Select(FormatValue).ToArray()
            : [];

    private static string? SchemaType(JsonObject schema) =>
        schema["type"] is JsonValue value && value.TryGetValue<string>(out var type)
            ? type
            : null;

    private static double? Number(JsonObject schema, string key)
    {
        if (schema[key] is not JsonValue value)
        {
            return null;
        }

        if (value.TryGetValue<double>(out var number))
        {
            return number;
        }

        return value.TryGetValue<long>(out var integer) ? integer : null;
    }

    private static JsonObject ToObject(IReadOnlyDictionary<string, JsonElement> source)
    {
        var result = new JsonObject();
        foreach (var pair in source)
        {
            result[pair.Key] = JsonNode.Parse(pair.Value.GetRawText());
        }
        return result;
    }

    private static void SetAtPointer(JsonObject root, string pointer, JsonNode? value)
    {
        if (string.IsNullOrWhiteSpace(pointer) || pointer[0] != '/')
        {
            throw new ArgumentException("Parameter paths must be JSON pointers.", nameof(pointer));
        }

        var segments = pointer[1..]
            .Split('/', StringSplitOptions.None)
            .Select(Unescape)
            .ToArray();
        var current = root;
        for (var index = 0; index < segments.Length - 1; index++)
        {
            if (current[segments[index]] is not JsonObject child)
            {
                child = new JsonObject();
                current[segments[index]] = child;
            }
            current = child;
        }
        current[segments[^1]] = value?.DeepClone();
    }

    private static string Humanize(string value) =>
        string.Join(' ', value.Split('_', StringSplitOptions.RemoveEmptyEntries)
            .Select(word => char.ToUpperInvariant(word[0]) + word[1..]));

    private static string Escape(string value) => value.Replace("~", "~0").Replace("/", "~1");

    private static string Unescape(string value) => value.Replace("~1", "/").Replace("~0", "~");
}
