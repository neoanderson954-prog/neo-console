using MailKit;
using MailKit.Net.Imap;
using MailKit.Search;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace NeoConsole.Services.Triggers;

/// <summary>
/// IMAP IDLE-based email trigger. Maintains persistent connection for push notifications.
/// Runs as a BackgroundService, injecting messages via IClaudeProcess when new mail arrives.
/// </summary>
public class EmailIdleService : BackgroundService, IIdleTrigger
{
    private readonly ILogger<EmailIdleService> _logger;
    private readonly IClaudeProcess? _claude;
    private readonly string? _email;
    private readonly string? _password;
    private readonly HashSet<uint> _seenUids = new();

    private ImapClient? _client;
    private bool _initialized;
    private CancellationTokenSource? _idleCts;
    private volatile bool _newMailPending;

    private const string ImapHost = "imap.gmail.com";
    private const int ImapPort = 993;
    private const int MaxReconnectAttempts = 5;
    private static readonly TimeSpan ReconnectDelay = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan IdleTimeout = TimeSpan.FromMinutes(9); // RFC recommends < 29min
    private static readonly TimeSpan StartupDelay = TimeSpan.FromSeconds(15); // Wait for Claude to boot

    public string Name => "EmailIdle";
    public bool Enabled { get; set; } = true;
    public bool IsConnected { get; private set; }
    public bool IsConfigured { get; }
    public string? LastError { get; private set; }
    public int ReconnectAttempts { get; private set; }
    public int UnreadCount { get; private set; }

    public event Func<string, Task>? OnMessage;
    public event Func<int, Task>? OnUnreadCountChanged;

    /// <summary>
    /// Request a refresh of the unread count. Called externally (e.g., after MCP marks email as read).
    /// Interrupts IDLE safely and triggers a refresh cycle.
    /// </summary>
    public void RequestRefresh()
    {
        _logger.LogInformation("EmailIdleService: external refresh requested");
        _refreshRequested = true;
        try
        {
            _idleCts?.Cancel();
        }
        catch (ObjectDisposedException) { }
    }

    private volatile bool _refreshRequested;

    /// <summary>
    /// Constructor for DI - reads credentials from ~/.accounts.
    /// </summary>
    public EmailIdleService(IClaudeProcess claude, ILogger<EmailIdleService> logger)
    {
        _claude = claude;
        _logger = logger;

        try
        {
            var accountsPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                ".accounts");
            var firstLine = File.ReadLines(accountsPath).First();
            var parts = firstLine.Split(':', 2);

            if (parts.Length == 2 && !string.IsNullOrWhiteSpace(parts[0]) && !string.IsNullOrWhiteSpace(parts[1]))
            {
                _email = parts[0];
                _password = parts[1];
                IsConfigured = true;
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to read credentials from ~/.accounts");
        }
    }

    /// <summary>
    /// Constructor for testing - accepts explicit credentials.
    /// </summary>
    public EmailIdleService(
        (string email, string password)? credentials,
        ILogger<EmailIdleService> logger)
    {
        _logger = logger;

        if (credentials.HasValue)
        {
            _email = credentials.Value.email;
            _password = credentials.Value.password;
            IsConfigured = !string.IsNullOrEmpty(_email) && !string.IsNullOrEmpty(_password);
        }
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!IsConfigured)
        {
            _logger.LogWarning("EmailIdleService: not configured, service disabled");
            return;
        }

        // Wait for Claude to start
        await Task.Delay(StartupDelay, stoppingToken);

        _logger.LogInformation("EmailIdleService: starting IMAP IDLE connection...");

