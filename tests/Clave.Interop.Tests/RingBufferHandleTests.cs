using Clave.Interop;
using Xunit;

namespace Clave.Interop.Tests;

public class RingBufferHandleTests
{
    [Fact]
    public void Constructor_StoresCapacity()
    {
        using var handle = new RingBufferHandle(8);
        Assert.Equal(8, handle.Capacity);
        Assert.False(handle.IsDisposed);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void Constructor_RejectsNonPositiveCapacity(int capacity)
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => new RingBufferHandle(capacity));
    }

    [Fact]
    public void Dispose_MarksDisposed_AndThrowIfDisposedRaises()
    {
        var handle = new RingBufferHandle(4);
        handle.Dispose();
        Assert.True(handle.IsDisposed);
        Assert.Throws<ObjectDisposedException>(() => handle.ThrowIfDisposed());
    }
}
