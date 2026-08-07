namespace Clave.Vision;

/// <summary>
/// Synthetic observation record compatible in spirit with fret observation contracts.
/// Real ONNX/OpenCVSharp backends are Phase 2.
/// </summary>
public sealed record Observation(
    DateTimeOffset Timestamp,
    string Label,
    float Confidence,
    int FrameWidth,
    int FrameHeight);

/// <summary>
/// Phase 0 vision pipeline stub that emits deterministic synthetic observations.
/// </summary>
public static class VisionPipelineStub
{
    public static Observation ProcessSynthetic(ReadOnlySpan<byte> frame, string label = "synthetic")
    {
        float confidence = frame.IsEmpty ? 0f : Math.Clamp(frame.Length / 1024f, 0f, 1f);
        return new Observation(
            Timestamp: DateTimeOffset.UtcNow,
            Label: label,
            Confidence: confidence,
            FrameWidth: frame.IsEmpty ? 0 : 64,
            FrameHeight: frame.IsEmpty ? 0 : 48);
    }
}
