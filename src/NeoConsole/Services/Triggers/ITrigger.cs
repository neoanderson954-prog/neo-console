namespace NeoConsole.Services.Triggers;

public interface ITrigger
{
    string Name { get; }
    TimeSpan Interval { get; }
    bool Enabled { get; set; }
    DateTime? LastRun { get; }
    string? LastError { get; }
    int ConsecutiveFailures { get; }
    Task<string?> CheckAsync(CancellationToken ct);
}
