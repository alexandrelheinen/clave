namespace Clave.Interop;

/// <summary>
/// Managed handle for a ring buffer capacity contract.
/// Phase 0: validation only. Phase 5: P/Invoke into Rust <c>clave-core</c> C ABI.
/// </summary>
public sealed class RingBufferHandle : IDisposable
{
    private bool _disposed;

    public RingBufferHandle(int capacity)
    {
        if (capacity <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(capacity), capacity, "Capacity must be greater than zero.");
        }

        Capacity = capacity;
    }

    public int Capacity { get; }

    public bool IsDisposed => _disposed;

    public void Dispose()
    {
        _disposed = true;
    }

    public void ThrowIfDisposed()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
    }
}
