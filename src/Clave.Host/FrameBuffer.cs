namespace Clave.Host;

/// <summary>
/// Zero-copy view over a frame payload. Phase 0 stub using a <c>readonly ref struct</c>
/// over <see cref="ReadOnlySpan{T}"/> — no heap allocation for the wrapper itself.
/// </summary>
public readonly ref struct FrameBuffer
{
    private readonly ReadOnlySpan<byte> _data;

    public FrameBuffer(ReadOnlySpan<byte> data)
    {
        _data = data;
    }

    public int Length => _data.Length;

    public ReadOnlySpan<byte> Span => _data;

    public byte this[int index] => _data[index];

    public bool IsEmpty => _data.IsEmpty;
}
