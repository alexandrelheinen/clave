using System.Threading.Channels;

namespace Clave.Host;

/// <summary>
/// Bounded telemetry channel over <see cref="Channel{T}"/> with explicit full-mode
/// policy and ValueTask-based hot-path APIs.
/// </summary>
public sealed class TelemetryChannel<T>
{
    private readonly Channel<T> _channel;
    private long _droppedCount;

    public TelemetryChannel(int capacity)
        : this(new TelemetryChannelOptions(capacity))
    {
    }

    public TelemetryChannel(TelemetryChannelOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);

        Capacity = options.Capacity;
        FullMode = options.FullMode;
        _channel = Channel.CreateBounded<T>(new BoundedChannelOptions(options.Capacity)
        {
            FullMode = ToBoundedFullMode(options.FullMode),
            SingleReader = options.SingleReader,
            SingleWriter = options.SingleWriter,
        });
    }

    public int Capacity { get; }

    public TelemetryFullMode FullMode { get; }

    /// <summary>
    /// Approximate number of items currently buffered (may race under concurrency).
    /// </summary>
    public int Count => _channel.Reader.Count;

    /// <summary>
    /// Items dropped by <see cref="TelemetryFullMode.DropWrite"/> when the channel was full.
    /// <see cref="TelemetryFullMode.DropOldest"/> drops are handled inside the channel and
    /// are not counted here.
    /// </summary>
    public long DroppedCount => Interlocked.Read(ref _droppedCount);

    public ValueTask WriteAsync(T item, CancellationToken cancellationToken = default) =>
        _channel.Writer.WriteAsync(item, cancellationToken);

    public ValueTask<T> ReadAsync(CancellationToken cancellationToken = default) =>
        _channel.Reader.ReadAsync(cancellationToken);

    public ValueTask<bool> WaitToWriteAsync(CancellationToken cancellationToken = default) =>
        _channel.Writer.WaitToWriteAsync(cancellationToken);

    public ValueTask<bool> WaitToReadAsync(CancellationToken cancellationToken = default) =>
        _channel.Reader.WaitToReadAsync(cancellationToken);

    /// <summary>
    /// Attempts a non-blocking write. Under <see cref="TelemetryFullMode.DropWrite"/>,
    /// returns false and increments <see cref="DroppedCount"/> when the channel was full
    /// (the underlying channel accepts the call but discards the item).
    /// </summary>
    public bool TryWrite(T item)
    {
        if (FullMode == TelemetryFullMode.DropWrite)
        {
            int before = _channel.Reader.Count;
            if (!_channel.Writer.TryWrite(item))
            {
                return false;
            }

            // DropWrite keeps Count unchanged when the new item is discarded.
            if (before >= Capacity && _channel.Reader.Count == before)
            {
                Interlocked.Increment(ref _droppedCount);
                return false;
            }

            return true;
        }

        return _channel.Writer.TryWrite(item);
    }

    public bool TryRead(out T item) => _channel.Reader.TryRead(out item!);

    public void Complete(Exception? error = null) => _channel.Writer.TryComplete(error);

    private static BoundedChannelFullMode ToBoundedFullMode(TelemetryFullMode mode) => mode switch
    {
        TelemetryFullMode.Wait => BoundedChannelFullMode.Wait,
        TelemetryFullMode.DropOldest => BoundedChannelFullMode.DropOldest,
        TelemetryFullMode.DropWrite => BoundedChannelFullMode.DropWrite,
        _ => throw new ArgumentOutOfRangeException(nameof(mode), mode, "Unsupported telemetry full mode."),
    };
}
