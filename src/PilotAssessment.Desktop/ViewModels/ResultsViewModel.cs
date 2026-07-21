using System.Collections.ObjectModel;
using System.Text.Json;

using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.ViewModels;

public sealed record ResultRunItemViewModel(
    AssessmentRunV3 Run,
    string ResultId,
    string Title,
    string DetailText)
{
    public override string ToString() => $"{Title} · {DetailText}";
}

public sealed record ResultArtifactItemViewModel(
    string Role,
    ManagedArtifact Artifact)
{
    public string ArtifactId => Artifact.ArtifactId;
    public string SchemaId => Artifact.SchemaId ?? "—";
    public string SizeText => $"{Artifact.ByteSize:N0} bytes";
    public string PathText => Artifact.ManagedRelativePath;
}

public sealed record ProvenanceItemViewModel(string Label, string Value);

public partial class ResultsViewModel : ObservableObject
{
    private const long InlineJsonLimit = 2 * 1024 * 1024;
    private readonly IRunGateway _gateway;
    private readonly IManagedArtifactReader _artifactReader;
    private readonly ILocalizationLookup? _localization;
    private readonly ApplicationShellState? _shellState;
    private readonly SynchronizationContext? _uiContext;
    private long _loadGeneration;
    private int _initialized;
    private bool _wasDomainReady;

    [ObservableProperty]
    public partial ResultRunItemViewModel? SelectedRun { get; set; }

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial bool HasError { get; private set; }

    [ObservableProperty]
    public partial string ErrorMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string ResultSummaryText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string ScientificStatusText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string CoverageText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string InfluenceExplanationText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial bool HasLoadedResult { get; private set; }

    public ResultsViewModel(
        IRunGateway gateway,
        IManagedArtifactReader artifactReader,
        ILocalizationLookup? localization = null,
        ApplicationShellState? shellState = null)
    {
        _gateway = gateway;
        _artifactReader = artifactReader;
        _localization = localization;
        _shellState = shellState;
        _wasDomainReady = _shellState?.Snapshot.CanUseDomainCommands ?? true;
        _uiContext = SynchronizationContext.Current;
        _localization?.LanguageChanged += OnLanguageChanged;
        if (_shellState is not null)
        {
            _shellState.Changed += OnShellStateChanged;
        }
        RefreshStaticPresentation();
    }

    public ObservableCollection<ResultRunItemViewModel> Runs { get; } = [];

    public ObservableCollection<EvidenceResultProjection> EvidenceRows { get; } = [];

    public ObservableCollection<ObservationProjection> ObservationRows { get; } = [];

    public ObservableCollection<PosteriorProjection> PosteriorRows { get; } = [];

    public ObservableCollection<InfluenceProjection> InfluenceRows { get; } = [];

    public ObservableCollection<ResultArtifactItemViewModel> Artifacts { get; } = [];

    public ObservableCollection<ProvenanceItemViewModel> ProvenanceRows { get; } = [];

    public bool CanRefresh => !IsBusy;

