using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.Contracts;

public enum ModelNodeKind
{
    [JsonStringEnumMemberName("raw_input")]
    RawInput,
    [JsonStringEnumMemberName("evidence")]
    Evidence,
    [JsonStringEnumMemberName("bn")]
    Bn,
}

public enum ModelObjectKind
{
    [JsonStringEnumMemberName("node")]
    Node,
    [JsonStringEnumMemberName("scheme")]
    Scheme,
}

public enum ModelObjectLifecycle
{
    [JsonStringEnumMemberName("active")]
    Active,
    [JsonStringEnumMemberName("archived")]
    Archived,
}

public enum ModelTechnicalStatus
{
    [JsonStringEnumMemberName("executable")]
    Executable,
    [JsonStringEnumMemberName("incomplete")]
    Incomplete,
    [JsonStringEnumMemberName("blocked")]
    Blocked,
}

public enum ModelDiagnosticSeverity
{
    [JsonStringEnumMemberName("info")]
    Info,
    [JsonStringEnumMemberName("warning")]
    Warning,
    [JsonStringEnumMemberName("error")]
    Error,
}

public enum RawInputFamily
{
    [JsonStringEnumMemberName("X")]
    X,
    [JsonStringEnumMemberName("U")]
    U,
    [JsonStringEnumMemberName("I")]
    I,
    [JsonStringEnumMemberName("G")]
    G,
    [JsonStringEnumMemberName("P")]
    P,
    [JsonStringEnumMemberName("pilot_camera")]
    PilotCamera,
}

public enum RawResourceRole
{
    [JsonStringEnumMemberName("stream")]
    Stream,
    [JsonStringEnumMemberName("task_reference")]
    TaskReference,
    [JsonStringEnumMemberName("annotation")]
    Annotation,
    [JsonStringEnumMemberName("event")]
    Event,
    [JsonStringEnumMemberName("aoi_definition")]
    AoiDefinition,
    [JsonStringEnumMemberName("derived_resource")]
    DerivedResource,
}

public enum ModelGraphEdgeKind
{
    [JsonStringEnumMemberName("extraction")]
    Extraction,
    [JsonStringEnumMemberName("probabilistic")]
    Probabilistic,
}

public enum ModelChangeKind
{
    [JsonStringEnumMemberName("create")]
    Create,
    [JsonStringEnumMemberName("update")]
    Update,
    [JsonStringEnumMemberName("archive")]
    Archive,
    [JsonStringEnumMemberName("undo")]
    Undo,
    [JsonStringEnumMemberName("redo")]
    Redo,
    [JsonStringEnumMemberName("migrate")]
    Migrate,
}

public enum ModelScientificStatus
{
    [JsonStringEnumMemberName("starter_template")]
    StarterTemplate,
    [JsonStringEnumMemberName("engineering_default")]
    EngineeringDefault,
    [JsonStringEnumMemberName("expert_defined")]
    ExpertDefined,
    [JsonStringEnumMemberName("calibrated")]
    Calibrated,
}

public enum ComponentSource
{
    [JsonStringEnumMemberName("engineering_default")]
    EngineeringDefault,
    [JsonStringEnumMemberName("expert_defined")]
    ExpertDefined,
    [JsonStringEnumMemberName("calibrated")]
    Calibrated,
    [JsonStringEnumMemberName("imported")]
    Imported,
}

public enum BnNodeRole
{
    [JsonStringEnumMemberName("aggregate_competency")]
    AggregateCompetency,
    [JsonStringEnumMemberName("sub_skill")]
    SubSkill,
    [JsonStringEnumMemberName("latent")]
    Latent,
    [JsonStringEnumMemberName("derived")]
    Derived,
    [JsonStringEnumMemberName("custom")]
    Custom,
}

public enum ObservationPolicy
{
    [JsonStringEnumMemberName("hard")]
    Hard,
    [JsonStringEnumMemberName("virtual")]
    Virtual,
    [JsonStringEnumMemberName("hard_or_virtual")]
    HardOrVirtual,
}

public enum CptMode
{
    [JsonStringEnumMemberName("manual")]
    Manual,
    [JsonStringEnumMemberName("generated")]
    Generated,
    [JsonStringEnumMemberName("incomplete")]
    Incomplete,
}

public enum SourceKind
{
    [JsonStringEnumMemberName("raw_stream")]
    RawStream,
    [JsonStringEnumMemberName("session_semantic")]
    SessionSemantic,
    [JsonStringEnumMemberName("task_semantic")]
    TaskSemantic,
    [JsonStringEnumMemberName("derived_artifact")]
    DerivedArtifact,
    [JsonStringEnumMemberName("evidence_observation")]
    EvidenceObservation,
}

