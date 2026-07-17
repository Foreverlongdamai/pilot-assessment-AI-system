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
