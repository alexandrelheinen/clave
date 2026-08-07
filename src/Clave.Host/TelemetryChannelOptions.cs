namespace Clave.Host;

/// <summary>
/// Configuration for <see cref="TelemetryChannel{T}"/>.
/// </summary>
public sealed class TelemetryChannelOptions
{
    public TelemetryChannelOptions(int capacity, TelemetryFullMode fullMode = TelemetryFullMode.Wait)
    {
        if (capacity <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(capacity), capacity, "Capacity must be greater than zero.");
        }

        Capacity = capacity;
        FullMode = fullMode;
    }

    public int Capacity { get; }

    public TelemetryFullMode FullMode { get; }

    /// <summary>
    /// When true, optimizes for a single consumer. Default false.
    /// </summary>
    public bool SingleReader { get; init; }

    /// <summary>
    /// When true, optimizes for a single producer. Default false.
    /// </summary>
    public bool SingleWriter { get; init; }
}