    public bool CanLoad => !IsBusy && SelectedRun is not null;

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        if (Interlocked.Exchange(ref _initialized, 1) == 0)
        {
            if (_shellState?.Snapshot.CanUseDomainCommands is not false)
            {
                await RefreshAsync(cancellationToken);
            }
        }
    }

    [RelayCommand(CanExecute = nameof(CanRefresh))]
    private async Task RefreshAsync(CancellationToken cancellationToken = default)
    {
        await RunBusyAsync(async () =>
        {
            var previousResultId = SelectedRun?.ResultId;
            var currentRuns = await _gateway.ListCurrentRunsAsync(cancellationToken);
            Runs.Clear();
            foreach (var item in currentRuns
                .Where(item => !string.IsNullOrWhiteSpace(item.ResultId))
                .OrderByDescending(item => item.Run.RequestedAt))
            {
                Runs.Add(BuildRunItem(item.Run, item.ResultId!));
            }

            SelectedRun = Runs.FirstOrDefault(item => item.ResultId == previousResultId)
                ?? Runs.FirstOrDefault();
            if (SelectedRun is not null)
            {
                await LoadSelectedCoreAsync(cancellationToken);
            }
            else
            {
                ClearResult();
                StatusMessage = L("Results_NoCurrentResults", "No completed current-model result is stored in this project yet.");
            }
        });
    }

    [RelayCommand(CanExecute = nameof(CanLoad))]
    private async Task LoadSelectedAsync(CancellationToken cancellationToken = default)
    {
        await RunBusyAsync(() => LoadSelectedCoreAsync(cancellationToken));
    }

    [RelayCommand]
    private async Task OpenArtifactAsync(
        ResultArtifactItemViewModel? item,
        CancellationToken cancellationToken = default)
    {
        if (item is null)
        {
            return;
        }

        try
        {
            await _artifactReader.OpenAsync(item.Artifact, cancellationToken);
            StatusMessage = L("Results_ArtifactOpened", "The verified managed artifact was selected in Windows Explorer.");
        }
        catch (Exception error)
        {
            SetError(error);
        }
    }

    partial void OnSelectedRunChanged(ResultRunItemViewModel? value)
    {
        NotifyCommandStates();
    }

    partial void OnIsBusyChanged(bool value) => NotifyCommandStates();

    private async Task LoadSelectedCoreAsync(CancellationToken cancellationToken)
    {
        var selection = SelectedRun
            ?? throw new InvalidOperationException("Select a completed current-model run.");
        var generation = Interlocked.Increment(ref _loadGeneration);
        ClearResult();
        var result = await _gateway.GetResultAsync(selection.ResultId, null, cancellationToken);

        var descriptors = ArtifactDescriptors(result);
        var metadataTasks = descriptors.Select(async descriptor => new LoadedArtifact(
            descriptor.Role,
            descriptor.Reference,
            await _gateway.GetArtifactAsync(
                result.ResultId,
                descriptor.Reference.ArtifactId,
                cancellationToken))).ToArray();
        var loadedArtifacts = await Task.WhenAll(metadataTasks);
        if (generation != Volatile.Read(ref _loadGeneration))
        {
            return;
        }

        foreach (var loaded in loadedArtifacts)
        {
            Artifacts.Add(new ResultArtifactItemViewModel(loaded.Role, loaded.Artifact));
        }

        var evidenceArtifacts = loadedArtifacts
            .Where(item => item.Role.StartsWith("evidence-result-", StringComparison.Ordinal))
            .ToArray();
        var evidenceResults = new List<EvidenceRuntimeResult>(evidenceArtifacts.Length);
        foreach (var item in evidenceArtifacts)
        {
            evidenceResults.Add(await ReadJsonAsync(
                item.Artifact,
                PilotAssessmentJsonContext.Default.EvidenceRuntimeResult,
                cancellationToken));
        }

        var observationArtifact = RequireArtifact(loadedArtifacts, "observation-set");
        var posteriorArtifact = RequireArtifact(loadedArtifacts, "posterior");
        var traceArtifact = RequireArtifact(loadedArtifacts, "inference-trace");
        var observations = await ReadJsonAsync(
            observationArtifact.Artifact,
            PilotAssessmentJsonContext.Default.ObservationSet,
            cancellationToken);
        var posterior = await ReadJsonAsync(
            posteriorArtifact.Artifact,
            PilotAssessmentJsonContext.Default.PosteriorResult,
            cancellationToken);
        var trace = await ReadJsonAsync(
            traceArtifact.Artifact,
            PilotAssessmentJsonContext.Default.InferenceTrace,
            cancellationToken);
        if (generation != Volatile.Read(ref _loadGeneration))
        {
            return;
        }

        var nodeNames = BuildNodeNames(selection.Run);
        var componentRefs = evidenceResults
            .Select(item => new ComponentIdRef(ComponentKind.EvidenceVersion, item.EvidenceVersionId))
            .Concat(observations.Observations.Select(item => item.VariableId))
            .Concat(posterior.Posteriors.Select(item => item.VariableId))
            .Concat(trace.InfluenceEdges.SelectMany(item => new[]
            {
                item.ObservedVariableId,
                item.QueriedVariableId,
            }))
            .DistinctBy(item => $"{item.Kind}:{item.VersionId}")
            .ToArray();
        var componentNodeIds = await ResolveComponentNodeIdsAsync(
            componentRefs,
            nodeNames.Keys,
            cancellationToken);

        foreach (var item in evidenceResults)
        {
            var component = new ComponentIdRef(ComponentKind.EvidenceVersion, item.EvidenceVersionId);
            var nodeId = ResolveNodeId(component, componentNodeIds);
            EvidenceRows.Add(RunResultProjector.Evidence(item, nodeId, ResolveName(nodeId, nodeNames)));
        }

        foreach (var item in observations.Observations)
        {
            var nodeId = ResolveNodeId(item.VariableId, componentNodeIds);
            ObservationRows.Add(RunResultProjector.Observation(
                item,
                nodeId,
                ResolveName(nodeId, nodeNames)));
        }

        var priors = posterior.Priors.ToDictionary(
            item => $"{item.VariableId.Kind}:{item.VariableId.VersionId}",
            StringComparer.Ordinal);
        foreach (var item in posterior.Posteriors)
        {
            priors.TryGetValue($"{item.VariableId.Kind}:{item.VariableId.VersionId}", out var prior);
            var nodeId = ResolveNodeId(item.VariableId, componentNodeIds);
            PosteriorRows.Add(RunResultProjector.Posterior(
                item,
                prior,
                nodeId,
                ResolveName(nodeId, nodeNames)));
        }

        foreach (var item in trace.InfluenceEdges.OrderByDescending(item => item.L1Delta))
        {
            var observedId = ResolveNodeId(item.ObservedVariableId, componentNodeIds);
            var queriedId = ResolveNodeId(item.QueriedVariableId, componentNodeIds);
            InfluenceRows.Add(RunResultProjector.Influence(
                item,
                ResolveName(observedId, nodeNames),
                ResolveName(queriedId, nodeNames)));
        }

        BuildProvenance(selection.Run, result, loadedArtifacts);
        ResultSummaryText = F(
            "Results_ResultSummaryText",
            "{0} Evidence · {1} posterior variables · {2} artifacts",
            EvidenceRows.Count,
            PosteriorRows.Count,
            Artifacts.Count);
        ScientificStatusText = LocalizeScientificStatus(result.ScientificStatus);
        CoverageText = result.CoverageRefs.Length == 0
            ? L("Results_NoCoverageArtifacts", "No separate coverage artifact was emitted for this run.")
            : string.Format(
                L("Results_CoverageArtifacts", "{0} verified coverage artifact(s) are available below."),
                result.CoverageRefs.Length);
        HasLoadedResult = true;
        StatusMessage = L("Results_StatusLoaded", "Result artifacts were verified by the backend and projected read-only.");
    }

    private async Task<Dictionary<string, string>> ResolveComponentNodeIdsAsync(
        IReadOnlyList<ComponentIdRef> components,
        IEnumerable<string> currentNodeIds,
        CancellationToken cancellationToken)
    {
        var current = currentNodeIds.ToHashSet(StringComparer.Ordinal);
        var tasks = components.Select(async component =>
        {
            var sources = await _gateway.GetComponentSourceIdsAsync(component, cancellationToken);
            var nodeId = sources.FirstOrDefault(current.Contains) ?? component.VersionId;
            return new KeyValuePair<string, string>(ComponentKey(component), nodeId);
        });
        return (await Task.WhenAll(tasks)).ToDictionary(
            item => item.Key,
            item => item.Value,
            StringComparer.Ordinal);
    }

    private Dictionary<string, string> BuildNodeNames(AssessmentRunV3 run) =>
        run.Snapshot.ActiveNodes.ToDictionary(
            node => node.NodeId,
            node => ModelDisplayNameResolver.ForNode(node, preferShort: false),
            StringComparer.Ordinal);

    private void BuildProvenance(
        AssessmentRunV3 run,
        RunResultEnvelope result,
        IReadOnlyList<LoadedArtifact> artifacts)
    {
        AddProvenance("Result ID", result.ResultId);
        AddProvenance("Run ID", result.RunId);
        AddProvenance("Snapshot hash", result.SnapshotHash);
        AddProvenance("Result hash", result.ResultHash);
        AddProvenance("Session revision", run.Snapshot.SessionRevisionRef.SessionRevisionId);
        AddProvenance("Bundle root hash", run.Snapshot.SessionRevisionRef.BundleRootHash);
        AddProvenance("Task scheme", run.Snapshot.Scheme.SchemeId);
        AddProvenance("Scheme semantic revision", run.Snapshot.Scheme.SemanticRevision.ToString());
        AddProvenance("Scheme content hash", run.Snapshot.Scheme.ContentHash);
        AddProvenance("Runtime parameters hash", run.Snapshot.RuntimeParametersHash);
        AddProvenance(
            "Inference engine",
            $"{run.Snapshot.EngineIdentity.IdentityId} {run.Snapshot.EngineIdentity.Version} · {run.Snapshot.EngineIdentity.ContentHash}");
        AddProvenance("Locked operators", run.Snapshot.LockedOperatorIdentities.Length.ToString());
        AddProvenance("Numeric runtimes", run.Snapshot.NumericRuntimeIdentities.Length.ToString());
        AddProvenance("Verified artifacts", artifacts.Count.ToString());
    }

    private void AddProvenance(string label, string value) =>
        ProvenanceRows.Add(new ProvenanceItemViewModel(label, value));

    private static LoadedArtifact RequireArtifact(
        IEnumerable<LoadedArtifact> artifacts,
        string role) =>
        artifacts.FirstOrDefault(item => item.Role == role)
        ?? throw new InvalidDataException($"Run result is missing required {role} artifact metadata.");

    private async Task<T> ReadJsonAsync<T>(
        ManagedArtifact artifact,
        System.Text.Json.Serialization.Metadata.JsonTypeInfo<T> typeInfo,
        CancellationToken cancellationToken)
    {
        var text = await _artifactReader.ReadTextAsync(
            artifact,
            InlineJsonLimit,
            cancellationToken);
        return JsonSerializer.Deserialize(text, typeInfo)
            ?? throw new JsonException($"Artifact {artifact.ArtifactId} was empty.");
    }

    private static ArtifactDescriptor[] ArtifactDescriptors(RunResultEnvelope result)
    {
        var descriptors = new List<ArtifactDescriptor>();
        descriptors.AddRange(result.EvidenceResultRefs.Select((item, index) =>
            new ArtifactDescriptor($"evidence-result-{index + 1:0000}", item)));
        descriptors.AddRange(result.EvidenceTraceRefs.Select((item, index) =>
            new ArtifactDescriptor($"evidence-trace-{index + 1:0000}", item)));
        descriptors.Add(new ArtifactDescriptor("observation-set", result.ObservationSetRef));
        descriptors.Add(new ArtifactDescriptor("posterior", result.PosteriorRef));
        descriptors.Add(new ArtifactDescriptor("inference-trace", result.InferenceTraceRef));
        descriptors.AddRange(result.ReportingRefs.Select((item, index) =>
            new ArtifactDescriptor($"reporting-{index + 1:0000}", item)));
        descriptors.AddRange(result.CoverageRefs.Select((item, index) =>
            new ArtifactDescriptor($"coverage-{index + 1:0000}", item)));
        return descriptors.ToArray();
    }

    private ResultRunItemViewModel BuildRunItem(AssessmentRunV3 run, string resultId)
    {
        var schemeName = ModelDisplayNameResolver.ForScheme(run.Snapshot.Scheme);
        return new ResultRunItemViewModel(
            run,
            resultId,
            schemeName,
            F(
                "Results_RunDetail",
                "{0:g} · {1} active nodes",
                run.FinishedAt?.ToLocalTime(),
                run.Snapshot.ActiveNodes.Length));
    }

    private void ClearResult()
    {
        EvidenceRows.Clear();
        ObservationRows.Clear();
        PosteriorRows.Clear();
        InfluenceRows.Clear();
        Artifacts.Clear();
        ProvenanceRows.Clear();
        ResultSummaryText = L("Results_NoResultLoaded", "No result loaded.");
        ScientificStatusText = L("Results_ScientificUnknown", "Scientific status is not available.");
        CoverageText = string.Empty;
        HasLoadedResult = false;
    }

    private void RefreshStaticPresentation()
    {
        InfluenceExplanationText = L(
            "Results_InfluenceExplanation",
            "Inference influence is a read-only explanation from this result. It is not a canonical BN edge and cannot be edited into the model graph.");
        if (!HasLoadedResult)
        {
            ClearResult();
        }
        if (string.IsNullOrWhiteSpace(StatusMessage))
        {
            StatusMessage = L("Results_StatusStart", "Completed current-model runs will appear here.");
        }
    }

    private void OnLanguageChanged(object? sender, EventArgs args) => InvokeOnUi(() =>
    {
        var selectedId = SelectedRun?.ResultId;
        var existing = Runs.Select(item => new CurrentModelRunListItem(item.Run, item.ResultId)).ToArray();
        Runs.Clear();
        foreach (var item in existing)
        {
            Runs.Add(BuildRunItem(item.Run, item.ResultId!));
        }
        SelectedRun = Runs.FirstOrDefault(item => item.ResultId == selectedId);
        RefreshStaticPresentation();
        if (SelectedRun is not null && HasLoadedResult)
        {
            _ = LoadSelectedCommand.ExecuteAsync(null);
        }
    });

    private void OnShellStateChanged(object? sender, EventArgs args)
    {
        var ready = _shellState?.Snapshot.CanUseDomainCommands ?? true;
        var becameReady = ready && !_wasDomainReady;
        _wasDomainReady = ready;
        if (becameReady && Volatile.Read(ref _initialized) != 0)
        {
            InvokeOnUi(() => _ = RefreshAsync());
        }
    }

    private async Task RunBusyAsync(Func<Task> operation)
    {
        if (IsBusy)
        {
            return;
        }

        IsBusy = true;
        ClearError();
        try
        {
            await operation();
        }
        catch (OperationCanceledException)
        {
            StatusMessage = L("Common_Cancelled", "Cancelled");
        }
        catch (Exception error)
        {
            SetError(error);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void SetError(Exception error)
    {
        System.Diagnostics.Debug.WriteLine(error);
        HasError = true;
        ErrorMessage = L(
            "Results_StatusLoadFailed",
            "Result data could not be loaded. Open Diagnostics for technical details.");
        StatusMessage = ErrorMessage;
    }

    private void ClearError()
    {
        HasError = false;
        ErrorMessage = string.Empty;
    }

    private void NotifyCommandStates()
    {
        RefreshCommand.NotifyCanExecuteChanged();
        LoadSelectedCommand.NotifyCanExecuteChanged();
        OnPropertyChanged(nameof(CanRefresh));
        OnPropertyChanged(nameof(CanLoad));
    }

    private string LocalizeScientificStatus(RunScientificStatus status) => status switch
    {
        RunScientificStatus.NotSupported => L("Results_ScientificNotSupported", "Scientific status: not supported / engineering workflow only."),
        RunScientificStatus.EngineeringDefault => L("Results_ScientificEngineering", "Scientific status: engineering default."),
        RunScientificStatus.ExpertReviewed => L("Results_ScientificExpertReviewed", "Scientific status: expert reviewed."),
        RunScientificStatus.Calibrated => L("Results_ScientificCalibrated", "Scientific status: calibrated."),
        RunScientificStatus.InternallyValidated => L("Results_ScientificInternal", "Scientific status: internally validated."),
        _ => L("Results_ScientificExternal", "Scientific status: externally validated."),
    };

    private void InvokeOnUi(Action action)
    {
        if (_uiContext is null || ReferenceEquals(SynchronizationContext.Current, _uiContext))
        {
            action();
            return;
        }

        _uiContext.Post(static state => ((Action)state!).Invoke(), action);
    }

    private string L(string key, string fallback)
    {
        if (_localization is null)
        {
            return fallback;
        }

        var value = _localization[key];
        return value.StartsWith("⟦", StringComparison.Ordinal) ? fallback : value;
    }

    private string F(string key, string fallback, params object?[] args) =>
        string.Format(L(key, fallback), args);

    private static string ComponentKey(ComponentIdRef component) =>
        $"{component.Kind}:{component.VersionId}";

    private static string ResolveNodeId(
        ComponentIdRef component,
        IReadOnlyDictionary<string, string> componentNodeIds) =>
        componentNodeIds.TryGetValue(ComponentKey(component), out var nodeId)
            ? nodeId
            : component.VersionId;

    private static string ResolveName(
        string nodeId,
        IReadOnlyDictionary<string, string> nodeNames) =>
        nodeNames.TryGetValue(nodeId, out var name)
            ? name
            : ModelDisplayNameResolver.HumanizeIdentifier(nodeId, "Model Result");

    private sealed record ArtifactDescriptor(string Role, ArtifactIdRef Reference);

    private sealed record LoadedArtifact(
        string Role,
        ArtifactIdRef Reference,
        ManagedArtifact Artifact);
}
