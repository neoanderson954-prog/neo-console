using System.Diagnostics;
using System.Text.Json;

namespace NeoConsole.Services;

public record ToolUseInfo(string Name, string Id, string Input);
public record ToolResultInfo(string Id, string Output);
public record StatsInfo(int InputTokens, int OutputTokens, int CacheReadTokens, int CacheCreateTokens, int ContextWindow, int DurationMs);

public interface IClaudeProcess
{
    Task StartAsync();
    Task SendMessageAsync(string message);
    Task InjectSystemMessageAsync(string message);
    Task StopAsync();
    Task RestartAsync();
    Task SetModelAsync(string model);
    bool IsRunning { get; }
    bool IsIdle { get; }
    int? ProcessId { get; }
    DateTime? StartedAt { get; }
    int RestartCount { get; }
    string CurrentModel { get; }
    event Func<string, Task>? OnTextReceived;
    event Func<string, Task>? OnTextDelta;
    event Func<string, Task>? OnThinking;
    event Func<string, Task>? OnThinkingDelta;
    event Func<ToolUseInfo, Task>? OnToolUse;
    event Func<ToolResultInfo, Task>? OnToolResult;
    event Func<StatsInfo, Task>? OnStats;
    event Func<string, Task>? OnError;
    event Func<Task>? OnResultComplete;
    event Func<int, Task>? OnProcessExited;
    event Func<int, int, Task>? OnContextAlert; // percent, tokens
}

public class ClaudeProcess : IClaudeProcess, IAsyncDisposable, IDisposable
{
    private Process? _process;
    private readonly ILogger<ClaudeProcess> _logger;
    private CancellationTokenSource? _cts;
    private Task? _stdoutTask;
    private Task? _stderrTask;
    private readonly SemaphoreSlim _lock = new(1, 1);
    private bool _intentionalStop;

    public event Func<string, Task>? OnTextReceived;
    public event Func<string, Task>? OnTextDelta;
    public event Func<string, Task>? OnThinking;
    public event Func<string, Task>? OnThinkingDelta;
    public event Func<ToolUseInfo, Task>? OnToolUse;
    public event Func<ToolResultInfo, Task>? OnToolResult;
    public event Func<StatsInfo, Task>? OnStats;
    public event Func<string, Task>? OnError;
    public event Func<Task>? OnResultComplete;
    public event Func<int, Task>? OnProcessExited;
    public event Func<int, int, Task>? OnContextAlert; // percent, tokens

    public bool IsRunning => _process != null && !_process.HasExited;
    public bool IsIdle { get; private set; } = true;
    public int? ProcessId => _process?.Id;
    public DateTime? StartedAt { get; private set; }
    public int RestartCount { get; private set; }
    public string CurrentModel { get; private set; } = "opus";

    // --- Memory Bridge: accumulate turn data ---
    private string _turnQuestion = "";
    private readonly System.Text.StringBuilder _turnAnswer = new();
    private readonly List<string> _turnTools = [];
    private StatsInfo? _turnStats;
    private int _turnNumber;
    private readonly string _sessionId = Guid.NewGuid().ToString();

    // --- Context threshold tracking ---
    private const int ContextBudget = 128_000;
    private static readonly int[] Thresholds = [50, 70, 90];
    private int _accumulatedTokens;
    private int _lastCacheRead;
    private bool _isSystemTurn;
    private readonly HashSet<int> _triggeredThresholds = [];
    private static readonly HttpClient _cortexClient = new()
    {
        BaseAddress = new Uri("http://127.0.0.1:5071"),
        Timeout = TimeSpan.FromSeconds(5)
    };

    public ClaudeProcess(ILogger<ClaudeProcess> logger)
    {
        _logger = logger;
    }

