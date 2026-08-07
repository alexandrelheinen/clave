namespace Clave.Host;

/// <summary>
/// Behavior when a bounded <see cref="TelemetryChannel{T}"/> is full.
/// Maps to <see cref="System.Threading.Channels.BoundedChannelFullMode"/>.
/// </summary>
public enum TelemetryFullMode
{
    /// <summary>Block writers until capacity is available.</summary>
    Wait = 0,

    /// <summary>Drop the oldest buffered item to make room for the new write.</summary>
    DropOldest = 1,

    /// <summary>Drop the item being written when the channel is full.</summary>
    DropWrite = 2,
}
