namespace Clave.Host;

/// <summary>
/// Zero-copy view over a frame payload. A <c>readonly ref struct</c> over
/// <see cref="ReadOnlySpan{T}"/> — no heap allocation for the wrapper itself.
/// Do not capture in async state machines; keep usage in synchronous helpers.
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

    public FrameBuffer Slice(int start) => new(_data[start..]);

    public FrameBuffer Slice(int start, int length) => new(_data.Slice(start, length));

    public void CopyTo(Span<byte> destination) => _data.CopyTo(destination);

    public bool TryCopyTo(Span<byte> destination) => _data.TryCopyTo(destination);
}
