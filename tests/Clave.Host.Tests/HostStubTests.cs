using Clave.Host;
using Xunit;

namespace Clave.Host.Tests;

public class TelemetryChannelTests
{
    [Fact]
    public async Task WriteThenRead_RoundTripsValue()
    {
        var channel = new TelemetryChannel<int>(capacity: 4);
        await channel.WriteAsync(42);
        int value = await channel.ReadAsync();
        Assert.Equal(42, value);
    }

    [Fact]
    public void Constructor_RejectsNonPositiveCapacity()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => new TelemetryChannel<string>(0));
        Assert.Throws<ArgumentOutOfRangeException>(() => new TelemetryChannelOptions(0));
    }

    [Fact]
    public void Options_Null_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new TelemetryChannel<int>(null!));
    }

    [Fact]
    public void WaitMode_WhenFull_TryWriteReturnsFalse()
    {
        var channel = new TelemetryChannel<int>(new TelemetryChannelOptions(2, TelemetryFullMode.Wait));
        Assert.True(channel.TryWrite(1));
        Assert.True(channel.TryWrite(2));
        Assert.False(channel.TryWrite(3));
        Assert.Equal(2, channel.Count);
        Assert.Equal(0, channel.DroppedCount);
    }

    [Fact]
    public async Task WaitMode_WriteAsync_BlocksUntilSpaceAvailable()
    {
        var channel = new TelemetryChannel<int>(new TelemetryChannelOptions(1, TelemetryFullMode.Wait));
        Assert.True(channel.TryWrite(1));

        using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(50));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await channel.WriteAsync(2, cts.Token));

        Assert.True(channel.TryRead(out int first));
        Assert.Equal(1, first);

        await channel.WriteAsync(2);
        Assert.Equal(2, await channel.ReadAsync());
    }

    [Fact]
    public void DropOldest_WhenFull_EvictsOldestItem()
    {
        var channel = new TelemetryChannel<int>(new TelemetryChannelOptions(2, TelemetryFullMode.DropOldest));
        Assert.True(channel.TryWrite(10));
        Assert.True(channel.TryWrite(20));
        Assert.True(channel.TryWrite(30)); // drops 10

        Assert.True(channel.TryRead(out int a));
        Assert.True(channel.TryRead(out int b));
        Assert.False(channel.TryRead(out _));
        Assert.Equal(20, a);
        Assert.Equal(30, b);
    }

    [Fact]
    public void DropWrite_WhenFull_IncrementsDroppedCount()
    {
        var channel = new TelemetryChannel<int>(new TelemetryChannelOptions(1, TelemetryFullMode.DropWrite));
        Assert.True(channel.TryWrite(1));
        Assert.False(channel.TryWrite(2));
        Assert.False(channel.TryWrite(3));
        Assert.Equal(2, channel.DroppedCount);

        Assert.True(channel.TryRead(out int kept));
        Assert.Equal(1, kept);
    }

    [Fact]
    public async Task WaitToWriteAsync_ReturnsFalseAfterComplete()
    {
        var channel = new TelemetryChannel<int>(capacity: 2);
        channel.Complete();
        Assert.False(await channel.WaitToWriteAsync());
    }

    [Fact]
    public async Task WaitToReadAsync_CompletesWhenItemAvailable()
    {
        var channel = new TelemetryChannel<int>(capacity: 2);
        ValueTask<bool> wait = channel.WaitToReadAsync();
        Assert.False(wait.IsCompleted);

        Assert.True(channel.TryWrite(7));
        Assert.True(await wait);
        Assert.Equal(7, await channel.ReadAsync());
    }
}

public class FrameBufferTests
{
    [Fact]
    public void Length_MatchesUnderlyingSpan()
    {
        byte[] data = [10, 20, 30];
        var buffer = new FrameBuffer(data);
        Assert.Equal(3, buffer.Length);
        Assert.False(buffer.IsEmpty);
        Assert.Equal(20, buffer[1]);
    }

    [Fact]
    public void EmptySpan_IsEmpty()
    {
        var buffer = new FrameBuffer(ReadOnlySpan<byte>.Empty);
        Assert.Equal(0, buffer.Length);
        Assert.True(buffer.IsEmpty);
    }

    [Fact]
    public void Slice_ReturnsSubViewWithoutCopy()
    {
        byte[] data = [1, 2, 3, 4, 5];
        var buffer = new FrameBuffer(data);
        FrameBuffer slice = buffer.Slice(1, 3);
        Assert.Equal(3, slice.Length);
        Assert.Equal(2, slice[0]);
        Assert.Equal(4, slice[2]);
    }

    [Fact]
    public void CopyTo_WritesIntoDestination()
    {
        byte[] data = [9, 8, 7];
        var buffer = new FrameBuffer(data);
        Span<byte> dest = stackalloc byte[3];
        buffer.CopyTo(dest);
        Assert.Equal(9, dest[0]);
        Assert.Equal(7, dest[2]);
    }

    [Fact]
    public void TryCopyTo_ReturnsFalseWhenDestinationTooSmall()
    {
        byte[] data = [1, 2, 3];
        var buffer = new FrameBuffer(data);
        Span<byte> dest = stackalloc byte[1];
        Assert.False(buffer.TryCopyTo(dest));
    }
}