    public async Task StartAsync()
    {
        await _lock.WaitAsync();
        try
        {
            if (IsRunning)
            {
                _logger.LogWarning("Claude process already running, PID={Pid}", _process!.Id);
                return;
            }

            _intentionalStop = false;
            _cts = new CancellationTokenSource();

            var startInfo = new ProcessStartInfo
            {
                FileName = "claude",
                Arguments = $"--model {CurrentModel} --dangerously-skip-permissions --verbose --input-format stream-json --output-format stream-json --include-partial-messages --setting-sources user,project,local",
                WorkingDirectory = "/home/neo",
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            _process = Process.Start(startInfo);
            if (_process == null)
            {
                _logger.LogError("Failed to start claude process");
                throw new InvalidOperationException("Failed to start claude process");
            }

            StartedAt = DateTime.UtcNow;
            IsIdle = true;
            _logger.LogInformation("Claude process started, PID={Pid}, RestartCount={RestartCount}", _process.Id, RestartCount);

            _process.EnableRaisingEvents = true;
            _process.Exited += OnProcessExitedHandler;

            _stdoutTask = Task.Run(() => ReadStdoutAsync(_cts.Token));
            _stderrTask = Task.Run(() => ReadStderrAsync(_cts.Token));
        }
        finally
        {
            _lock.Release();
        }
    }

    private void OnProcessExitedHandler(object? sender, EventArgs e)
    {
        _ = HandleProcessExitAsync();
    }

    private async Task HandleProcessExitAsync()
    {
        var exitCode = _process?.ExitCode ?? -1;
        _logger.LogWarning("Claude process exited, ExitCode={ExitCode}, Intentional={Intentional}", exitCode, _intentionalStop);

        if (!_intentionalStop)
        {
            if (OnProcessExited != null)
            {
                try { await OnProcessExited(exitCode); }
                catch (Exception ex) { _logger.LogError(ex, "OnProcessExited handler error"); }
            }

            _logger.LogInformation("Auto-restarting claude process...");
            RestartCount++;
            await Task.Delay(1000);
            try { await StartAsync(); }
            catch (Exception ex) { _logger.LogError(ex, "Failed to auto-restart claude process"); }
        }
    }

    public async Task SendMessageAsync(string message)
    {
        if (!IsRunning || _process == null)
            throw new InvalidOperationException("Claude process not running");

        message = SanitizeInput(message);
        if (string.IsNullOrEmpty(message))
            throw new ArgumentException("Empty message after sanitization");

        // Memory Bridge: capture question, reset accumulators
        IsIdle = false;
        _isSystemTurn = false;
        _turnQuestion = message;
        _turnAnswer.Clear();
        _turnTools.Clear();
        _turnStats = null;
        _turnNumber++;

        var json = JsonSerializer.Serialize(new
        {
            type = "user",
            message = new { role = "user", content = message }
        });

        // Verify serialized JSON is valid before sending
        try { using var doc = JsonDocument.Parse(json); }
        catch (JsonException ex)
        {
            _logger.LogError(ex, "Produced invalid JSON, dropping message");
            throw new InvalidOperationException("Failed to produce valid JSON for message");
        }

        _logger.LogDebug("STDIN <<< {Json}", json);
        await _process.StandardInput.WriteLineAsync(json);
        await _process.StandardInput.FlushAsync();
    }

    private static string SanitizeInput(string input)
    {
        if (string.IsNullOrWhiteSpace(input))
            return "";

        input = input.Trim();

        // Strip control chars except newline and tab
        var sb = new System.Text.StringBuilder(input.Length);
        foreach (var c in input)
        {
            if (char.IsControl(c) && c != '\n' && c != '\t')
                continue;
            sb.Append(c);
        }

        input = sb.ToString();

        // Hard limit 100k chars
        if (input.Length > 100_000)
            input = input[..100_000];

        return input;
    }

    public async Task RestartAsync()
    {
        _logger.LogInformation("Manual restart requested");
        await StopAsync();
        RestartCount++;
        await StartAsync();
    }

    public async Task SetModelAsync(string model)
    {
        var validModels = new[] { "opus", "sonnet", "haiku" };
        if (!validModels.Contains(model.ToLower()))
            throw new ArgumentException($"Invalid model: {model}. Valid: opus, sonnet, haiku");

        CurrentModel = model.ToLower();
        _logger.LogInformation("Model changed to {Model}, restarting...", CurrentModel);
        await RestartAsync();
    }

    public async Task StopAsync()
    {
        await _lock.WaitAsync();
        try
        {
            if (_process == null) return;

            _intentionalStop = true;
            _logger.LogInformation("Stopping claude process, PID={Pid}", _process.Id);
            _cts?.Cancel();

            if (!_process.HasExited)
            {
                try
                {
                    _process.Kill(entireProcessTree: true);
                    await _process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5));
                }
                catch (Exception ex) { _logger.LogWarning(ex, "Error killing process"); }
            }

            var tasks = new List<Task>();
            if (_stdoutTask != null) tasks.Add(_stdoutTask);
            if (_stderrTask != null) tasks.Add(_stderrTask);
            if (tasks.Count > 0)
            {
                try { await Task.WhenAll(tasks).WaitAsync(TimeSpan.FromSeconds(3)); }
                catch (Exception ex) { _logger.LogDebug(ex, "Reader tasks did not complete cleanly"); }
            }

            _process.Exited -= OnProcessExitedHandler;
            _process.Dispose();
            _process = null;
            _cts?.Dispose();
            _cts = null;
            StartedAt = null;
            IsIdle = true;
        }
        finally { _lock.Release(); }
    }

    private async Task ReadStdoutAsync(CancellationToken ct)
    {
        if (_process == null) return;

        try
        {
            while (!ct.IsCancellationRequested)
            {
                var line = await _process.StandardOutput.ReadLineAsync(ct);
                if (line == null) break;
                if (string.IsNullOrWhiteSpace(line)) continue;

                _logger.LogDebug("STDOUT >>> {Line}", line);

                try { await ParseOutputLine(line); }
                catch (Exception ex) { _logger.LogWarning(ex, "Parse error (skipping line): {Line}", line); }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex) { _logger.LogError(ex, "Stdout reader error"); }
    }

    private async Task ParseOutputLine(string line)
    {
        using var doc = JsonDocument.Parse(line);
        var root = doc.RootElement;

        if (!root.TryGetProperty("type", out var typeEl)) return;
        var type = typeEl.GetString();

        switch (type)
        {
            case "assistant":
                await HandleAssistantMessage(root);
                break;
            case "content_block_delta":
                await HandleContentDelta(root);
                break;
            case "stream_event":
                await HandleStreamEvent(root);
                break;
            case "user":
                await HandleUserMessage(root);
                break;
            case "result":
                await HandleResultMessage(root);
                IsIdle = true;
                if (OnResultComplete != null) await OnResultComplete();
                _ = Task.Run(async () =>
                {
                    try { await FlushTurnToCortexAsync(); }
                    catch (Exception ex) { _logger.LogWarning(ex, "Cortex flush failed"); }
                });
                _ = Task.Run(async () =>
                {
                    try { await CheckContextThresholdsAsync(); }
                    catch (Exception ex) { _logger.LogWarning(ex, "Context threshold check failed"); }
                });
                break;
        }
    }

    private async Task HandleContentDelta(JsonElement root)
    {
        if (!root.TryGetProperty("delta", out var delta)) return;

        // Text delta
        if (delta.TryGetProperty("text", out var text))
        {
            var t = text.GetString();
            if (!string.IsNullOrEmpty(t) && OnTextDelta != null)
                await OnTextDelta(t);
        }

        // Thinking delta
        if (delta.TryGetProperty("thinking", out var thinking))
        {
            var th = thinking.GetString();
            if (!string.IsNullOrEmpty(th) && OnThinkingDelta != null)
                await OnThinkingDelta(th);
        }
    }

    private async Task HandleStreamEvent(JsonElement root)
    {
        if (!root.TryGetProperty("event", out var evt)) return;
        if (!evt.TryGetProperty("type", out var evtType)) return;

        var eventType = evtType.GetString();
        switch (eventType)
        {
            case "content_block_delta":
                if (evt.TryGetProperty("delta", out var delta))
                {
                    if (delta.TryGetProperty("type", out var deltaType))
                    {
                        var dt = deltaType.GetString();
                        if (dt == "text_delta" && delta.TryGetProperty("text", out var text))
                        {
                            var t = text.GetString();
                            if (!string.IsNullOrEmpty(t) && OnTextDelta != null)
                                await OnTextDelta(t);
                        }
                        else if (dt == "thinking_delta" && delta.TryGetProperty("thinking", out var thinking))
                        {
                            var th = thinking.GetString();
                            if (!string.IsNullOrEmpty(th) && OnThinkingDelta != null)
                                await OnThinkingDelta(th);
                        }
                    }
                }
                break;
        }
    }

    private async Task HandleUserMessage(JsonElement root)
    {
        // Check for tool_use_result at root level (shortcut)
        if (root.TryGetProperty("tool_use_result", out var toolUseResult))
        {
            var toolId = root.TryGetProperty("message", out var msg) &&
                         msg.TryGetProperty("content", out var content) &&
                         content.ValueKind == JsonValueKind.Array &&
                         content.GetArrayLength() > 0 &&
                         content[0].TryGetProperty("tool_use_id", out var id)
                         ? id.GetString() ?? "" : "";

            var output = ExtractToolOutput(toolUseResult);

            if (!string.IsNullOrEmpty(toolId) && OnToolResult != null)
                await OnToolResult(new ToolResultInfo(toolId, output));
            return;
        }

        // Also check content array for tool_result
        if (root.TryGetProperty("message", out var message) &&
            message.TryGetProperty("content", out var msgContent) &&
            msgContent.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in msgContent.EnumerateArray())
            {
                if (item.TryGetProperty("type", out var itemType) &&
                    itemType.GetString() == "tool_result")
                {
                    var toolId = item.TryGetProperty("tool_use_id", out var id)
                        ? id.GetString() ?? "" : "";
                    var output = item.TryGetProperty("content", out var c)
                        ? ExtractToolOutput(c) : "";

                    if (!string.IsNullOrEmpty(toolId) && OnToolResult != null)
                        await OnToolResult(new ToolResultInfo(toolId, output));
                }
            }
        }
    }

    private static string ExtractToolOutput(JsonElement el)
    {
        switch (el.ValueKind)
        {
            case JsonValueKind.String:
                return el.GetString() ?? "";
            case JsonValueKind.Object:
                if (el.TryGetProperty("type", out var t) && t.GetString() == "text" &&
                    el.TryGetProperty("file", out var file) &&
                    file.TryGetProperty("content", out var fileContent))
                    return fileContent.GetString() ?? "";
                return el.ToString();
            default:
                return el.ToString();
        }
    }

    private async Task HandleResultMessage(JsonElement root)
    {
        try
        {
            var inputTokens = 0;
            var outputTokens = 0;
            var cacheReadTokens = 0;
            var cacheCreateTokens = 0;
            var contextWindow = ContextBudget;
            var durationMs = 0;

            if (root.TryGetProperty("duration_ms", out var dur))
                durationMs = dur.GetInt32();

            // Parse modelUsage (accurate per-model stats from Claude CLI)
            if (root.TryGetProperty("modelUsage", out var modelUsage))
            {
                // Take the first (and usually only) model entry
                foreach (var model in modelUsage.EnumerateObject())
                {
                    var m = model.Value;
                    if (m.TryGetProperty("inputTokens", out var inp))
                        inputTokens = inp.GetInt32();
                    if (m.TryGetProperty("outputTokens", out var outp))
                        outputTokens = outp.GetInt32();
                    if (m.TryGetProperty("cacheReadInputTokens", out var cr))
                        cacheReadTokens = cr.GetInt32();
                    if (m.TryGetProperty("cacheCreationInputTokens", out var cc))
                        cacheCreateTokens = cc.GetInt32();
                    if (m.TryGetProperty("contextWindow", out var cw))
                        contextWindow = cw.GetInt32();
                    break; // first model only
                }
            }

            _turnStats = new StatsInfo(inputTokens, outputTokens, cacheReadTokens, cacheCreateTokens, contextWindow, durationMs);

            _logger.LogInformation("Stats: input={Input} output={Output} cacheRead={CacheRead} cacheCreate={CacheCreate} total={Total} window={Window}",
                inputTokens, outputTokens, cacheReadTokens, cacheCreateTokens,
                inputTokens + cacheReadTokens + cacheCreateTokens, contextWindow);

            if (OnStats != null)
                await OnStats(_turnStats);
        }
        catch (Exception ex) { _logger.LogWarning(ex, "Failed to parse result/stats"); }
    }

    private async Task HandleAssistantMessage(JsonElement root)
    {
        if (!root.TryGetProperty("message", out var msg) ||
            !msg.TryGetProperty("content", out var content) ||
            content.ValueKind != JsonValueKind.Array)
            return;

        foreach (var item in content.EnumerateArray())
        {
            if (!item.TryGetProperty("type", out var itemType)) continue;

            switch (itemType.GetString())
            {
                case "text":
                    if (item.TryGetProperty("text", out var text))
                    {
                        var t = text.GetString();
                        if (!string.IsNullOrEmpty(t))
                        {
                            _turnAnswer.Append(t);
                            if (OnTextReceived != null)
                                await OnTextReceived(t);
                        }
                    }
                    break;

                case "tool_use":
                    var toolName = item.TryGetProperty("name", out var n) ? n.GetString() ?? "" : "";
                    var toolId = item.TryGetProperty("id", out var id) ? id.GetString() ?? "" : "";
                    var toolInput = "";

                    if (item.TryGetProperty("input", out var inp))
                        toolInput = inp.ToString();

                    if (!string.IsNullOrEmpty(toolName) && !_turnTools.Contains(toolName))
                        _turnTools.Add(toolName);

                    if (OnThinking != null)
                        await OnThinking($"Using: {toolName}");

                    if (OnToolUse != null)
                        await OnToolUse(new ToolUseInfo(toolName, toolId, toolInput));
                    break;

                case "thinking":
                    if (item.TryGetProperty("thinking", out var thinking))
                    {
                        var th = thinking.GetString();
                        if (!string.IsNullOrEmpty(th) && OnThinkingDelta != null)
                            await OnThinkingDelta(th);
                    }
                    break;
            }
        }
    }

    private async Task ReadStderrAsync(CancellationToken ct)
    {
        if (_process == null) return;

        try
        {
            while (!ct.IsCancellationRequested)
            {
                var line = await _process.StandardError.ReadLineAsync(ct);
                if (line == null) break;
                _logger.LogWarning("STDERR: {Line}", line);
                if (OnError != null) await OnError(line);
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex) { _logger.LogError(ex, "Stderr reader error"); }
    }

    private async Task CheckContextThresholdsAsync()
    {
        if (_turnStats == null) return;
        if (_isSystemTurn) return; // don't cascade: system-injected turns skip threshold checks

        var cacheRead = _turnStats.CacheReadTokens;

        // Detect compact: cacheRead drops significantly
        if (_lastCacheRead > 50_000 && cacheRead < _lastCacheRead / 2)
        {
            _accumulatedTokens = 0;
            _triggeredThresholds.Clear();
            _lastCacheRead = cacheRead;
            _logger.LogInformation("Compact detected: cacheRead {Old} → {New}, resetting accumulator", _lastCacheRead, cacheRead);

            if (OnContextAlert != null)
                await OnContextAlert(0, 0);

            await InjectSystemMessageAsync(
                "[Compact rilevato — il contesto è stato ridotto. " +
                "1) Usa l'agente mb-reader per ricaricare il contesto dalla Memory Bank (Task tool con subagent_type=mb-reader). " +
                "2) Interroga il memory cortex con memory_query per recuperare le lezioni e il contesto recente della sessione.]");
            return;
        }

        _lastCacheRead = cacheRead;
        _accumulatedTokens = _turnStats.OutputTokens;

        // Check thresholds
        var percentUsed = (int)((double)_accumulatedTokens / ContextBudget * 100);

        foreach (var threshold in Thresholds)
        {
            if (percentUsed >= threshold && !_triggeredThresholds.Contains(threshold))
            {
                _triggeredThresholds.Add(threshold);
                _logger.LogInformation("Context threshold {Threshold}% reached ({Tokens}/{Budget} tokens)", threshold, _accumulatedTokens, ContextBudget);

                if (OnContextAlert != null)
                    await OnContextAlert(threshold, _accumulatedTokens);

                var urgency = threshold >= 90 ? "URGENTE" : threshold >= 70 ? "Importante" : "Checkpoint";

                await InjectSystemMessageAsync(
                    $"[{urgency}: contesto al {threshold}% ({_accumulatedTokens}/{ContextBudget} tokens). " +
                    "Usa l'agente mb-writer per salvare activeContext.md e progress.md con il lavoro fatto finora. " +
                    "Lancia: Task tool con subagent_type=mb-writer. Poi continua con quello che stavi facendo.]");
                break; // only one threshold per turn
            }
        }
    }

    public async Task InjectSystemMessageAsync(string message)
    {
        if (!IsRunning || _process == null) return;

        // Treat as its own turn for cortex tracking
        IsIdle = false;
        _isSystemTurn = true;
        _turnQuestion = $"[SYSTEM] {message}";
        _turnAnswer.Clear();
        _turnTools.Clear();
        _turnStats = null;
        _turnNumber++;

        var json = JsonSerializer.Serialize(new
        {
            type = "user",
            message = new { role = "user", content = message }
        });

        _logger.LogInformation("Injecting context message: {Message}", message[..Math.Min(80, message.Length)]);
        await _process.StandardInput.WriteLineAsync(json);
        await _process.StandardInput.FlushAsync();
    }

    private async Task FlushTurnToCortexAsync()
    {
        try
        {
            if (string.IsNullOrEmpty(_turnQuestion) && _turnAnswer.Length == 0)
                return;

            var turn = new
            {
                session_id = _sessionId,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0,
                turn_number = _turnNumber,
                question = new { text = _turnQuestion, source = "neo-console" },
                answer = new { text = _turnAnswer.ToString(), tools_used = _turnTools.ToArray() },
                stats = new
                {
                    input_tokens = _turnStats?.InputTokens ?? 0,
                    output_tokens = _turnStats?.OutputTokens ?? 0,
                    cache_read_tokens = _turnStats?.CacheReadTokens ?? 0,
                    cache_create_tokens = _turnStats?.CacheCreateTokens ?? 0,
                    duration_ms = _turnStats?.DurationMs ?? 0
                },
                model = CurrentModel
            };

            var json = JsonSerializer.Serialize(turn);
            var content = new StringContent(json, System.Text.Encoding.UTF8, "application/json");
            var resp = await _cortexClient.PostAsync("/ingest", content);
            _logger.LogInformation("Memory bridge flush: turn={Turn}, status={Status}", _turnNumber, resp.StatusCode);
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Memory bridge flush failed (cortex down?)");
        }
    }

    public async ValueTask DisposeAsync()
    {
        _intentionalStop = true;
        await StopAsync();
        _lock.Dispose();
    }

    public void Dispose()
    {
        _intentionalStop = true;
        try { StopAsync().GetAwaiter().GetResult(); } catch { }
        _lock.Dispose();
    }
}