        while (!stoppingToken.IsCancellationRequested && Enabled)
        {
            try
            {
                await ConnectAsync(stoppingToken);

                if (!_initialized)
                {
                    await SnapshotExistingUidsAsync(stoppingToken);
                    _initialized = true;
                }

                // IDLE loop with periodic refresh (RFC recommends < 29 min)
                while (!stoppingToken.IsCancellationRequested && IsConnected && Enabled)
                {
                    await IdleAsync(stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                LastError = ex.Message;
                ReconnectAttempts++;
                _logger.LogWarning(ex, "EmailIdleService: connection error (attempt {Attempt}/{Max})",
                    ReconnectAttempts, MaxReconnectAttempts);

                if (ReconnectAttempts >= MaxReconnectAttempts)
                {
                    _logger.LogError("EmailIdleService: max reconnect attempts reached, disabling");
                    Enabled = false;
                    break;
                }

                await DisconnectAsync();
                await Task.Delay(ReconnectDelay, stoppingToken);
            }
        }

        await DisconnectAsync();
        _logger.LogInformation("EmailIdleService: stopped");
    }

    private async Task ConnectAsync(CancellationToken ct)
    {
        _client = new ImapClient();

        _logger.LogDebug("EmailIdleService: connecting to {Host}:{Port}...", ImapHost, ImapPort);
        await _client.ConnectAsync(ImapHost, ImapPort, useSsl: true, ct);
        await _client.AuthenticateAsync(_email, _password, ct);
        await _client.Inbox.OpenAsync(FolderAccess.ReadOnly, ct);

        // Subscribe to new message notifications
        _client.Inbox.CountChanged += OnCountChanged;

        IsConnected = true;
        ReconnectAttempts = 0;
        LastError = null;
        _logger.LogInformation("EmailIdleService: connected, IDLE mode active");
    }

    private async Task DisconnectAsync()
    {
        if (_client != null)
        {
            if (_client.Inbox != null)
                _client.Inbox.CountChanged -= OnCountChanged;

            if (_client.IsConnected)
            {
                try
                {
                    await _client.DisconnectAsync(true);
                }
                catch { }
            }

            _client.Dispose();
            _client = null;
        }
        IsConnected = false;
    }

    private async Task SnapshotExistingUidsAsync(CancellationToken ct)
    {
        var uids = await _client!.Inbox.SearchAsync(SearchQuery.All, ct);
        foreach (var uid in uids)
            _seenUids.Add(uid.Id);
        _logger.LogInformation("EmailIdleService: snapshotted {Count} existing UIDs", _seenUids.Count);

        // Get initial unread count
        var unread = await _client!.Inbox.SearchAsync(SearchQuery.NotSeen, ct);
        UnreadCount = unread.Count;
        _logger.LogInformation("EmailIdleService: initial unread count = {Count}", UnreadCount);

        // Broadcast initial count to UI
        if (OnUnreadCountChanged != null)
            await OnUnreadCountChanged(UnreadCount);

        // Notify Claude of initial status (trigger status on startup)
        if (UnreadCount > 0)
        {
            var statusMessage = $"[Trigger: Email] {UnreadCount} email non lette. Usa email_list_tool per vedere i dettagli.";
            await InjectMessageAsync(statusMessage);
        }
    }

    private async Task IdleAsync(CancellationToken ct)
    {
        _idleCts = new CancellationTokenSource();
        using var timeoutCts = new CancellationTokenSource();
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, _idleCts.Token, timeoutCts.Token);

        // IDLE for up to 9 minutes, then refresh connection
        _ = Task.Delay(IdleTimeout, ct).ContinueWith(_ =>
        {
            try { timeoutCts.Cancel(); } catch { }
        }, TaskScheduler.Default);

        _logger.LogDebug("EmailIdleService: entering IDLE mode...");
        try
        {
            await _client!.IdleAsync(linked.Token);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            // Normal: timeout or new mail signal
        }

        _idleCts.Dispose();
        _idleCts = null;

        // Now IDLE is stopped — safe to read
        if (_newMailPending)
        {
            _newMailPending = false;
            _logger.LogDebug("EmailIdleService: IDLE interrupted by new mail, checking...");
            await CheckNewMessagesAsync();
        }
        else if (_refreshRequested)
        {
            _refreshRequested = false;
            _logger.LogDebug("EmailIdleService: external refresh requested, updating count...");
            await RefreshUnreadCountAsync();
        }
        else
        {
            _logger.LogDebug("EmailIdleService: IDLE timeout, refreshing unread count...");
            await RefreshUnreadCountAsync();
        }
    }

