using System.Globalization;

using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

public sealed record CptGridDiagnostic(string Code, int? RowIndex, int? ColumnIndex, string Message);

public sealed record CptGridValidation(
    bool IsValid,
    int RowCount,
    int CellCount,
    IReadOnlyList<CptGridDiagnostic> Diagnostics);

public sealed record CptRectangularPasteResult(int RowCount, int ColumnCount);

/// <summary>
/// UI-only editable projection of one backend-owned CPT. This class validates
/// shape and probability text but never materializes or infers a Bayesian model.
/// </summary>
public sealed class CptGridModel
{
    public const double DefaultRowSumTolerance = 1e-9;

    private CptEditorState _editor;
    private double?[][] _values;

    public CptGridModel(CptEditorState editor)
    {
        _editor = editor;
        _values = CreateValues(editor);
    }

    public CptEditorState Editor => _editor;

    public int RowCount => _editor.RequiredRowCount;

    public int ColumnCount => _editor.ChildStateIds.Length;

    public IReadOnlyList<string> ChildStateIds => _editor.ChildStateIds;

    public IReadOnlyList<ModelNodeRef> OrderedParents => _editor.OrderedParentNodes;

    public double? GetCell(int rowIndex, int columnIndex)
    {
        CheckCell(rowIndex, columnIndex);
        return _values[rowIndex][columnIndex];
    }

    public void SetCell(int rowIndex, int columnIndex, double? value)
    {
        CheckCell(rowIndex, columnIndex);
        _values[rowIndex][columnIndex] = value;
    }

    public string ParentAssignmentLabel(int rowIndex)
    {
        var assignment = ParentAssignment(rowIndex);
        if (assignment.Count == 0)
        {
            return "Prior";
        }

        return string.Join(
            " · ",
            assignment.Select((stateId, index) =>
                $"{_editor.OrderedParentNodes[index].NodeId}={stateId}"));
    }

    public IReadOnlyList<string> ParentAssignment(int rowIndex)
    {
        if (rowIndex < 0 || rowIndex >= RowCount)
        {
            throw new ArgumentOutOfRangeException(nameof(rowIndex));
        }

        if (_editor.OrderedParentStateIds.Length == 0)
        {
            return [];
        }

        var remainder = rowIndex;
        var assignment = new string[_editor.OrderedParentStateIds.Length];
        for (var axis = _editor.OrderedParentStateIds.Length - 1; axis >= 0; axis--)
        {
            var states = _editor.OrderedParentStateIds[axis];
            if (states.Length == 0)
            {
                throw new InvalidOperationException("A CPT parent axis has no states.");
            }
            assignment[axis] = states[remainder % states.Length];
            remainder /= states.Length;
        }
        return assignment;
    }

    public CptRectangularPasteResult ApplyRectangularText(
        int startRow,
        int startColumn,
        string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        var lines = text
            .Replace("\r\n", "\n", StringComparison.Ordinal)
            .Replace('\r', '\n')
            .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (lines.Length == 0)
        {
            throw new FormatException("The pasted probability block is empty.");
        }

        var parsed = lines.Select(ParseRow).ToArray();
        var width = parsed[0].Length;
        if (width == 0 || parsed.Any(row => row.Length != width))
        {
            throw new FormatException("The pasted probability block must be rectangular.");
        }
        if (startRow < 0 || startColumn < 0 ||
            startRow + parsed.Length > RowCount || startColumn + width > ColumnCount)
        {
            throw new ArgumentOutOfRangeException(
                nameof(text),
                "The pasted probability block does not fit inside the CPT grid.");
        }

        for (var row = 0; row < parsed.Length; row++)
        {
            for (var column = 0; column < width; column++)
            {
                _values[startRow + row][startColumn + column] = parsed[row][column];
            }
        }
        return new CptRectangularPasteResult(parsed.Length, width);
    }

