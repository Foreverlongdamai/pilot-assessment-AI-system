using System.Buffers;
using System.Collections.Concurrent;
using System.Text.Json;

namespace PilotAssessment.Desktop.Core.Protocol;

public sealed record JsonRpcNotificationMessage(string Method, JsonElement? Params);

public sealed class JsonRpcRemoteException : Exception
{
    public JsonRpcRemoteException(int code, string message, JsonElement? data)
        : base(message)
    {
        Code = code;
        DataElement = data;
    }

    public int Code { get; }
    public JsonElement? DataElement { get; }
}

public sealed class JsonRpcResponseNotReceivedException : IOException
{
    public JsonRpcResponseNotReceivedException(string requestId, string message)
        : base(message)
    {
        RequestId = requestId;
    }

    public JsonRpcResponseNotReceivedException(
        string requestId,
        string message,
        Exception innerException)
        : base(message, innerException)
    {
        RequestId = requestId;
    }

    public string RequestId { get; }
}

public sealed class JsonRpcClient : IAsyncDisposable
{
    private readonly JsonLineFramer _framer;
    private readonly CancellationTokenSource _lifetime = new();
    private readonly ConcurrentDictionary<string, PendingRequest> _pending = new(StringComparer.Ordinal);
    private readonly ConcurrentDictionary<string, byte> _cancelledRequestIds = new(StringComparer.Ordinal);
    private readonly TaskCompletionSource _completion = new(
        TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly Task _readerTask;
    private long _requestSequence;
    private int _acceptingRequests = 1;
    private int _disposed;

    public JsonRpcClient(JsonLineFramer framer)
    {
        ArgumentNullException.ThrowIfNull(framer);
        _framer = framer;
        _readerTask = ReadLoopAsync();
    }

    public event EventHandler<JsonRpcNotificationMessage>? NotificationReceived;

    public Task Completion => _completion.Task;

    public async Task<JsonElement> InvokeAsync(
        string method,
        JsonElement? parameters = null,
        CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        ArgumentException.ThrowIfNullOrWhiteSpace(method);
        cancellationToken.ThrowIfCancellationRequested();
        if (Volatile.Read(ref _acceptingRequests) == 0)
        {
            throw new InvalidOperationException("The JSON-RPC connection is closed.");
        }

        if (parameters is { ValueKind: not JsonValueKind.Object })
        {
            throw new ArgumentException("JSON-RPC params must be an object.", nameof(parameters));
        }

        var requestId = $"request-{Interlocked.Increment(ref _requestSequence)}";
        var pending = new PendingRequest();
        if (!_pending.TryAdd(requestId, pending))
        {
            throw new InvalidOperationException($"Duplicate request ID {requestId}.");
        }

        using var registration = cancellationToken.UnsafeRegister(
            static (state, token) =>
            {
                var registrationState = (CancellationState)state!;
                registrationState.Client.CancelPending(registrationState.RequestId, token);
            },
            new CancellationState(this, requestId));

        try
        {
            await _framer.WriteAsync(
                BuildRequest(requestId, method, parameters),
                cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            CancelPending(requestId, cancellationToken);
            throw;
        }
        catch (Exception error) when (error is IOException or ObjectDisposedException)
        {
            if (_pending.TryRemove(requestId, out var removed))
            {
                removed.Completion.TrySetException(
                    new JsonRpcResponseNotReceivedException(
                        requestId,
                        $"The response for {method} was not received.",
                        error));
            }
        }

        return await pending.Completion.Task.ConfigureAwait(false);
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
        }

        Interlocked.Exchange(ref _acceptingRequests, 0);
        _lifetime.Cancel();
        FailPending(new ObjectDisposedException(nameof(JsonRpcClient)));
        try
        {
            await _readerTask.ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch
        {
            // Completion preserves the protocol fault for observers.
        }

        await _framer.DisposeAsync().ConfigureAwait(false);
        _lifetime.Dispose();
    }

    private async Task ReadLoopAsync()
    {
        try
        {
            await foreach (var message in _framer.ReadMessagesAsync(_lifetime.Token).ConfigureAwait(false))
            {
                HandleMessage(message);
            }

            Interlocked.Exchange(ref _acceptingRequests, 0);
            FailPendingForMissingResponses("The sidecar stdout stream closed before a response arrived.");
            _completion.TrySetResult();
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            _completion.TrySetResult();
        }
        catch (Exception error)
        {
            Interlocked.Exchange(ref _acceptingRequests, 0);
            FailPending(error);
            _completion.TrySetException(error);
        }
    }

    private void HandleMessage(JsonElement message)
    {
        if (!message.TryGetProperty("jsonrpc", out var version) ||
            version.ValueKind is not JsonValueKind.String ||
            version.GetString() != "2.0")
        {
            throw new JsonLineProtocolException("Inbound message does not declare JSON-RPC 2.0.");
        }

        if (message.TryGetProperty("id", out var idElement))
        {
            HandleResponse(message, idElement);
            return;
        }

        HandleNotification(message);
    }

    private void HandleResponse(JsonElement message, JsonElement idElement)
    {
        if (idElement.ValueKind is not JsonValueKind.String ||
            string.IsNullOrWhiteSpace(idElement.GetString()))
        {
            throw new JsonLineProtocolException("Response ID must match a non-empty client string ID.");
        }

        var requestId = idElement.GetString()!;
        if (_cancelledRequestIds.TryRemove(requestId, out _))
        {
            return;
        }

        if (!_pending.TryGetValue(requestId, out var pending))
        {
            throw new JsonLineProtocolException($"Response ID '{requestId}' is not pending.");
        }

        var hasResult = message.TryGetProperty("result", out var result);
        var hasError = message.TryGetProperty("error", out var error);
        if (hasResult == hasError)
        {
            throw new JsonLineProtocolException(
                "A JSON-RPC response must contain exactly one of result or error.");
        }

        if (hasResult)
        {
            CompletePending(requestId, pending, result.Clone());
            return;
        }

        if (error.ValueKind is not JsonValueKind.Object ||
            !error.TryGetProperty("code", out var codeElement) ||
            !codeElement.TryGetInt32(out var code) ||
            !error.TryGetProperty("message", out var messageElement) ||
            messageElement.ValueKind is not JsonValueKind.String)
        {
            throw new JsonLineProtocolException("A JSON-RPC error response is malformed.");
        }

        JsonElement? data = error.TryGetProperty("data", out var dataElement)
            ? dataElement.Clone()
            : null;
        CompletePending(
            requestId,
            pending,
            new JsonRpcRemoteException(code, messageElement.GetString()!, data));
    }

    private void HandleNotification(JsonElement message)
    {
        if (!message.TryGetProperty("method", out var methodElement) ||
            methodElement.ValueKind is not JsonValueKind.String ||
            string.IsNullOrWhiteSpace(methodElement.GetString()))
        {
            throw new JsonLineProtocolException(
                "A JSON-RPC notification must contain a non-empty method.");
        }

        JsonElement? parameters = message.TryGetProperty("params", out var paramsElement)
            ? paramsElement.Clone()
            : null;
        var notification = new JsonRpcNotificationMessage(methodElement.GetString()!, parameters);
        var handlers = NotificationReceived;
        if (handlers is null)
        {
            return;
        }

        foreach (EventHandler<JsonRpcNotificationMessage> handler in handlers.GetInvocationList())
        {
            try
            {
                handler(this, notification);
            }
            catch
            {
                // Consumer UI errors are not wire-protocol failures.
            }
        }
    }

    private void CancelPending(string requestId, CancellationToken cancellationToken)
    {
        if (_pending.TryRemove(requestId, out var pending))
        {
            _cancelledRequestIds.TryAdd(requestId, 0);
            pending.Completion.TrySetCanceled(cancellationToken);
        }
    }

    private void CompletePending(
        string requestId,
        PendingRequest expected,
        JsonElement result)
    {
        if (_pending.TryRemove(
            new KeyValuePair<string, PendingRequest>(requestId, expected)))
        {
            expected.Completion.TrySetResult(result);
            return;
        }

        if (!_cancelledRequestIds.TryRemove(requestId, out _))
        {
            throw new JsonLineProtocolException(
                $"Response ID '{requestId}' stopped being pending before completion.");
        }
    }

    private void CompletePending(
        string requestId,
        PendingRequest expected,
        Exception error)
    {
        if (_pending.TryRemove(
            new KeyValuePair<string, PendingRequest>(requestId, expected)))
        {
            expected.Completion.TrySetException(error);
            return;
        }

        if (!_cancelledRequestIds.TryRemove(requestId, out _))
        {
            throw new JsonLineProtocolException(
                $"Response ID '{requestId}' stopped being pending before completion.");
        }
    }

    private void FailPending(Exception error)
    {
        foreach (var entry in _pending.ToArray())
        {
            if (_pending.TryRemove(entry.Key, out var pending))
            {
                pending.Completion.TrySetException(error);
            }
        }
    }

    private void FailPendingForMissingResponses(string message)
    {
        foreach (var entry in _pending.ToArray())
        {
            if (_pending.TryRemove(entry.Key, out var pending))
            {
                pending.Completion.TrySetException(
                    new JsonRpcResponseNotReceivedException(entry.Key, message));
            }
        }
    }

    private static JsonElement BuildRequest(
        string requestId,
        string method,
        JsonElement? parameters)
    {
        var buffer = new ArrayBufferWriter<byte>();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            writer.WriteString("jsonrpc", "2.0");
            writer.WriteString("id", requestId);
            writer.WriteString("method", method);
            writer.WritePropertyName("params");
            if (parameters is null)
            {
                writer.WriteStartObject();
                writer.WriteEndObject();
            }
            else
            {
                parameters.Value.WriteTo(writer);
            }

            writer.WriteEndObject();
        }

        using var document = JsonDocument.Parse(buffer.WrittenMemory);
        return document.RootElement.Clone();
    }

    private sealed class PendingRequest
    {
        public TaskCompletionSource<JsonElement> Completion { get; } = new(
            TaskCreationOptions.RunContinuationsAsynchronously);
    }

    private sealed record CancellationState(JsonRpcClient Client, string RequestId);
}

public static class IdempotentRequestRetry
{
    public static async Task<T> ExecuteAsync<T>(
        string transactionId,
        Func<string, CancellationToken, Task<T>> attempt,
        int maxAttempts = 2,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(transactionId);
        ArgumentNullException.ThrowIfNull(attempt);
        if (maxAttempts < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(maxAttempts));
        }

        for (var index = 1; ; index++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                return await attempt(transactionId, cancellationToken).ConfigureAwait(false);
            }
            catch (JsonRpcResponseNotReceivedException) when (index < maxAttempts)
            {
                // Reuse the caller-owned transaction ID; never mint a replacement here.
            }
        }
    }
}
