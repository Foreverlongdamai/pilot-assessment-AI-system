namespace PilotAssessment.Desktop.Core.Contracts;

public sealed record ModelEditSessionStatus(
    string ContractId,
    string ContractVersion,
    string SessionId,
    string ModelLibraryId,
    string BaseFingerprint,
    int Cursor,
    int LatestSequence,
    bool Dirty,
    bool CanUndo,
    bool CanRedo,
    int ChangeCount,
    bool Recovered);

public sealed record ModelEditSessionStatusResponse(
    ModelEditSessionStatus EditSession,
    string TraceId);

public sealed record ModelEditSessionMutationRequest(
    string Actor,
    string TransactionId);

public sealed record ModelEditSessionMutationResponse(
    ModelEditSessionStatus EditSession,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId,
    string[]? ChangedNodeIds = null,
    string[]? ChangedSchemeIds = null,
    int? DiscardedChangeCount = null);

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

public sealed record CptValidationDiagnostic(
    string Code,
    ModelDiagnosticSeverity Severity,
    string Location,
    string Message);

public sealed record CptValidationOutcome(
    bool Executable,
    int RequiredRowCount,
    int RequiredCellCount,
    CptValidationDiagnostic[] Diagnostics);

public sealed record CptInspectRequest(string NodeId);

public sealed record CptInspectResponse(
    CptValidationOutcome Validation,
    CptEditorState Editor,
    string TraceId);

public sealed record CptRowsUpdateRequest(
    string NodeId,
    double[][] Rows,
    int ExpectedSemanticRevision,
    string Actor,
    string TransactionId);

public sealed record CptMaterializeRequest(
    string NodeId,
    string Strategy,
    double[]? Weights,
    double WeakestLinkStrength,
    double Sigma,
    int ExpectedSemanticRevision,
    string Actor,
    string TransactionId);

public sealed record ProbabilisticParentReorderRequest(
    string ChildNodeId,
    string[] OrderedParentNodeIds,
    int ExpectedSemanticRevision,
    string Actor,
    string TransactionId);

public sealed record ModelNodeStatesReplaceRequest(
    string NodeId,
    VariableState[] States,
    string Outcome,
    IReadOnlyDictionary<string, int> ExpectedSemanticRevisions,
    string Actor,
    string TransactionId);

public sealed record ModelNodeStatesMutationResponse(
    ModelNode[] Nodes,
    string[] AffectedSchemeIds,
    CanonicalModelDiff Diff,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);
