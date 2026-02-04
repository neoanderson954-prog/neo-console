namespace NeoConsole.Services.Triggers;

public class TriggerWorker : BackgroundService
{
    private readonly IClaudeProcess _claude;
    private readonly IEnumerable<ITrigger> _triggers;
    private readonly ILogger<TriggerWorker> _logger;
    private readonly Queue<string> _pendingMessages = new();
    private static readonly TimeSpan TickInterval = TimeSpan.FromSeconds(30);
    private const int MaxConsecutiveFailures = 3;

    public TriggerWorker(
        IClaudeProcess claude,
        IEnumerable<ITrigger> triggers,
        ILogger<TriggerWorker> logger)
    {
        _claude = claude;
        _triggers = triggers;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("TriggerWorker started with {Count} trigger(s): {Names}",
            _triggers.Count(),
            string.Join(", ", _triggers.Select(t => t.Name)));

        // Wait for Claude to boot up
        await Task.Delay(TimeSpan.FromSeconds(10), stoppingToken);

        _claude.OnResultComplete += OnClaudeIdle;

        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                foreach (var trigger in _triggers)
                {
                    if (!trigger.Enabled) continue;
                    if (trigger.LastRun.HasValue &&
                        DateTime.UtcNow - trigger.LastRun.Value < trigger.Interval)
                        continue;

                    await RunTriggerAsync(trigger, stoppingToken);
                }

                await Task.Delay(TickInterval, stoppingToken);
            }
        }
        catch (OperationCanceledException) { }
        finally
        {
            _claude.OnResultComplete -= OnClaudeIdle;
        }
    }

    private async Task RunTriggerAsync(ITrigger trigger, CancellationToken ct)
    {
        try
        {
            var message = await trigger.CheckAsync(ct);

            if (message != null)
            {
                _logger.LogInformation("Trigger [{Name}] fired: {Preview}",
                    trigger.Name,
                    message.Length > 80 ? message[..80] + "..." : message);

                await InjectOrQueueAsync(message);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Trigger [{Name}] failed ({Failures}/{Max})",
                trigger.Name,
                trigger.ConsecutiveFailures,
                MaxConsecutiveFailures);

            if (trigger.ConsecutiveFailures >= MaxConsecutiveFailures)
            {
                trigger.Enabled = false;
                _logger.LogWarning("Trigger [{Name}] disabled after {Max} consecutive failures",
                    trigger.Name, MaxConsecutiveFailures);
            }
        }
    }

    private async Task InjectOrQueueAsync(string message)
    {
        if (_claude.IsRunning && _claude.IsIdle)
        {
            await _claude.InjectSystemMessageAsync(message);
        }
        else
        {
            _pendingMessages.Enqueue(message);
            _logger.LogDebug("Claude busy, queued trigger message ({Count} pending)",
                _pendingMessages.Count);
        }
    }

    private async Task OnClaudeIdle()
    {
        if (_pendingMessages.TryDequeue(out var message))
        {
            await Task.Delay(500);
            if (_claude.IsRunning)
            {
                await _claude.InjectSystemMessageAsync(message);
            }
        }
    }
}