public enum RawModality
{
    [JsonStringEnumMemberName("X")]
    X,
    [JsonStringEnumMemberName("U")]
    U,
    [JsonStringEnumMemberName("I")]
    I,
    [JsonStringEnumMemberName("G")]
    G,
    [JsonStringEnumMemberName("EEG")]
    Eeg,
    [JsonStringEnumMemberName("ECG")]
    Ecg,
    [JsonStringEnumMemberName("pilot_camera")]
    PilotCamera,
}

public enum RecipeLifecycle
{
    [JsonStringEnumMemberName("active")]
    Active,
    [JsonStringEnumMemberName("disabled")]
    Disabled,
    [JsonStringEnumMemberName("retired")]
    Retired,
}

public enum RecipeScientificStatus
{
    [JsonStringEnumMemberName("starter_template")]
    StarterTemplate,
    [JsonStringEnumMemberName("expert_defined")]
    ExpertDefined,
    [JsonStringEnumMemberName("calibrated")]
    Calibrated,
}

public enum InputBindingKind
{
    [JsonStringEnumMemberName("stream")]
    Stream,
    [JsonStringEnumMemberName("semantic")]
    Semantic,
    [JsonStringEnumMemberName("reference")]
    Reference,
}

public enum OperatorFamily
{
    [JsonStringEnumMemberName("input")]
    Input,
    [JsonStringEnumMemberName("temporal")]
    Temporal,
    [JsonStringEnumMemberName("signal")]
    Signal,
    [JsonStringEnumMemberName("event")]
    Event,
    [JsonStringEnumMemberName("gaze_vision")]
    GazeVision,
    [JsonStringEnumMemberName("flight_geometry")]
    FlightGeometry,
    [JsonStringEnumMemberName("statistics")]
    Statistics,
    [JsonStringEnumMemberName("composition")]
    Composition,
    [JsonStringEnumMemberName("aggregation")]
    Aggregation,
    [JsonStringEnumMemberName("scoring")]
    Scoring,
}

public enum PortCardinality
{
    [JsonStringEnumMemberName("one")]
    One,
    [JsonStringEnumMemberName("optional")]
    Optional,
    [JsonStringEnumMemberName("many")]
    Many,
}

public enum TemporalSemantics
{
    [JsonStringEnumMemberName("timeless")]
    Timeless,
    [JsonStringEnumMemberName("sampled")]
    Sampled,
    [JsonStringEnumMemberName("point")]
    Point,
    [JsonStringEnumMemberName("interval")]
    Interval,
    [JsonStringEnumMemberName("mixed")]
    Mixed,
}

public enum TraceCapability
{
    [JsonStringEnumMemberName("none")]
    None,
    [JsonStringEnumMemberName("summary")]
    Summary,
    [JsonStringEnumMemberName("full")]
    Full,
}

public enum OperatorImplementationSource
{
    [JsonStringEnumMemberName("built_in")]
    BuiltIn,
    [JsonStringEnumMemberName("trusted_extension")]
    TrustedExtension,
}

public enum ParameterControlKind
{
    [JsonStringEnumMemberName("number")]
    Number,
    [JsonStringEnumMemberName("slider")]
    Slider,
    [JsonStringEnumMemberName("text")]
    Text,
    [JsonStringEnumMemberName("select")]
    Select,
    [JsonStringEnumMemberName("multi_select")]
    MultiSelect,
    [JsonStringEnumMemberName("checkbox")]
    Checkbox,
    [JsonStringEnumMemberName("formula")]
    Formula,
}

public enum OutputRole
{
    [JsonStringEnumMemberName("primary_value")]
    PrimaryValue,
    [JsonStringEnumMemberName("raw_metric")]
    RawMetric,
    [JsonStringEnumMemberName("breakdown")]
    Breakdown,
    [JsonStringEnumMemberName("trace")]
    Trace,
}

public enum ScoringMode
{
    [JsonStringEnumMemberName("ordered_dau")]
    OrderedDau,
    [JsonStringEnumMemberName("soft_likelihood")]
    SoftLikelihood,
    [JsonStringEnumMemberName("custom_operator")]
    CustomOperator,
}

public sealed record ModelDiagnostic(
    string Code,
    ModelDiagnosticSeverity Severity,
    string Location,
    string Message,
    IReadOnlyDictionary<string, JsonNode?> Details);

public sealed record ModelNodeRef(string NodeId, ModelNodeKind NodeKind);

public sealed record NodeLayout(string NodeId, double X, double Y);

public sealed record PortType(
    string ValueType,
    PortCardinality Cardinality,
    TemporalSemantics TemporalSemantics,
    string? Unit);

