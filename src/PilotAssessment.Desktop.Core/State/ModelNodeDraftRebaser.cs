using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

public static class ModelNodeDraftRebaser
{
    public static ModelNode Rebase(ModelNode draft, ModelNode canonical)
    {
        ArgumentNullException.ThrowIfNull(draft);
        ArgumentNullException.ThrowIfNull(canonical);
        if (!string.Equals(draft.NodeId, canonical.NodeId, StringComparison.Ordinal) ||
            draft.NodeKind != canonical.NodeKind)
        {
            throw new ArgumentException("A local node intent can only rebase onto the same canonical node.");
        }

        return canonical with
        {
            Name = draft.Name,
            ShortName = draft.ShortName,
            Description = draft.Description,
            Tags = draft.Tags,
            Group = draft.Group,
            Definition = RebaseDefinition(draft.Definition, canonical.Definition),
        };
    }

    private static ModelNodeDefinition RebaseDefinition(
        ModelNodeDefinition draft,
        ModelNodeDefinition canonical) =>
        (draft, canonical) switch
        {
            (RawInputNodeDefinition local, RawInputNodeDefinition) => local,
            (EvidenceNodeDefinition local, EvidenceNodeDefinition current) => current with
            {
                Recipe = local.Recipe,
                ObservationMapping = local.ObservationMapping,
                ObservationPolicy = local.ObservationPolicy,
                ModalityAttributionWeights = local.ModalityAttributionWeights,
                HelpText = local.HelpText,
            },
            (BnNodeDefinition local, BnNodeDefinition current) => current with
            {
                NodeRole = local.NodeRole,
                Documentation = local.Documentation,
                ScientificStatus = local.ScientificStatus,
                ReportingMetadata = local.ReportingMetadata,
                HelpText = local.HelpText,
            },
            _ => throw new ArgumentException("Local and canonical node definitions have different kinds."),
        };
}
