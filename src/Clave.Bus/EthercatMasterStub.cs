namespace Clave.Bus;

/// <summary>
/// EtherCAT master stub. SOEM / hardware paths are Phase 4 (optional).
/// </summary>
public sealed class EthercatMasterStub
{
    private bool _running;

    public bool IsRunning => _running;

    public int ConfiguredSlaves { get; private set; }

    public void Configure(int slaveCount)
    {
        if (slaveCount < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(slaveCount), slaveCount, "Slave count cannot be negative.");
        }

        if (_running)
        {
            throw new InvalidOperationException("Cannot reconfigure while the master is running.");
        }

        ConfiguredSlaves = slaveCount;
    }

    public void Start()
    {
        _running = true;
    }

    public void Stop()
    {
        _running = false;
    }

    public string StatusSummary() =>
        _running
            ? $"EtherCAT stub running with {ConfiguredSlaves} configured slave(s)."
            : $"EtherCAT stub idle ({ConfiguredSlaves} configured slave(s)).";
}
