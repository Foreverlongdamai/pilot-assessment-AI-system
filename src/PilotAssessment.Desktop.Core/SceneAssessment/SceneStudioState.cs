namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>Owns independently editable scene documents for the global studio.</summary>
public sealed class SceneStudioState
{
    private readonly List<SceneDocument> _documents = [];
    private readonly Dictionary<string, SceneDocument> _documentsById = new(StringComparer.Ordinal);

    public SceneStudioState() => Documents = _documents.AsReadOnly();

    public IReadOnlyList<SceneDocument> Documents { get; }

    public SceneDocument AddCatalog(SceneCatalog catalog)
    {
        ArgumentNullException.ThrowIfNull(catalog);
        ArgumentException.ThrowIfNullOrWhiteSpace(catalog.SceneId);
        if (_documentsById.ContainsKey(catalog.SceneId))
        {
            throw new ArgumentException($"场景 {catalog.SceneId} 已加载，不能覆盖现有编辑。", nameof(catalog));
        }

        var document = new SceneDocument(catalog);
        _documentsById.Add(catalog.SceneId, document);
        _documents.Add(document);
        return document;
    }

    public SceneDocument GetDocument(string sceneId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sceneId);
        return _documentsById.TryGetValue(sceneId, out var document)
            ? document
            : throw new KeyNotFoundException($"尚未加载场景 {sceneId}。");
    }
}
