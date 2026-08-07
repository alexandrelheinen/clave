using Clave.Bus;
using Clave.Capture;
using Clave.Host;
using Clave.Interop;
using Clave.Vision;

namespace Clave.Cli;

internal static class Program
{
    private static async Task<int> Main(string[] args)
    {
        _ = args;

        Console.WriteLine("CLAVE — Cross-Language Architecture for Vision & Edge");
        Console.WriteLine("Phase 0 scaffold smoke (stubs only; no native SDKs).");
        Console.WriteLine();

        var channel = new TelemetryChannel<string>(capacity: 8);
        await channel.WriteAsync("hello-clave");
        var roundTrip = await channel.ReadAsync();
        Console.WriteLine($"TelemetryChannel round-trip: {roundTrip}");

        byte[] frameBytes = [1, 2, 3, 4, 5, 6, 7, 8];
        PrintFrameBuffer(frameBytes);

        var observation = VisionPipelineStub.ProcessSynthetic(frameBytes);
        Console.WriteLine($"Vision observation: {observation.Label} @ {observation.Confidence:F2}");

        float[] cloud = PointCloudStub.GenerateSynthetic(4);
        Console.WriteLine($"Point cloud points: {PointCloudStub.PointCount(cloud)}");

        using var ring = new RingBufferHandle(capacity: 16);
        Console.WriteLine($"RingBufferHandle capacity: {ring.Capacity}");

        var bus = new EthercatMasterStub();
        bus.Configure(slaveCount: 2);
        bus.Start();
        Console.WriteLine(bus.StatusSummary());
        bus.Stop();

        Console.WriteLine();
        Console.WriteLine("Smoke OK.");
        return 0;
    }

    // FrameBuffer is a ref struct — keep usage out of async methods on net8.0.
    private static void PrintFrameBuffer(byte[] frameBytes)
    {
        var frame = new FrameBuffer(frameBytes);
        Console.WriteLine($"FrameBuffer length: {frame.Length}");
    }
}
