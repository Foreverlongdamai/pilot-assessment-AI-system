using System.Text.Json;
using PilotAssessment.Desktop.Core.Protocol;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneGateway(JsonRpcClient client)
{
    public async Task<SceneRegistry> GetSceneListAsync(CancellationToken cancellationToken = default)
    {
        var result = await client.InvokeAsync("scene.list", cancellationToken: cancellationToken).ConfigureAwait(false);
        return result.Deserialize(SceneJsonContext.Default.SceneRegistry)
            ?? throw new JsonException("场景列表为空。");
    }

    public async Task<SceneCatalog> GetCatalogAsync(CancellationToken cancellationToken = default)
    {
        var result = await client.InvokeAsync("scene.catalog", cancellationToken: cancellationToken).ConfigureAwait(false);
        return result.Deserialize(SceneJsonContext.Default.SceneCatalog)
            ?? throw new JsonException("场景目录为空。");
    }

    public async Task<SceneCatalog> GetCatalogAsync(string sceneId, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sceneId);
        var parameters = JsonSerializer.SerializeToElement(new SceneCatalogRequest(sceneId), SceneJsonContext.Default.SceneCatalogRequest);
        var result = await client.InvokeAsync("scene.catalog", parameters, cancellationToken).ConfigureAwait(false);
        return result.Deserialize(SceneJsonContext.Default.SceneCatalog)
            ?? throw new JsonException("场景目录为空。");
    }

    public async Task<SceneCatalog> GetCatalogAsync(
        string sceneId, string schemaVersion, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sceneId);
        ArgumentException.ThrowIfNullOrWhiteSpace(schemaVersion);
        var parameters = JsonSerializer.SerializeToElement(
            new SceneCatalogRequest(sceneId, schemaVersion), SceneJsonContext.Default.SceneCatalogRequest);
        var result = await client.InvokeAsync("scene.catalog", parameters, cancellationToken).ConfigureAwait(false);
        return result.Deserialize(SceneJsonContext.Default.SceneCatalog)
            ?? throw new JsonException("场景目录为空。");
    }

    public async Task<SceneValidationResult> ValidateConfigurationAsync(
        SceneConfiguration configuration, CancellationToken cancellationToken = default)
    {
        var parameters = JsonSerializer.SerializeToElement(new SceneValidationRequest(configuration), SceneJsonContext.Default.SceneValidationRequest);
        var result = await client.InvokeAsync("scene.validate_configuration", parameters, cancellationToken).ConfigureAwait(false);
        return result.Deserialize(SceneJsonContext.Default.SceneValidationResult)
            ?? throw new JsonException("配置校验结果为空。");
    }

    public async Task<SceneReport> EvaluateAsync(
        SceneConfiguration configuration, SceneInput input, CancellationToken cancellationToken = default)
    {
        var parameters = JsonSerializer.SerializeToElement(new SceneEvaluationRequest(configuration, input), SceneJsonContext.Default.SceneEvaluationRequest);
        var result = await client.InvokeAsync("scene.evaluate", parameters, cancellationToken).ConfigureAwait(false);
        return result.Deserialize(SceneJsonContext.Default.SceneReport)
            ?? throw new JsonException("场景计算报告为空。");
    }
}
