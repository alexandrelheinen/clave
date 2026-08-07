namespace Clave.Capture;

/// <summary>
/// Synthetic point-cloud capture stub. RealSense and calibration land in Phase 3.
/// </summary>
public static class PointCloudStub
{
    /// <summary>
    /// Generates a deterministic synthetic XYZ point cloud (flat array: x,y,z per point).
    /// </summary>
    public static float[] GenerateSynthetic(int pointCount = 8)
    {
        if (pointCount <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(pointCount), pointCount, "Point count must be greater than zero.");
        }

        var points = new float[pointCount * 3];
        for (int i = 0; i < pointCount; i++)
        {
            int o = i * 3;
            points[o] = i;
            points[o + 1] = i * 0.5f;
            points[o + 2] = 1.0f;
        }

        return points;
    }

    public static int PointCount(ReadOnlySpan<float> xyz) => xyz.Length / 3;
}
