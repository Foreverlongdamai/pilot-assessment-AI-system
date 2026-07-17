using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;

using PilotAssessment.Desktop.Core.Protocol;

namespace PilotAssessment.Desktop.UnitTests.Protocol;

public sealed class JsonLineFramerTests
{
    [Fact]
    public async Task ReadMessagesAsync_HandlesSplitAndCoalescedPhysicalReads()
    {
        var input = new ChunkedReadStream(
            "{\"jsonrpc\":\"2.0\",\"id\":\"one\",",
            "\"result\":{}}\n{\"jsonrpc\":\"2.0\",",
            "\"method\":\"run.progress\",\"params\":{}}\r\n");
        var framer = new JsonLineFramer(input, Stream.Null);

        var messages = new List<JsonElement>();
        await foreach (var message in framer.ReadMessagesAsync())
        {
            messages.Add(message);
        }

        Assert.Equal(2, messages.Count);
        Assert.Equal("one", messages[0].GetProperty("id").GetString());
        Assert.Equal("run.progress", messages[1].GetProperty("method").GetString());
    }

    [Fact]
    public async Task WriteAsync_EmitsOneCompactUtf8Line()
    {
        await using var output = new MemoryStream();
        var framer = new JsonLineFramer(Stream.Null, output);
        var message = ParseElement("""
            {
              "jsonrpc": "2.0",
              "method": "notice",
              "params": { "text": "飞行员" }
            }
            """);

        await framer.WriteAsync(message);

        var framed = Encoding.UTF8.GetString(output.ToArray());
        Assert.EndsWith("\n", framed, StringComparison.Ordinal);
        Assert.DoesNotContain("\r", framed, StringComparison.Ordinal);
        Assert.DoesNotContain("\n", framed[..^1], StringComparison.Ordinal);
        using var parsed = JsonDocument.Parse(framed);
        Assert.Equal("飞行员", parsed.RootElement.GetProperty("params").GetProperty("text").GetString());
    }

    [Fact]
    public async Task ReadMessagesAsync_RejectsOversizeFrameWithoutLargeFixture()
    {
        var bytes = Encoding.UTF8.GetBytes("{\"value\":\"1234567890123456789012345678901234567890\"}\n");
        var framer = new JsonLineFramer(new MemoryStream(bytes), Stream.Null, maxMessageBytes: 24);

        await Assert.ThrowsAsync<JsonLineProtocolException>(async () =>
        {
            await foreach (var _ in framer.ReadMessagesAsync())
            {
            }
        });
    }

    [Theory]
    [InlineData("{not-json}\n")]
    [InlineData("[]\n")]
    [InlineData("{\"id\":1,\"id\":2}\n")]
    public async Task ReadMessagesAsync_RejectsMalformedNonObjectAndDuplicateMembers(string payload)
    {
        var framer = new JsonLineFramer(
            new MemoryStream(Encoding.UTF8.GetBytes(payload)),
            Stream.Null);

        await Assert.ThrowsAsync<JsonLineProtocolException>(async () =>
        {
            await foreach (var _ in framer.ReadMessagesAsync())
            {
            }
        });
    }

    private static JsonElement ParseElement(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    private sealed class ChunkedReadStream(params string[] chunks) : Stream
    {
        private readonly Queue<byte[]> _chunks = new(
            chunks.Select(value => Encoding.UTF8.GetBytes(value)));
        private byte[]? _current;
        private int _offset;

        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position
        {
            get => throw new NotSupportedException();
            set => throw new NotSupportedException();
        }

        public override int Read(byte[] buffer, int offset, int count) =>
            ReadAsync(buffer.AsMemory(offset, count)).AsTask().GetAwaiter().GetResult();

        public override ValueTask<int> ReadAsync(
            Memory<byte> buffer,
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (_current is null || _offset == _current.Length)
            {
                if (!_chunks.TryDequeue(out _current))
                {
                    return ValueTask.FromResult(0);
                }

                _offset = 0;
            }

            var count = Math.Min(buffer.Length, _current.Length - _offset);
            _current.AsMemory(_offset, count).CopyTo(buffer);
            _offset += count;
            return ValueTask.FromResult(count);
        }

        public override void Flush()
        {
        }

        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }
}
