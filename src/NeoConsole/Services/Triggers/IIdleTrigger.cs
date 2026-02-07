namespace NeoConsole.Services.Triggers;

/// <summary>
/// Interface for push-based triggers that maintain persistent connections.
/// Unlike ITrigger (polling), IIdleTrigger receives events in real-time.
/// Implementors are typically BackgroundService instances.
/// </summary>
public interface IIdleTrigger
{
    string Name { get; }
    bool Enabled { get; set; }
    bool IsConnected { get; }
    bool IsConfigured { get; }
    string? LastError { get; }
    int ReconnectAttempts { get; }

    /// <summary>
    /// Fired when the trigger has a message to inject into Claude.
    /// </summary>
    event Func<string, Task>? OnMessage;
}
