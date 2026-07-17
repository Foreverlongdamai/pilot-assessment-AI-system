using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Controls.Editors;

public sealed partial class SchemaParameterForm : UserControl
{
    private readonly Dictionary<FrameworkElement, (JsonSchemaFormField Field, TextBlock Error)> _controls = [];
    private bool _rendering;

    public SchemaParameterForm()
    {
        InitializeComponent();
    }

    public JsonSchemaFormModel? Model { get; private set; }

    public event EventHandler? ParameterChanged;

    public void SetModel(JsonSchemaFormModel? model)
    {
        Model = model;
        _rendering = true;
        try
        {
            _controls.Clear();
            FieldsPanel.Children.Clear();
            if (model is null || model.Fields.Count == 0)
            {
                FieldsPanel.Children.Add(new TextBlock
                {
                    Text = model is null
                        ? "Select an installed operator node to edit its schema-driven parameters."
                        : "This operator has no editable parameters.",
                    Opacity = 0.68,
                    TextWrapping = TextWrapping.Wrap,
                });
                return;
            }

            foreach (var field in model.Fields)
            {
                FieldsPanel.Children.Add(CreateField(field));
            }
        }
        finally
        {
            _rendering = false;
        }
    }

    private FrameworkElement CreateField(JsonSchemaFormField field)
    {
        var panel = new StackPanel { Spacing = 5 };
        panel.Children.Add(new TextBlock
        {
            Text = field.Label + (field.IsRequired ? " *" : string.Empty),
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
        });
        if (!string.IsNullOrWhiteSpace(field.HelpText) || !string.IsNullOrWhiteSpace(field.Unit))
        {
            panel.Children.Add(new TextBlock
            {
                Text = string.Join(" · ", new[] { field.HelpText, field.Unit }
                    .Where(value => !string.IsNullOrWhiteSpace(value))),
                Opacity = 0.68,
                TextWrapping = TextWrapping.Wrap,
            });
        }

        FrameworkElement control = field.Kind switch
        {
            JsonSchemaFieldKind.Enum => EnumControl(field),
            JsonSchemaFieldKind.Boolean => BooleanControl(field),
            _ => TextControl(field),
        };
        var error = new TextBlock
        {
            Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.IndianRed),
            TextWrapping = TextWrapping.Wrap,
            Visibility = Visibility.Collapsed,
        };
        _controls[control] = (field, error);
        panel.Children.Add(control);
        panel.Children.Add(error);
        return panel;
    }

    private ComboBox EnumControl(JsonSchemaFormField field)
    {
        var control = new ComboBox
        {
            ItemsSource = field.Options,
            SelectedItem = field.ValueText,
            IsEnabled = !field.IsReadOnly,
            HorizontalAlignment = HorizontalAlignment.Stretch,
        };
        control.SelectionChanged += OnEnumChanged;
        return control;
    }

    private ToggleSwitch BooleanControl(JsonSchemaFormField field)
    {
        var control = new ToggleSwitch
        {
            IsOn = string.Equals(field.ValueText, "true", StringComparison.OrdinalIgnoreCase),
            IsEnabled = !field.IsReadOnly,
            OnContent = "True",
            OffContent = "False",
        };
        control.Toggled += OnBooleanChanged;
        return control;
    }

    private TextBox TextControl(JsonSchemaFormField field)
    {
        var multiline = field.Kind is JsonSchemaFieldKind.Array or JsonSchemaFieldKind.Object or
            JsonSchemaFieldKind.Unsupported;
        var control = new TextBox
        {
            Text = field.ValueText,
            IsReadOnly = field.IsReadOnly,
            AcceptsReturn = multiline,
            MinHeight = multiline ? 96 : 0,
            TextWrapping = multiline ? TextWrapping.Wrap : TextWrapping.NoWrap,
            Header = field.IsReadOnly ? "Preserved read-only JSON" : null,
        };
        control.LostFocus += OnTextLostFocus;
        return control;
    }

    private void OnEnumChanged(object sender, SelectionChangedEventArgs args)
    {
        if (!_rendering && sender is ComboBox control && control.SelectedItem is string value)
        {
            Apply(control, value);
        }
    }

    private void OnBooleanChanged(object sender, RoutedEventArgs args)
    {
        if (!_rendering && sender is ToggleSwitch control)
        {
            Apply(control, control.IsOn ? "true" : "false");
        }
    }

    private void OnTextLostFocus(object sender, RoutedEventArgs args)
    {
        if (!_rendering && sender is TextBox control && !control.IsReadOnly)
        {
            Apply(control, control.Text);
        }
    }

    private void Apply(FrameworkElement control, string text)
    {
        if (Model is null || !_controls.TryGetValue(control, out var metadata))
        {
            return;
        }

        if (Model.TrySetValue(metadata.Field.Path, text, out var error))
        {
            metadata.Error.Text = string.Empty;
            metadata.Error.Visibility = Visibility.Collapsed;
            ParameterChanged?.Invoke(this, EventArgs.Empty);
            return;
        }

        metadata.Error.Text = error;
        metadata.Error.Visibility = Visibility.Visible;
    }
}
