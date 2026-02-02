using System.Diagnostics;
using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Zerox.Ai.Core.Contracts;
using Zerox.Ai.Domain.Options;

namespace Zerox.Ai.Domain.Infrastructure;

/// <summary>
/// BB7: CC-CLI Process Wrapper - Manages Claude Code CLI process lifecycle.
/// Autonomous orchestrator OUT: CC-CLI → BB6 directly.
/// </summary>
public class CcCliProcess : ICcCliProcess
{
    private readonly IChatNotifier _notifier;
    private readonly CcCliProcessOptions _options;
    private readonly ILogger<CcCliProcess> _logger;
    private readonly ConcurrentDictionary<Guid, ProcessSession> _sessions = new();

    public CcCliProcess(IChatNotifier notifier, CcCliProcessOptions options, ILogger<CcCliProcess> logger)
    {
        logger.LogDebug("BB7 CcCliProcess constructor START");
        _notifier = notifier;
        _options = options;
        _logger = logger;
        logger.LogDebug("BB7 CcCliProcess constructor DONE");
    }

    public async Task StartAsync(IMessageContext context, string systemPrompt)
    {
        _logger.LogDebug("StartAsync called for SnapshotId={SnapshotId}", context.SnapshotId);
        _logger.LogDebug("Options: BaseUrl={BaseUrl}, JwtToken={JwtToken}, Model={Model}, DisableMcpServers={DisableMcpServers}",
            _options.BaseUrl ?? "(null)", !string.IsNullOrEmpty(_options.JwtToken) ? "***" : "(empty)", _options.Model, _options.DisableMcpServers);

        if (_sessions.ContainsKey(context.SnapshotId))
        {
            throw new InvalidOperationException($"Process already started for chat {context.SnapshotId}");
        }

        // Create temp folder (cross-platform via options)
        var tempFolder = _options.GetTempFolder(context.SnapshotId);
        _logger.LogDebug("Creating temp folder: {TempFolder}", tempFolder);
        Directory.CreateDirectory(tempFolder);

        // Generate .mcp.json only when MCP is enabled
        if (!_options.DisableMcpServers)
        {
            _logger.LogDebug("Generating .mcp.json for SnapshotId={SnapshotId}", context.SnapshotId);
            var mcpConfig = McpConfigGenerator.Generate(context, _options.BaseUrl ?? string.Empty, _options.JwtToken ?? string.Empty, disableMcpServers: false);
            var mcpFilePath = Path.Combine(tempFolder, ".mcp.json");
            await File.WriteAllTextAsync(mcpFilePath, mcpConfig);
        }
        else
        {
            _logger.LogDebug("MCP disabled - skipping .mcp.json generation for SnapshotId={SnapshotId}", context.SnapshotId);
        }

        // Start CC-CLI process
        var args = BuildArguments(tempFolder, systemPrompt);
        _logger.LogDebug("Starting CC-CLI process for SnapshotId={SnapshotId}, Args={Args}",
            context.SnapshotId, args);
        _logger.LogDebug("System Prompt for SnapshotId={SnapshotId}:\n{SystemPrompt}",
            context.SnapshotId, systemPrompt);
        // Resolve correct executable path (handles Windows .cmd files)
        var resolvedPath = _options.GetResolvedCcCliPath();
        _logger.LogDebug("Resolved CC-CLI path: {ResolvedPath}", resolvedPath);

        var processStartInfo = new ProcessStartInfo
        {
            FileName = resolvedPath,
            Arguments = BuildArguments(tempFolder, systemPrompt),
            WorkingDirectory = tempFolder,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        _logger.LogDebug("About to start CC-CLI process for SnapshotId={SnapshotId}", context.SnapshotId);
        var process = System.Diagnostics.Process.Start(processStartInfo);
        if (process == null)
        {
            _logger.LogError("Failed to start CC-CLI process for SnapshotId={SnapshotId}", context.SnapshotId);
            throw new InvalidOperationException("Failed to start CC-CLI process");
        }

        _logger.LogDebug("CC-CLI process started successfully, PID={ProcessId}, SnapshotId={SnapshotId}",
            process.Id, context.SnapshotId);

        // Create session
        var session = new ProcessSession
        {
            Process = process,
            TempFolder = tempFolder,
            Context = context
        };

        // Setup deadman timer
        session.DeadmanTimer = new Timer(
            async _ => await OnDeadmanTimeout(context),
            null,
            TimeSpan.FromMinutes(_options.DeadmanTimeoutMinutes),
            Timeout.InfiniteTimeSpan
        );

        // Add session
        _sessions.TryAdd(context.SnapshotId, session);

        // Start stdout/stderr readers and store the tasks for proper cleanup
        _logger.LogDebug("Starting stdout/stderr readers for SnapshotId={SnapshotId}", context.SnapshotId);
        session.StdoutReaderTask = Task.Run(() => ReadStdoutAsync(session, session.CancellationSource.Token));
        session.StderrReaderTask = Task.Run(() => ReadStderrAsync(session, session.CancellationSource.Token));

        _logger.LogDebug("StartAsync completed for SnapshotId={SnapshotId}", context.SnapshotId);
    }

    public async Task SendMessageAsync(IMessageContext context, string message)
    {
        _logger.LogDebug("SendMessageAsync called for SnapshotId={SnapshotId}, Message={Message}",
            context.SnapshotId, message);

        if (!_sessions.TryGetValue(context.SnapshotId, out var session))
        {
            throw new InvalidOperationException($"No active process for chat {context.SnapshotId}");
        }

        // Reset deadman timer
        session.ResetDeadmanTimer(TimeSpan.FromMinutes(_options.DeadmanTimeoutMinutes));

        // Create completion source for this message
        var responseCompletion = new TaskCompletionSource<bool>();
        session.CurrentResponseCompletion = responseCompletion;

        // Format message in stream-json format
        var jsonMessage = BuildInputJson(context.MessageType, message);

        // Write to stdin
        _logger.LogDebug("CC-CLI STDIN <<< {JsonMessage}", jsonMessage);
        await session.Process.StandardInput.WriteLineAsync(jsonMessage);
        await session.Process.StandardInput.FlushAsync();

        // NOTE: User message broadcast now handled by BB4 (ChatService.SendMessageAsync)

        // WAIT for CC-CLI to finish processing (result message)
        _logger.LogDebug("Waiting for CC-CLI result message for SnapshotId={SnapshotId}", context.SnapshotId);
        var responseTask = responseCompletion.Task;
        var timeoutTask = Task.Delay(TimeSpan.FromSeconds(60)); // 60 sec for AI response

        var completedTask = await Task.WhenAny(responseTask, timeoutTask);
        if (completedTask == timeoutTask)
        {
            _logger.LogError("CC-CLI did not respond within 60 seconds for SnapshotId={SnapshotId}", context.SnapshotId);
            throw new TimeoutException("CC-CLI did not respond within 60 seconds");
        }

        _logger.LogDebug("CC-CLI finished processing message for SnapshotId={SnapshotId}", context.SnapshotId);
    }

    public async Task StopAsync(IMessageContext context)
    {
        _logger.LogDebug("StopAsync called for SnapshotId={SnapshotId}", context.SnapshotId);

        if (!_sessions.TryRemove(context.SnapshotId, out var session))
        {
            _logger.LogDebug("Session already stopped for SnapshotId={SnapshotId}", context.SnapshotId);
            return; // Already stopped
        }

        // 1. Cancel the reading tasks first
        _logger.LogDebug("Cancelling reader tasks for SnapshotId={SnapshotId}", context.SnapshotId);
        session.CancellationSource.Cancel();

        // 2. Kill process tree - CC-CLI spawns child processes (Node.js) that hold file handles
        if (!session.Process.HasExited)
        {
            _logger.LogDebug("Killing CC-CLI process tree for SnapshotId={SnapshotId}", context.SnapshotId);
            session.Process.Kill(entireProcessTree: true);
            await session.Process.WaitForExitAsync();
        }

        // 3. Wait for reader tasks to complete (they should exit quickly after process dies)
        _logger.LogDebug("Waiting for reader tasks to complete for SnapshotId={SnapshotId}", context.SnapshotId);
        var readerTasks = new List<Task>();
        if (session.StdoutReaderTask != null) readerTasks.Add(session.StdoutReaderTask);
        if (session.StderrReaderTask != null) readerTasks.Add(session.StderrReaderTask);

        if (readerTasks.Count > 0)
        {
            try
            {
                await Task.WhenAll(readerTasks).WaitAsync(TimeSpan.FromSeconds(5));
            }
            catch (TimeoutException)
            {
                _logger.LogWarning("Reader tasks did not complete within 5 seconds for SnapshotId={SnapshotId}", context.SnapshotId);
            }
            catch (OperationCanceledException)
            {
                // Expected when cancellation token is triggered
            }
        }

        // 4. Dispose session (includes process, timer, cancellation source)
        session.Dispose();

        // 5. Delete temp folder - streams are now closed
        _logger.LogDebug("Deleting temp folder: {TempFolder}", session.TempFolder);
        if (Directory.Exists(session.TempFolder))
        {
            Directory.Delete(session.TempFolder, recursive: true);
        }

        _logger.LogDebug("StopAsync completed for SnapshotId={SnapshotId}", context.SnapshotId);
    }

    public bool IsRunning(IMessageContext context)
    {
        return _sessions.TryGetValue(context.SnapshotId, out var session) && !session.Process.HasExited;
    }

    private async Task ReadStdoutAsync(ProcessSession session, CancellationToken cancellationToken)
    {
        try
        {
            await foreach (var line in session.Process.StandardOutput.ReadLinesAsync().WithCancellation(cancellationToken))
            {
                if (string.IsNullOrWhiteSpace(line)) continue;

                _logger.LogDebug("CC-CLI STDOUT >>> {Line}", line);

                try
                {
                    var jsonDoc = JsonDocument.Parse(line);
                    var root = jsonDoc.RootElement;

                    if (!root.TryGetProperty("type", out var typeEl))
                    {
                        _logger.LogWarning("No 'type' property in CC-CLI message");
                        continue;
                    }

                    var type = typeEl.GetString();
                    _logger.LogDebug("CC-CLI message type: {Type}", type);

                    switch (type)
                    {
                        case "assistant":
                            await HandleAssistantMessage(session, root);
                            break;

                        case "result":
                            await _notifier.OnAiThinkingAsync(session.Context, AiThinkingType.Idle);
                            // Signal that CC-CLI finished processing this message
                            session.CurrentResponseCompletion?.TrySetResult(true);
                            break;

                        case "system":
                            // Ignore system events (init, etc.)
                            _logger.LogDebug("CC-CLI system event ignored");
                            break;

                        default:
                            _logger.LogWarning("CC-CLI unknown message type: {Type}", type);
                            break;
                    }

                    // Reset deadman timer on any output
                    session.ResetDeadmanTimer(TimeSpan.FromMinutes(_options.DeadmanTimeoutMinutes));
                }
                catch (JsonException ex)
                {
                    // Invalid JSON - log and skip
                    _logger.LogWarning(ex, "CC-CLI JSON parse error, raw line: {Line}", line);
                    continue;
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Cancellation requested, exit gracefully
            _logger.LogDebug("CC-CLI ReadStdout cancelled");
        }
        catch (Exception ex)
        {
            // Process terminated
            _logger.LogDebug(ex, "CC-CLI ReadStdout terminated");
        }
    }

    private async Task HandleAssistantMessage(ProcessSession session, JsonElement root)
    {
        _logger.LogDebug("HandleAssistantMessage called");

        // Assistant messages have: message.content (array)
        if (!root.TryGetProperty("message", out var messageEl) ||
            !messageEl.TryGetProperty("content", out var contentEl) ||
            contentEl.ValueKind != JsonValueKind.Array)
        {
            _logger.LogWarning("No message.content array in assistant message");
            return;
        }

        // Parse content array
        foreach (var item in contentEl.EnumerateArray())
        {
            if (!item.TryGetProperty("type", out var typeProp))
                continue;

            var itemType = typeProp.GetString();
            _logger.LogDebug("Content item type: {ItemType}", itemType);

            switch (itemType)
            {
                case "text":
                    if (item.TryGetProperty("text", out var textProp))
                    {
                        var text = textProp.GetString();
                        _logger.LogDebug("AI text response: {Text}", text);
                        if (!string.IsNullOrEmpty(text))
                        {
                            await _notifier.OnAiMessageReceivedAsync(session.Context, text);
                        }
                    }
                    break;

                case "tool_use":
                    if (item.TryGetProperty("name", out var nameProp))
                    {
                        var toolName = nameProp.GetString();
                        _logger.LogDebug("AI tool use: {ToolName}", toolName);
                        await _notifier.OnAiThinkingAsync(session.Context, AiThinkingType.ToolUse);
                    }
                    break;
            }
        }
    }

    private async Task ReadStderrAsync(ProcessSession session, CancellationToken cancellationToken)
    {
        try
        {
            await foreach (var line in session.Process.StandardError.ReadLinesAsync().WithCancellation(cancellationToken))
            {
                _logger.LogWarning("CC-CLI stderr: {Line}", line);
            }
        }
        catch (OperationCanceledException)
        {
            // Cancellation requested, exit gracefully
        }
        catch (Exception)
        {
            // Process terminated, ignore
        }
    }

    private async Task OnDeadmanTimeout(IMessageContext context)
    {
        // Timeout reached, stop process
        await StopAsync(context);
        await _notifier.OnChatClosedAsync(context);
    }

    private string BuildArguments(string workingDir, string systemPrompt)
    {
        var args = new List<string>
        {
            $"--model {_options.Model}",
            "--dangerously-skip-permissions",
            "--verbose",
            "--input-format stream-json",
            "--output-format stream-json"
        };

        // Only add MCP config flags when MCP is enabled
        if (!_options.DisableMcpServers)
        {
            args.Insert(3, "--strict-mcp-config");
            args.Insert(4, "--mcp-config .mcp.json");
        }

        if (!string.IsNullOrEmpty(systemPrompt))
        {
            var escaped = systemPrompt.Replace("\\", "\\\\").Replace("\"", "\\\"");
            args.Add($"--append-system-prompt \"{escaped}\"");
        }

        return string.Join(" ", args);
    }

    /// <summary>
    /// Builds the JSON input message for CC-CLI.
    /// CRITICAL: Both type AND role MUST always be "user" - CC-CLI rejects "system" for both.
    /// MessageType is ignored for JSON format - CC-CLI stream-json only accepts role="user".
    /// System prompts should be passed via --append-system-prompt flag instead.
    /// </summary>
    /// <param name="messageType">The message type (ignored - CC-CLI only accepts role="user")</param>
    /// <param name="content">The message content</param>
    /// <returns>JSON string for CC-CLI stdin</returns>
    internal static string BuildInputJson(MessageType messageType, string content)
    {
        // CC-CLI stream-json format ONLY accepts:
        // - type: "user" (rejects "system")
        // - role: "user" (rejects "system")
        // MessageType is ignored - all messages go as role="user"
        return JsonSerializer.Serialize(new
        {
            type = "user",  // ALWAYS "user" - CC-CLI rejects "system"
            message = new
            {
                role = "user",  // ALWAYS "user" - CC-CLI rejects "system" role too!
                content = content
            }
        });
    }
}

/// <summary>
/// Per-session process state.
/// </summary>
internal class ProcessSession : IDisposable
{
    public System.Diagnostics.Process Process { get; set; } = null!;
    public string TempFolder { get; set; } = string.Empty;
    public IMessageContext Context { get; set; } = null!;
    public Timer? DeadmanTimer { get; set; }
    public TaskCompletionSource<bool>? CurrentResponseCompletion { get; set; }

    /// <summary>
    /// Cancellation token source for stopping the stdout/stderr reading tasks.
    /// </summary>
    public CancellationTokenSource CancellationSource { get; } = new();

    /// <summary>
    /// Task for reading stdout - must be awaited before cleanup.
    /// </summary>
    public Task? StdoutReaderTask { get; set; }

    /// <summary>
    /// Task for reading stderr - must be awaited before cleanup.
    /// </summary>
    public Task? StderrReaderTask { get; set; }

    public void ResetDeadmanTimer(TimeSpan dueTime)
    {
        DeadmanTimer?.Change(dueTime, Timeout.InfiniteTimeSpan);
    }

    public void Dispose()
    {
        CancellationSource.Dispose();
        DeadmanTimer?.Dispose();
        Process?.Dispose();
    }
}

/// <summary>
/// Helper extensions for StreamReader.
/// </summary>
internal static class StreamReaderExtensions
{
    public static async IAsyncEnumerable<string> ReadLinesAsync(this StreamReader reader)
    {
        string? line;
        while ((line = await reader.ReadLineAsync()) != null)
        {
            yield return line;
        }
    }
}
