using System.IO.Pipes;
using System.Text;
using System.Text.Json;

using PilotAssessment.Desktop.Core.Protocol;

namespace PilotAssessment.Desktop.UnitTests.Protocol;

public sealed class JsonRpcClientTests
{
    [Fact]
    public async Task InvokeAsync_MatchesOutOfOrderResponsesAndDispatchesNotification()
    {
        await using var harness = await RpcPipeHarness.CreateAsync();
        var notification = new TaskCompletionSource<JsonRpcNotificationMessage>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        harness.Client.NotificationReceived += (_, message) => notification.TrySetResult(message);

        var first = harness.Client.InvokeAsync("test.first", EmptyObject());
        var second = harness.Client.InvokeAsync("test.second", EmptyObject());
        var firstRequest = await harness.ReadServerMessageAsync();
        var secondRequest = await harness.ReadServerMessageAsync();

        await harness.WriteServerMessageAsync(Notification("run.progress", "{\"sequence\":1}"));
        await harness.WriteServerMessageAsync(Response(secondRequest, "second"));
        await harness.WriteServerMessageAsync(Response(firstRequest, "first"));

        Assert.Equal("first", (await first).GetProperty("value").GetString());
        Assert.Equal("second", (await second).GetProperty("value").GetString());
        Assert.Equal("run.progress", (await notification.Task).Method);
    }

    [Fact]
    public async Task InvokeAsync_CancellationCompletesOnceAndLateResponseIsIgnored()
    {
        await using var harness = await RpcPipeHarness.CreateAsync();
        using var cancellation = new CancellationTokenSource();

        var cancelledCall = harness.Client.InvokeAsync(
            "test.cancel",
            EmptyObject(),
            cancellation.Token);
        var cancelledRequest = await harness.ReadServerMessageAsync();
        cancellation.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => cancelledCall);
        await harness.WriteServerMessageAsync(Response(cancelledRequest, "late"));

        var nextCall = harness.Client.InvokeAsync("test.next", EmptyObject());
        var nextRequest = await harness.ReadServerMessageAsync();
        await harness.WriteServerMessageAsync(Response(nextRequest, "alive"));

        Assert.Equal("alive", (await nextCall).GetProperty("value").GetString());
    }

    [Fact]
    public async Task MalformedInboundJson_FaultsPendingRequestAndClientCompletion()
    {
        await using var harness = await RpcPipeHarness.CreateAsync();
        var pending = harness.Client.InvokeAsync("test.pending", EmptyObject());
        _ = await harness.ReadServerMessageAsync();

        await harness.ServerStream.WriteAsync(Encoding.UTF8.GetBytes("{malformed}\n"));
        await harness.ServerStream.FlushAsync();

        await Assert.ThrowsAsync<JsonLineProtocolException>(() => pending);
        await Assert.ThrowsAsync<JsonLineProtocolException>(() => harness.Client.Completion);
    }

    [Fact]
    public async Task MalformedResponseShape_FaultsItsPendingRequestInsteadOfLeavingItWaiting()
    {
        await using var harness = await RpcPipeHarness.CreateAsync();
        var pending = harness.Client.InvokeAsync("test.pending", EmptyObject());
        var request = await harness.ReadServerMessageAsync();
        var requestId = request.GetProperty("id").GetString();

        await harness.WriteServerMessageAsync(
            ParseElement(
                "{\"jsonrpc\":\"2.0\",\"id\":" + JsonSerializer.Serialize(requestId) + "}"));

        await Assert.ThrowsAsync<JsonLineProtocolException>(() => pending);
        await Assert.ThrowsAsync<JsonLineProtocolException>(() => harness.Client.Completion);
    }

    [Fact]
    public async Task RetryIdempotentAsync_ReusesTransactionIdOnlyForMissingResponse()
    {
        var seenTransactionIds = new List<string>();
        var attempts = 0;

        var value = await IdempotentRequestRetry.ExecuteAsync(
            "tx.same",
            (transactionId, _) =>
            {
                seenTransactionIds.Add(transactionId);
                attempts++;
                return attempts == 1
                    ? Task.FromException<string>(
                        new JsonRpcResponseNotReceivedException("request-1", "response lost"))
                    : Task.FromResult("ok");
            },
            maxAttempts: 2);

        Assert.Equal("ok", value);
        Assert.Equal(["tx.same", "tx.same"], seenTransactionIds);
    }

    private static JsonElement EmptyObject() => ParseElement("{}");

    private static JsonElement Response(JsonElement request, string value)
    {
        var id = request.GetProperty("id").GetString();
        return ParseElement(
            "{\"jsonrpc\":\"2.0\",\"id\":" + JsonSerializer.Serialize(id) +
            ",\"result\":{\"value\":" + JsonSerializer.Serialize(value) + "}}");
    }

    private static JsonElement Notification(string method, string parameters) =>
        ParseElement(
            "{\"jsonrpc\":\"2.0\",\"method\":" + JsonSerializer.Serialize(method) +
            ",\"params\":" + parameters + "}");

    private static JsonElement ParseElement(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    private sealed class RpcPipeHarness : IAsyncDisposable
    {
        private readonly IAsyncEnumerator<JsonElement> _serverMessages;
        private readonly NamedPipeServerStream _serverStream;
        private readonly NamedPipeClientStream _clientStream;

        private RpcPipeHarness(
            NamedPipeServerStream serverStream,
            NamedPipeClientStream clientStream)
        {
            _serverStream = serverStream;
            _clientStream = clientStream;
            ServerFramer = new JsonLineFramer(serverStream, serverStream);
            Client = new JsonRpcClient(new JsonLineFramer(clientStream, clientStream));
            _serverMessages = ServerFramer.ReadMessagesAsync().GetAsyncEnumerator();
        }

        public Stream ServerStream => _serverStream;
        public JsonLineFramer ServerFramer { get; }
        public JsonRpcClient Client { get; }

        public static async Task<RpcPipeHarness> CreateAsync()
        {
            var name = $"pilot-assessment-{Guid.NewGuid():N}";
            var server = new NamedPipeServerStream(
                name,
                PipeDirection.InOut,
                1,
                PipeTransmissionMode.Byte,
                PipeOptions.Asynchronous);
            var client = new NamedPipeClientStream(
                ".",
                name,
                PipeDirection.InOut,
                PipeOptions.Asynchronous);

            await Task.WhenAll(server.WaitForConnectionAsync(), client.ConnectAsync());
            return new RpcPipeHarness(server, client);
        }

        public async Task<JsonElement> ReadServerMessageAsync()
        {
            Assert.True(await _serverMessages.MoveNextAsync());
            return _serverMessages.Current;
        }

        public ValueTask WriteServerMessageAsync(JsonElement message) =>
            ServerFramer.WriteAsync(message);

        public async ValueTask DisposeAsync()
        {
            await Client.DisposeAsync();
            await _serverMessages.DisposeAsync();
            await ServerFramer.DisposeAsync();
            await _clientStream.DisposeAsync();
            await _serverStream.DisposeAsync();
        }
    }
}
