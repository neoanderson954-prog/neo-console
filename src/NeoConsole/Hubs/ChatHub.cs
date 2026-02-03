using Microsoft.AspNetCore.SignalR;
using NeoConsole.Services;

namespace NeoConsole.Hubs;

public class ChatHub : Hub
{
    private readonly IClaudeProcess _claude;
    private readonly ILogger<ChatHub> _logger;

    public ChatHub(IClaudeProcess claude, ILogger<ChatHub> logger)
    {
        _claude = claude;
        _logger = logger;
    }

    public async Task SendMessage(string message)
    {
        if (string.IsNullOrWhiteSpace(message))
        {
            await Clients.Caller.SendAsync("ReceiveError", "Empty message");
            return;
        }

        _logger.LogInformation("Message received: {Message}", message.Trim());

        if (!_claude.IsRunning)
        {
            await Clients.Caller.SendAsync("ReceiveError", "Claude process not running");
            return;
        }

        try
        {
            await _claude.SendMessageAsync(message);
        }
        catch (ArgumentException ex)
        {
            await Clients.Caller.SendAsync("ReceiveError", $"Invalid message: {ex.Message}");
        }
        catch (InvalidOperationException ex)
        {
            await Clients.Caller.SendAsync("ReceiveError", ex.Message);
        }
    }

    public override async Task OnConnectedAsync()
    {
        _logger.LogInformation("Client connected: {ConnectionId}", Context.ConnectionId);
        await base.OnConnectedAsync();
    }

    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        _logger.LogInformation("Client disconnected: {ConnectionId}", Context.ConnectionId);
        await base.OnDisconnectedAsync(exception);
    }
}