    public void NormalizeRow(int rowIndex)
    {
        if (rowIndex < 0 || rowIndex >= RowCount)
        {
            throw new ArgumentOutOfRangeException(nameof(rowIndex));
        }

        var values = _values[rowIndex];
        if (values.Any(value => value is null || !double.IsFinite(value.Value) || value.Value < 0))
        {
            throw new InvalidOperationException("A row can be normalized only after every cell is a finite non-negative number.");
        }
        var sum = values.Sum(value => value!.Value);
        if (!double.IsFinite(sum) || sum <= 0)
        {
            throw new InvalidOperationException("A row with a zero or non-finite sum cannot be normalized.");
        }
        for (var column = 0; column < values.Length; column++)
        {
            values[column] = values[column]!.Value / sum;
        }
    }

    public CptGridValidation Validate(double tolerance = DefaultRowSumTolerance)
    {
        var diagnostics = new List<CptGridDiagnostic>();
        if (RowCount != _values.Length)
        {
            diagnostics.Add(new CptGridDiagnostic(
                "cpt.row_count",
                null,
                null,
                $"Expected {RowCount} rows but found {_values.Length}."));
        }

        for (var row = 0; row < _values.Length; row++)
        {
            var values = _values[row];
            if (values.Length != ColumnCount)
            {
                diagnostics.Add(new CptGridDiagnostic(
                    "cpt.column_count",
                    row,
                    null,
                    $"Expected {ColumnCount} cells but found {values.Length}."));
                continue;
            }
            var sum = 0.0;
            for (var column = 0; column < values.Length; column++)
            {
                var value = values[column];
                if (value is null)
                {
                    diagnostics.Add(new CptGridDiagnostic(
                        "cpt.cell_missing",
                        row,
                        column,
                        "Probability is required."));
                    continue;
                }
                if (!double.IsFinite(value.Value) || value.Value < 0 || value.Value > 1)
                {
                    diagnostics.Add(new CptGridDiagnostic(
                        "cpt.cell_range",
                        row,
                        column,
                        "Probability must be finite and between 0 and 1."));
                    continue;
                }
                sum += value.Value;
            }
            if (values.All(value => value is not null && double.IsFinite(value.Value)) &&
                Math.Abs(sum - 1.0) > tolerance)
            {
                diagnostics.Add(new CptGridDiagnostic(
                    "cpt.row_sum",
                    row,
                    null,
                    $"Row sum is {sum.ToString("G12", CultureInfo.InvariantCulture)}; expected 1."));
            }
        }

        return new CptGridValidation(
            diagnostics.Count == 0,
            _values.Length,
            _values.Sum(row => row.Length),
            diagnostics);
    }

    public double[][] BuildBackendRows()
    {
        var validation = Validate();
        if (!validation.IsValid)
        {
            throw new InvalidOperationException(validation.Diagnostics[0].Message);
        }
        return _values
            .Select(row => row.Select(value => value!.Value).ToArray())
            .ToArray();
    }

    public void ReplaceCanonical(CptEditorState editor)
    {
        _editor = editor;
        _values = CreateValues(editor);
    }

    private static double?[][] CreateValues(CptEditorState editor)
    {
        var values = new double?[editor.RequiredRowCount][];
        for (var row = 0; row < values.Length; row++)
        {
            values[row] = new double?[editor.ChildStateIds.Length];
            if (row >= editor.MaterializedProbabilities.Length)
            {
                continue;
            }
            var source = editor.MaterializedProbabilities[row];
            for (var column = 0; column < Math.Min(source.Length, values[row].Length); column++)
            {
                values[row][column] = source[column];
            }
        }
        return values;
    }

    private static double[] ParseRow(string line)
    {
        var tokens = line.Contains('\t')
            ? line.Split('\t', StringSplitOptions.TrimEntries)
            : line.Split([',', ';', ' '], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        return tokens.Select(token =>
        {
            if (!double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out var value) ||
                !double.IsFinite(value) || value < 0 || value > 1)
            {
                throw new FormatException($"'{token}' is not a probability between 0 and 1.");
            }
            return value;
        }).ToArray();
    }

    private void CheckCell(int rowIndex, int columnIndex)
    {
        if (rowIndex < 0 || rowIndex >= RowCount)
        {
            throw new ArgumentOutOfRangeException(nameof(rowIndex));
        }
        if (columnIndex < 0 || columnIndex >= ColumnCount)
        {
            throw new ArgumentOutOfRangeException(nameof(columnIndex));
        }
    }
}
