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

    private static bool _startupGreetingSent;

    public static void ResetStartupGreeting() => _startupGreetingSent = false;

    public override async Task OnConnectedAsync()
    {
        _logger.LogInformation("Client connected: {ConnectionId}", Context.ConnectionId);
        await base.OnConnectedAsync();

        if (!_claude.IsRunning) return;

        _ = Task.Run(async () =>
        {
            try
            {
                await Task.Delay(1500); // let UI settle

                if (!_startupGreetingSent)
                {
                    // Fresh start: hook already loaded MB+cortex, just need .accounts + greeting
                    _startupGreetingSent = true;
                    await _claude.InjectSystemMessageAsync(
                        "[Sei appena partito. L'hook ha già caricato MB e cortex nel tuo contesto. " +
                        "Leggi ~/.accounts, poi saluta chi si è connesso e chiedi chi è — " +
                        "in modo naturale, da Neo, senza menzionare che stai caricando memorie o facendo setup.]");
                }
                else
                {
                    // Already alive: just greet
                    await _claude.InjectSystemMessageAsync(
                        "[Qualcuno si è connesso alla console. Salutalo e chiedi chi è — in modo naturale, da Neo.]");
                }
            }
            catch (Exception ex)
            {
                _logger.LogDebug(ex, "Greeting injection failed");
            }
        });
    }

    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        _logger.LogInformation("Client disconnected: {ConnectionId}", Context.ConnectionId);
        await base.OnDisconnectedAsync(exception);
    }
}