public sealed record OperatorPortDefinition(
    string PortId,
    string Name,
    string Description,
    PortType PortType);

public sealed record ParameterUiDefinition(
    string ParameterPath,
    string Label,
    string GroupId,
    ParameterControlKind Control,
    string HelpText,
    string? Unit);

public sealed record OperatorDefinition(
    string ContractId,
    string ContractVersion,
    string OperatorId,
    string ImplementationVersion,
    OperatorFamily Family,
    string Name,
    string Description,
    string? Pseudocode,
    OperatorPortDefinition[] InputPorts,
    OperatorPortDefinition[] OutputPorts,
    IReadOnlyDictionary<string, JsonElement> ParameterSchema,
    ParameterUiDefinition[] ParameterUi,
    TraceCapability TraceCapability,
    OperatorImplementationSource ImplementationSource,
    string ImplementationRef);

public sealed record RecipeAnchor(
    string AnchorId,
    string Name,
    string Description,
    RecipeLifecycle Lifecycle,
    RecipeScientificStatus ScientificStatus);

public sealed record RecipeInputBinding(
    string BindingId,
    InputBindingKind Kind,
    string SourceId,
    string Name,
    PortType DeclaredType,
    IReadOnlyDictionary<string, JsonElement> Selector);

public sealed record NodePortReference(string NodeId, string PortId);

public sealed record RecipeNode(
    string NodeId,
    string OperatorId,
    string OperatorVersion,
    string? InputBindingId,
    IReadOnlyDictionary<string, JsonNode?> Parameters);

public sealed record RecipeEdge(
    string EdgeId,
    NodePortReference Source,
    NodePortReference Target,
    string? TargetSlotId);

public sealed record RecipeGraph(RecipeNode[] Nodes, RecipeEdge[] Edges);

public sealed record RecipeOutputBinding(
    string OutputId,
    OutputRole Role,
    string Name,
    NodePortReference Source,
    string? Unit);

public sealed record RecipeScoring(
    ScoringMode Mode,
    NodePortReference? Input,
    IReadOnlyDictionary<string, JsonNode?> Parameters,
    string? CustomOperatorId,
    string? CustomOperatorVersion);

public sealed record RecipeDocumentation(
    string Summary,
    string[] Assumptions,
    IReadOnlyDictionary<string, string> ParameterNotes,
    string[] References);

public sealed record RecipeUiGroup(string GroupId, string Label, string[] ParameterPaths);

public sealed record RecipeUiMetadata(
    RecipeUiGroup[] Groups,
    IReadOnlyDictionary<string, JsonElement> PreferredLayout);

public sealed record EvidenceRecipe(
    string ContractId,
    string ContractVersion,
    string RecipeId,
    int RecipeVersion,
    RecipeAnchor Anchor,
    RecipeInputBinding[] Inputs,
    RecipeGraph Graph,
    RecipeOutputBinding[] Outputs,
    RecipeScoring? Scoring,
    RecipeDocumentation Documentation,
    RecipeUiMetadata Ui);

public sealed record VariableState(string StateId, string Label, string Description);

public sealed record SourceDescriptor(
    string ContractId,
    string ContractVersion,
    string SourceId,
    SourceKind Kind,
    string Name,
    string Description,
    PortType DeclaredType,
    RawModality? RawModality,
    string[] SourceDependencies,
    IReadOnlyDictionary<string, JsonElement> Metadata,
    string ContentHash);

public sealed record EvidenceDataBinding(
    string RecipeInputBindingId,
    ModelNodeRef RawInputNode);

public sealed record NodeCpt(
    string CptId,
    ModelNodeRef ChildNode,
    ModelNodeRef[] OrderedParentNodes,
    string[] ChildStateIds,
    string[][] OrderedParentStateIds,
    double[][] MaterializedProbabilities,
    CptMode Mode,
    IReadOnlyDictionary<string, JsonElement> GeneratorMetadata,
    ComponentSource Source);

public sealed record CptEditorState(
    ModelNodeRef ChildNode,
    ModelNodeRef[] OrderedParentNodes,
    string[] ChildStateIds,
    string[][] OrderedParentStateIds,
    double[][] MaterializedProbabilities,
    CptMode Mode,
    int RequiredRowCount,
    int RequiredCellCount);

[JsonPolymorphic(TypeDiscriminatorPropertyName = "definition_kind")]
[JsonDerivedType(typeof(RawInputNodeDefinition), "raw_input")]
[JsonDerivedType(typeof(EvidenceNodeDefinition), "evidence")]
[JsonDerivedType(typeof(BnNodeDefinition), "bn")]
public abstract record ModelNodeDefinition;

