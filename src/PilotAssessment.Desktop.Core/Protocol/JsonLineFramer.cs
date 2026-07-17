using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;

namespace PilotAssessment.Desktop.Core.Protocol;

public sealed class JsonLineProtocolException : IOException
{
    public JsonLineProtocolException(string message)
        : base(message)
    {
    }

    public JsonLineProtocolException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

public sealed class JsonLineFramer : IAsyncDisposable
{
    public const int DefaultMaxMessageBytes = 4 * 1024 * 1024;

    private static readonly UTF8Encoding StrictUtf8 = new(
        encoderShouldEmitUTF8Identifier: false,
        throwOnInvalidBytes: true);

    private readonly Stream _input;
    private readonly Stream _output;
    private readonly SemaphoreSlim _writeLock = new(1, 1);
    private int _readerStarted;
    private int _disposed;

    public JsonLineFramer(
        Stream input,
        Stream output,
        int maxMessageBytes = DefaultMaxMessageBytes)
    {
        ArgumentNullException.ThrowIfNull(input);
        ArgumentNullException.ThrowIfNull(output);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(maxMessageBytes);

        _input = input;
        _output = output;
        MaxMessageBytes = maxMessageBytes;
    }

    public int MaxMessageBytes { get; }

    public async IAsyncEnumerable<JsonElement> ReadMessagesAsync(
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        if (Interlocked.Exchange(ref _readerStarted, 1) != 0)
        {
            throw new InvalidOperationException("A JsonLineFramer supports one stdout reader.");
        }

        var readBuffer = new byte[16 * 1024];
        using var frame = new MemoryStream();

        while (true)
        {
            var bytesRead = await _input.ReadAsync(readBuffer, cancellationToken).ConfigureAwait(false);
            if (bytesRead == 0)
            {
                break;
            }

            var consumed = 0;
            while (consumed < bytesRead)
            {
                var remaining = readBuffer.AsSpan(consumed, bytesRead - consumed);
                var newlineOffset = remaining.IndexOf((byte)'\n');
                var segmentLength = newlineOffset >= 0 ? newlineOffset : remaining.Length;
                frame.Write(remaining[..segmentLength]);
                EnsureBufferedFrameWithinBound(frame);
                consumed += segmentLength;

                if (newlineOffset < 0)
                {
                    continue;
                }

                consumed++;
                yield return DecodeFrame(frame);
                frame.SetLength(0);
            }
        }

        if (frame.Length > 0)
        {
            yield return DecodeFrame(frame);
        }
    }

    public async ValueTask WriteAsync(
        JsonElement message,
        CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        if (message.ValueKind is not JsonValueKind.Object)
        {
            throw new JsonLineProtocolException("A JSON-RPC frame must contain one JSON object.");
        }

        ValidateNoDuplicateMembers(message);
        using var payload = new MemoryStream();
        await using (var writer = new Utf8JsonWriter(payload, new JsonWriterOptions { Indented = false }))
        {
            message.WriteTo(writer);
            await writer.FlushAsync(cancellationToken).ConfigureAwait(false);
        }

        if (payload.Length > MaxMessageBytes)
        {
            throw new JsonLineProtocolException(
                $"JSON-RPC frame exceeds the {MaxMessageBytes}-byte limit.");
        }

        await _writeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            payload.Position = 0;
            await payload.CopyToAsync(_output, cancellationToken).ConfigureAwait(false);
            await _output.WriteAsync("\n"u8.ToArray(), cancellationToken).ConfigureAwait(false);
            await _output.FlushAsync(cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _writeLock.Release();
        }
    }

    public ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposed, 1) == 0)
        {
            _writeLock.Dispose();
        }

        return ValueTask.CompletedTask;
    }

    private void EnsureBufferedFrameWithinBound(MemoryStream frame)
    {
        // One extra byte is allowed until the line ending is known because it may be CR.
        if (frame.Length > (long)MaxMessageBytes + 1)
        {
            throw new JsonLineProtocolException(
                $"JSON-RPC frame exceeds the {MaxMessageBytes}-byte limit.");
        }
    }

    private JsonElement DecodeFrame(MemoryStream frame)
    {
        var payload = frame.ToArray().AsSpan();
        if (!payload.IsEmpty && payload[^1] == (byte)'\r')
        {
            payload = payload[..^1];
        }

        if (payload.Length > MaxMessageBytes)
        {
            throw new JsonLineProtocolException(
                $"JSON-RPC frame exceeds the {MaxMessageBytes}-byte limit.");
        }

        try
        {
            var json = StrictUtf8.GetString(payload);
            using var document = JsonDocument.Parse(
                json,
                new JsonDocumentOptions
                {
                    AllowTrailingCommas = false,
                    CommentHandling = JsonCommentHandling.Disallow,
                    MaxDepth = 128,
                });
            if (document.RootElement.ValueKind is not JsonValueKind.Object)
            {
                throw new JsonLineProtocolException(
                    "A JSON-RPC frame must contain one JSON object.");
            }

            ValidateNoDuplicateMembers(document.RootElement);
            return document.RootElement.Clone();
        }
        catch (JsonLineProtocolException)
        {
            throw;
        }
        catch (Exception error) when (error is JsonException or DecoderFallbackException)
        {
            throw new JsonLineProtocolException("The JSON-RPC frame is malformed.", error);
        }
    }

    private static void ValidateNoDuplicateMembers(JsonElement element)
    {
        if (element.ValueKind is JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
            {
                if (!names.Add(property.Name))
                {
                    throw new JsonLineProtocolException(
                        $"JSON object contains duplicate member '{property.Name}'.");
                }

                ValidateNoDuplicateMembers(property.Value);
            }
        }
        else if (element.ValueKind is JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray())
            {
                ValidateNoDuplicateMembers(item);
            }
        }
    }
}
