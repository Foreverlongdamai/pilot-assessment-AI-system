using System.Text.Json;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>Preserves parameter ownership and source attribution when editing a model.</summary>
public static class SceneSkillModelEditing
{
    public static SceneSkillModel Copy(SceneSkillModel model) => JsonSerializer.Deserialize(
        JsonSerializer.SerializeToUtf8Bytes(model, SceneJsonContext.Default.SceneSkillModel), SceneJsonContext.Default.SceneSkillModel)!;

    public static bool ParametersEqual(SceneSkillModel first, SceneSkillModel second) =>
        first.InferenceMethod == second.InferenceMethod
        && ((first.Compensation is null && second.Compensation is null)
            || (first.Compensation is not null && second.Compensation is not null
                && first.Compensation.Alpha == second.Compensation.Alpha))
        && first.Prior.SequenceEqual(second.Prior)
        && first.StateScores.SequenceEqual(second.StateScores)
        && first.CheckpointModels.Count == second.CheckpointModels.Count
            && first.CheckpointModels.All(pair => second.CheckpointModels.TryGetValue(pair.Key, out var other)
            && pair.Value.States.SequenceEqual(other.States)
            && pair.Value.Probabilities.Count == other.Probabilities.Count
            && pair.Value.Probabilities.Select((row, index) => row.SequenceEqual(other.Probabilities[index])).All(equal => equal));

}