public sealed record RawInputNodeDefinition(
    RawInputFamily? Family,
    RawResourceRole ResourceRole,
    SourceDescriptor SourceDescriptor,
    IReadOnlyDictionary<string, JsonElement> Metadata,
    string? HelpTextZh,
    string? HelpTextEn) : ModelNodeDefinition;

public sealed record EvidenceNodeDefinition(
    EvidenceRecipe Recipe,
    EvidenceDataBinding[] DataBindings,
    VariableState[] OrderedObservationStates,
    IReadOnlyDictionary<string, JsonElement> ObservationMapping,
    ModelNodeRef[] OrderedProbabilisticParentNodes,
    NodeCpt Cpt,
    ObservationPolicy ObservationPolicy,
    IReadOnlyDictionary<string, double> ModalityAttributionWeights,
    ModelScientificStatus ScientificStatus,
    IReadOnlyDictionary<string, JsonElement> Provenance,
    string? HelpTextZh,
    string? HelpTextEn) : ModelNodeDefinition;

public sealed record BnNodeDefinition(
    BnNodeRole NodeRole,
    VariableState[] OrderedStates,
    ModelNodeRef[] OrderedProbabilisticParentNodes,
    NodeCpt Cpt,
    string Documentation,
    ModelScientificStatus ScientificStatus,
    IReadOnlyDictionary<string, JsonElement> ReportingMetadata,
    IReadOnlyDictionary<string, JsonElement> Provenance,
    string? HelpTextZh,
    string? HelpTextEn) : ModelNodeDefinition;

public sealed record ModelNode(
    string ContractId,
    string ContractVersion,
    string NodeId,
    ModelNodeKind NodeKind,
    string? NameZh,
    string? NameEn,
    string? ShortNameZh,
    string? ShortNameEn,
    string? DescriptionZh,
    string? DescriptionEn,
    string[] Tags,
    string? Group,
    ModelObjectLifecycle Lifecycle,
    string? CopiedFromNodeId,
    ModelNodeDefinition Definition,
    NodeLayout GlobalLayout,
    int SemanticRevision,
    int LayoutRevision,
    ModelTechnicalStatus TechnicalStatus,
    ModelDiagnostic[] Diagnostics,
    string ContentHash,
    string LayoutHash,
    DateTime CreatedAt,
    DateTime UpdatedAt);

public sealed record TaskScheme(
    string ContractId,
    string ContractVersion,
    string SchemeId,
    string? NameZh,
    string? NameEn,
    string? DescriptionZh,
    string? DescriptionEn,
    string[] Tags,
    string? Group,
    ModelObjectLifecycle Lifecycle,
    string? CopiedFromSchemeId,
    string[] ExplicitActiveNodeIds,
    string[] ComputedActiveClosure,
    string[] OutputNodeIds,
    IReadOnlyDictionary<string, JsonElement> TaskBindings,
    NodeLayout[] LayoutOverrides,
    int SemanticRevision,
    int LayoutRevision,
    ModelTechnicalStatus TechnicalStatus,
    ModelDiagnostic[] Diagnostics,
    string ContentHash,
    string LayoutHash,
    DateTime CreatedAt,
    DateTime UpdatedAt);

public sealed record ModelGraphEdge(
    string EdgeId,
    ModelGraphEdgeKind EdgeKind,
    ModelNodeRef Parent,
    ModelNodeRef Child,
    string? RecipeInputBindingId);

public sealed record ModelGraphSnapshot(
    string ContractId,
    string ContractVersion,
    string ProjectId,
    TaskScheme Scheme,
    ModelNode[] Nodes,
    ModelGraphEdge[] Edges,
    DateTime GeneratedAt,
    string GraphHash);

public sealed record CanonicalModelDiff(
    string[] ChangedPaths,
    string[] AddedNodeIds,
    string[] RemovedNodeIds,
    string[] AddedEdgeIds,
    string[] RemovedEdgeIds,
    IReadOnlyDictionary<string, JsonElement> Metadata);

public sealed record DeactivationImpact(
    string ContractId,
    string ContractVersion,
    string SchemeId,
    int SchemeSemanticRevision,
    string RequestedNodeId,
    string[] ImpactedNodeIds,
    string[] ImpactedEdgeIds,
    string ImpactHash);

public sealed record ModelChangeEvent(
    string ContractId,
    string ContractVersion,
    string EventId,
    ModelObjectKind ObjectKind,
    string ObjectId,
    ModelChangeKind EventKind,
    string? ParentEventId,
    int SemanticRevision,
    int LayoutRevision,
    string? BeforeHash,
    string? AfterHash,
    CanonicalModelDiff Diff,
    string TransactionId,
    string ActorId,
    DateTime OccurredAt);
