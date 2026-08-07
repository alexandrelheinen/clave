using System.Threading.Channels;

namespace Clave.Host;

/// <summary>
/// Bounded telemetry channel wrapper over <see cref="Channel{T}"/>.
/// Phase 0 stub — GC profiling and drop policies come in Phase 1.
/// </summary>
public sealed class TelemetryChannel<T>
{
    private readonly Channel<T> _channel;

    public TelemetryChannel(int capacity)
    {
        if (capacity <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(capacity), capacity, "Capacity must be greater than zero.");
        }

        Capacity = capacity;
        _channel = Channel.CreateBounded<T>(new BoundedChannelOptions(capacity)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = false,
            SingleWriter = false,
        });
    }

    public int Capacity { get; }

    public ValueTask WriteAsync(T item, CancellationToken cancellationToken = default) =>
        _channel.Writer.WriteAsync(item, cancellationToken);

    public ValueTask<T> ReadAsync(CancellationToken cancellationToken = default) =>
        _channel.Reader.ReadAsync(cancellationToken);

    public bool TryWrite(T item) => _channel.Writer.TryWrite(item);

    public bool TryRead(out T item) => _channel.Reader.TryRead(out item!);

    public void Complete(Exception? error = null) => _channel.Writer.TryComplete(error);
}
