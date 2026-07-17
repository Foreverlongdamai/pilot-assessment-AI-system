namespace PilotAssessment.Desktop.Core.Contracts;

public sealed record TaskSchemeListResponse(
    IReadOnlyList<TaskScheme> Schemes,
    string TraceId);

public sealed record TaskSchemeCreateRequest(
    TaskScheme Scheme,
    string Actor,
    string TransactionId);

public sealed record TaskSchemeCopyRequest(
    string SourceSchemeId,
    string NewSchemeId,
    string? NameZh,
    string? NameEn,
    string Actor,
    string TransactionId);

public sealed record TaskSchemeUpdateRequest(
    TaskScheme Scheme,
    int? ExpectedSemanticRevision,
    int? ExpectedLayoutRevision,
    string Actor,
    string TransactionId);

public sealed record TaskSchemeArchiveRequest(
    string SchemeId,
    int ExpectedSemanticRevision,
    string Actor,
    string TransactionId);

public sealed record TaskSchemeMutationResponse(
    TaskScheme Scheme,
    ModelGraphSnapshot Graph,
    int SemanticRevision,
    int LayoutRevision,
    ModelTechnicalStatus TechnicalStatus,
    CanonicalModelDiff Diff,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);

public sealed record ModelGraphGetRequest(string SchemeId);

public sealed record ModelGraphGetResponse(
    ModelGraphSnapshot Graph,
    string TraceId);

public sealed record ModelNodeCreateRequest(
    ModelNode Node,
    string Actor,
    string TransactionId);

public sealed record ModelNodeUpdateRequest(
    ModelNode Node,
    int? ExpectedSemanticRevision,
    int? ExpectedLayoutRevision,
    string Actor,
    string TransactionId);

public sealed record ModelNodeMutationResponse(
    ModelNode Node,
    string[] AffectedSchemeIds,
    int SemanticRevision,
    int LayoutRevision,
    ModelTechnicalStatus TechnicalStatus,
    CanonicalModelDiff Diff,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);

public sealed record ModelNodeUsage(
    string SchemeId,
    ModelObjectLifecycle SchemeLifecycle,
    bool ExplicitlyActive,
    bool ActiveInClosure,
    bool SelectedAsOutput);

public sealed record ModelNodeUsageListRequest(string NodeId);

public sealed record ModelNodeUsageListResponse(
    ModelNodeUsage[] Usages,
    string TraceId);

public sealed record ModelNodeHistoryListRequest(string NodeId);

public sealed record ModelNodeHistoryListResponse(
    ModelChangeEvent[] Events,
    string TraceId);

public sealed record OperatorCatalogListResponse(
    OperatorDefinition[] Operators,
    string TraceId);

public sealed record ModelNodePreviewRequest(
    string SessionRevisionId,
    string SchemeId,
    string NodeId,
    IReadOnlyDictionary<string, System.Text.Json.JsonElement> RuntimeParameters,
    string PreviewId);

public sealed record ModelNodePreviewResponse(
    CurrentModelRunSnapshot Preview,
    string TraceId);

public sealed record SchemeNodeActivationRequest(
    string SchemeId,
    string NodeId,
    int ExpectedSemanticRevision,
    string Actor,
    string TransactionId);

public sealed record SchemeDeactivationPreviewRequest(
    string SchemeId,
    string NodeId);

public sealed record SchemeDeactivationPreviewResponse(
    DeactivationImpact Impact,
    string TraceId);

public sealed record SchemeNodeDeactivationRequest(
    string SchemeId,
    string NodeId,
    int ExpectedSemanticRevision,
    string ImpactHash,
    string Actor,
    string TransactionId);

public sealed record GraphBatchApplyRequest(
    string SchemeId,
    string[] CopyNodeIds,
    string[] ActivateNodeIds,
    NodeLayout[] LayoutUpdates,
    int ExpectedSemanticRevision,
    int ExpectedLayoutRevision,
    string Actor,
    string TransactionId);

public sealed record LayoutUpdateRequest(
    string SchemeId,
    NodeLayout[] Positions,
    int ExpectedSemanticRevision,
    int ExpectedLayoutRevision,
    string Actor,
    string TransactionId);

public sealed record GraphBatchMutationResponse(
    ModelNode[] CopiedNodes,
    TaskScheme Scheme,
    ModelGraphSnapshot Graph,
    CanonicalModelDiff Diff,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);

public sealed record ProbabilisticEdgeAddRequest(
    string EdgeKind,
    string ChildNodeId,
    string ParentNodeId,
    string Strategy,
    int ExpectedSemanticRevision,
    string Actor,
    string TransactionId);

public sealed record ProbabilisticEdgeRemoveRequest(
    string EdgeKind,
    string ChildNodeId,
    string ParentNodeId,
    string Strategy,
    double[]? MarginalWeights,
    int ExpectedSemanticRevision,
    string Actor,
    string TransactionId);

public sealed record ExtractionEdgeAddRequest(
    string EdgeKind,
    string ChildNodeId,
    string ParentNodeId,
    string RecipeInputBindingId,
    EvidenceRecipe UpdatedRecipe,
    int ExpectedSemanticRevision,
    string Actor,
    string TransactionId);

public sealed record ExtractionEdgeRemoveRequest(
    string EdgeKind,
    string ChildNodeId,
    string? ParentNodeId,
    string RecipeInputBindingId,
    EvidenceRecipe UpdatedRecipe,
    int ExpectedSemanticRevision,
    string Actor,
    string TransactionId);

public sealed record CptMutationResponse(
    ModelNode Node,
    string[] AffectedSchemeIds,
    int SemanticRevision,
    CptEditorState Editor,
    CanonicalModelDiff Diff,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);
