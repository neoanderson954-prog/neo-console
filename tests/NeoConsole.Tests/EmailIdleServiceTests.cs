using NeoConsole.Services.Triggers;
using Xunit;

namespace NeoConsole.Tests;

public class EmailIdleServiceTests
{
    [Fact]
    public void Constructor_WithoutCredentials_IsNotConfigured()
    {
        // EmailIdleService should gracefully handle missing credentials
        var service = new EmailIdleService(
            credentials: null,
            logger: new FakeLogger<EmailIdleService>());

        Assert.False(service.IsConfigured);
        Assert.False(service.IsConnected);
    }

    [Fact]
    public void Constructor_WithValidCredentials_IsConfigured()
    {
        var service = new EmailIdleService(
            credentials: ("test@example.com", "password"),
            logger: new FakeLogger<EmailIdleService>());

        Assert.True(service.IsConfigured);
        Assert.False(service.IsConnected); // Not connected until ExecuteAsync runs
    }

    [Fact]
    public void Name_ReturnsEmailIdle()
    {
        var service = new EmailIdleService(
            credentials: ("test@example.com", "password"),
            logger: new FakeLogger<EmailIdleService>());

        Assert.Equal("EmailIdle", service.Name);
    }

    [Fact]
    public void Enabled_DefaultsToTrue()
    {
        var service = new EmailIdleService(
            credentials: ("test@example.com", "password"),
            logger: new FakeLogger<EmailIdleService>());

        Assert.True(service.Enabled);
    }

    [Fact]
    public void ReconnectAttempts_StartsAtZero()
    {
        var service = new EmailIdleService(
            credentials: ("test@example.com", "password"),
            logger: new FakeLogger<EmailIdleService>());

        Assert.Equal(0, service.ReconnectAttempts);
    }

    [Fact]
    public void LastError_StartsNull()
    {
        var service = new EmailIdleService(
            credentials: ("test@example.com", "password"),
            logger: new FakeLogger<EmailIdleService>());

        Assert.Null(service.LastError);
    }

    [Fact]
    public void OnMessage_CanBeSubscribed()
    {
        var service = new EmailIdleService(
            credentials: ("test@example.com", "password"),
            logger: new FakeLogger<EmailIdleService>());

        bool called = false;
        service.OnMessage += async (msg) => { called = true; await Task.CompletedTask; };

        // Event subscription should work without throwing
        Assert.False(called); // Not called yet
    }

    [Fact]
    public void Enabled_CanBeDisabled()
    {
        var service = new EmailIdleService(
            credentials: ("test@example.com", "password"),
            logger: new FakeLogger<EmailIdleService>());

        service.Enabled = false;
        Assert.False(service.Enabled);
    }
}

/// <summary>
/// Minimal fake logger for testing without DI.
/// </summary>
public class FakeLogger<T> : Microsoft.Extensions.Logging.ILogger<T>
{
    public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
    public bool IsEnabled(Microsoft.Extensions.Logging.LogLevel logLevel) => false;
    public void Log<TState>(
        Microsoft.Extensions.Logging.LogLevel logLevel,
        Microsoft.Extensions.Logging.EventId eventId,
        TState state,
        Exception? exception,
        Func<TState, Exception?, string> formatter)
    { }
}
