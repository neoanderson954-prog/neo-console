using Microsoft.AspNetCore.SignalR;
using NeoConsole.Hubs;
using NeoConsole.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddSignalR();
builder.Services.AddSingleton<IClaudeProcess, ClaudeProcess>();

var app = builder.Build();

app.UseDefaultFiles();
app.UseStaticFiles();

app.MapHub<ChatHub>("/hub/chat");

// Health check with process details
var claude = app.Services.GetRequiredService<IClaudeProcess>();

app.MapGet("/health", () => Results.Ok(new
{
    status = claude.IsRunning ? "healthy" : "degraded",
    claude = new
    {
        running = claude.IsRunning,
        pid = claude.ProcessId,
        startedAt = claude.StartedAt,
        restartCount = claude.RestartCount,
        model = claude.CurrentModel
    }
}));

// Model endpoint
app.MapPost("/model/{model}", async (string model) =>
{
    try
    {
        await claude.SetModelAsync(model);
        return Results.Ok(new { model = claude.CurrentModel, status = "restarted" });
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { error = ex.Message });
    }
});

// Restart endpoint
app.MapPost("/restart", async () =>
{
    await claude.RestartAsync();
    return Results.Ok(new { status = "restarted", pid = claude.ProcessId });
});

// Wire up events
var hubContext = app.Services.GetRequiredService<IHubContext<ChatHub>>();
var logger = app.Services.GetRequiredService<ILogger<Program>>();

claude.OnTextReceived += async (text) =>
{
    await hubContext.Clients.All.SendAsync("ReceiveMessage", text);
};

claude.OnTextDelta += async (delta) =>
{
    await hubContext.Clients.All.SendAsync("ReceiveTextDelta", delta);
};

claude.OnThinkingDelta += async (delta) =>
{
    await hubContext.Clients.All.SendAsync("ReceiveThinkingDelta", delta);
};

claude.OnThinking += async (status) =>
{
    await hubContext.Clients.All.SendAsync("ReceiveThinking", status);
};

claude.OnToolUse += async (tool) =>
{
    await hubContext.Clients.All.SendAsync("ReceiveToolUse", new { tool.Name, tool.Id, tool.Input });
};

claude.OnToolResult += async (result) =>
{
    await hubContext.Clients.All.SendAsync("ReceiveToolResult", new { result.Id, result.Output });
};

claude.OnStats += async (stats) =>
{
    await hubContext.Clients.All.SendAsync("ReceiveStats", new {
        stats.InputTokens,
        stats.OutputTokens,
        stats.CostUsd,
        stats.DurationMs
    });
};

claude.OnError += async (error) =>
{
    await hubContext.Clients.All.SendAsync("ReceiveError", error);
};

claude.OnResultComplete += async () =>
{
    await hubContext.Clients.All.SendAsync("ReceiveComplete");
};

claude.OnProcessExited += async (exitCode) =>
{
    logger.LogWarning("Claude process crashed with exit code {ExitCode}, notifying clients", exitCode);
    await hubContext.Clients.All.SendAsync("ReceiveError", $"Claude process crashed (exit code: {exitCode}). Restarting...");
};

await claude.StartAsync();
logger.LogInformation("Claude process started, PID={Pid}, ready for connections", claude.ProcessId);

app.Lifetime.ApplicationStopping.Register(() =>
{
    logger.LogInformation("Application stopping, shutting down claude process...");
    claude.StopAsync().GetAwaiter().GetResult();
});

app.Run();