    private async Task RefreshUnreadCountAsync()
    {
        if (_client == null || !_client.IsConnected)
            return;

        try
        {
            // Safe to call — IDLE is stopped before this runs
            var allUnread = await _client.Inbox.SearchAsync(SearchQuery.NotSeen);
            var previousCount = UnreadCount;
            UnreadCount = allUnread.Count;

            if (UnreadCount != previousCount && OnUnreadCountChanged != null)
            {
                _logger.LogInformation("EmailIdleService: unread count refreshed {Old} -> {New}", previousCount, UnreadCount);
                await OnUnreadCountChanged(UnreadCount);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "EmailIdleService: failed to refresh unread count");
        }
    }

    private void OnCountChanged(object? sender, EventArgs e)
    {
        // Don't read here — just signal and cancel IDLE
        // The main loop will handle reading after IDLE stops
        _newMailPending = true;
        try
        {
            _idleCts?.Cancel();
        }
        catch (ObjectDisposedException) { }
    }

    private async Task CheckNewMessagesAsync()
    {
        if (_client == null || !_client.IsConnected)
            return;

        // Safe to call — IDLE is stopped before this runs
        var allUnread = await _client.Inbox.SearchAsync(SearchQuery.NotSeen);
        var previousCount = UnreadCount;
        UnreadCount = allUnread.Count;

        var newUids = allUnread.Where(u => !_seenUids.Contains(u.Id)).ToList();

        IList<IMessageSummary>? fetched = null;
        if (newUids.Count > 0)
        {
            fetched = await _client.Inbox.FetchAsync(
                newUids,
                MessageSummaryItems.Envelope | MessageSummaryItems.BodyStructure);
        }

        if (UnreadCount != previousCount && OnUnreadCountChanged != null)
        {
            _logger.LogInformation("EmailIdleService: unread count changed {Old} -> {New}", previousCount, UnreadCount);
            await OnUnreadCountChanged(UnreadCount);
        }

        if (newUids.Count == 0 || fetched == null)
            return;

        _logger.LogInformation("EmailIdleService: {Count} new email(s) detected", newUids.Count);

        var lines = new List<string>();
        foreach (var msg in fetched.Take(5))
        {
            var uid = msg.UniqueId.Id;
            var from = msg.Envelope.From.FirstOrDefault()?.Name
                ?? msg.Envelope.From.FirstOrDefault()?.ToString()
                ?? "unknown";
            var subject = msg.Envelope.Subject ?? "(no subject)";

            _seenUids.Add(uid);
            lines.Add($"  - {from}: {subject}");
            _logger.LogInformation("  [{Uid}] {From} — {Subject}", uid, from, subject);
        }

        var extra = newUids.Count > 5 ? $"\n  (+{newUids.Count - 5} altre)" : "";
        var message = $"[Email: {newUids.Count} nuovi messaggi]\n"
            + string.Join("\n", lines)
            + extra;

        await InjectMessageAsync(message);
    }

    private async Task InjectMessageAsync(string message)
    {
        // Try to inject via Claude
        if (_claude != null && _claude.IsRunning && _claude.IsIdle)
        {
            _logger.LogInformation("EmailIdleService: injecting message to Claude");
            await _claude.InjectSystemMessageAsync(message);
        }
        else
        {
            _logger.LogDebug("EmailIdleService: Claude not idle, raising OnMessage event");
        }

        // Also raise event for other subscribers
        if (OnMessage != null)
        {
            await OnMessage(message);
        }
    }
}
