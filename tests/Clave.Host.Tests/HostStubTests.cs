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
}
