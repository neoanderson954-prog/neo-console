using Microsoft.AspNetCore.SignalR;
using NeoConsole.Hubs;
using NeoConsole.Services;
using NeoConsole.Services.Triggers;
using Serilog;

var builder = WebApplication.CreateBuilder(args);

builder.Host.UseSerilog((context, config) =>
    config.ReadFrom.Configuration(context.Configuration));

builder.Services.AddSignalR();
builder.Services.AddSingleton<IClaudeProcess, ClaudeProcess>();

// Email service + Trigger pipeline
builder.Services.AddSingleton<EmailService>();
builder.Services.AddSingleton<ITrigger, EmailTrigger>();
builder.Services.AddHostedService<TriggerWorker>();

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

// Trigger status
app.MapGet("/triggers", (IEnumerable<ITrigger> triggers) => Results.Ok(
    triggers.Select(t => new
    {
        name = t.Name,
        enabled = t.Enabled,
        interval = t.Interval.TotalSeconds,
        lastRun = t.LastRun,
        lastError = t.LastError,
        consecutiveFailures = t.ConsecutiveFailures
    })
));

// Email detail endpoints (on-demand, token-efficient)
app.MapGet("/email/list", (EmailService email) => Results.Ok(email.GetCachedEmails()));

app.MapGet("/email/{uid}", (uint uid, EmailService email) =>
{
    var e = email.GetEmail(uid);
    return e is not null ? Results.Ok(e) : Results.NotFound();
});

app.MapGet("/email/{uid}/body", async (uint uid, EmailService email, CancellationToken ct) =>
{
    var body = await email.GetBodyAsync(uid, ct);
    return body is not null ? Results.Ok(new { uid, body }) : Results.NotFound();
});

app.MapGet("/email/{uid}/attachments/{index}", async (uint uid, int index, EmailService email, CancellationToken ct) =>
{
    var result = await email.GetAttachmentAsync(uid, index, ct);
    if (result is null) return Results.NotFound();
    return Results.File(result.Value.Data, result.Value.ContentType, result.Value.FileName);
});

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
        stats.CacheReadTokens,
        stats.CacheCreateTokens,
        stats.ContextWindow,
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

claude.OnContextAlert += async (percent, tokens) =>
{
    logger.LogInformation("Context alert: {Percent}% ({Tokens} tokens)", percent, tokens);
    await hubContext.Clients.All.SendAsync("ReceiveContextAlert", new { percent, tokens });
};

claude.OnProcessExited += async (exitCode) =>
{
    logger.LogWarning("Claude process crashed with exit code {ExitCode}, notifying clients", exitCode);
    ChatHub.ResetStartupGreeting();
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
