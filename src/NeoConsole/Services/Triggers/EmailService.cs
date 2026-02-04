using MailKit;
using MailKit.Net.Imap;
using MailKit.Search;
using MimeKit;

namespace NeoConsole.Services.Triggers;

public record EmailSummary(
    uint Uid,
    string From,
    string Subject,
    string[] To,
    string[] Cc,
    DateTimeOffset Date,
    string[] AttachmentNames,
    int AttachmentCount,
    bool HasBody
);

public class EmailService
{
    private readonly ILogger<EmailService> _logger;
    private readonly string _email = "";
    private readonly string _appPassword = "";
    private readonly HashSet<uint> _seenUids = new();
    private readonly Dictionary<uint, EmailSummary> _cache = new();
    private readonly Dictionary<uint, string> _bodyCache = new();
    private readonly LinkedList<uint> _cacheOrder = new();
    private readonly LinkedList<uint> _bodyCacheOrder = new();
    private bool _initialized;
    public bool IsConfigured { get; }

    private const int MaxSummaries = 200;
    private const int MaxBodies = 30;
    private const int MaxSeenUids = 2000;

    public EmailService(ILogger<EmailService> logger)
    {
        _logger = logger;

        try
        {
            var accountsPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                ".accounts");
            var firstLine = File.ReadLines(accountsPath).First();
            var parts = firstLine.Split(':', 2);
            if (parts.Length != 2 || string.IsNullOrWhiteSpace(parts[0]) || string.IsNullOrWhiteSpace(parts[1]))
            {
                _logger.LogError("EmailService: invalid credentials format in ~/.accounts (expected email:password)");
                return;
            }
            _email = parts[0];
            _appPassword = parts[1];
            IsConfigured = true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "EmailService: failed to read credentials from ~/.accounts — email trigger disabled");
        }
    }

    public async Task<List<EmailSummary>> CheckNewAsync(CancellationToken ct)
    {
        if (!IsConfigured)
            return [];

        _logger.LogDebug("EmailService: checking for new emails...");

        using var client = new ImapClient();
        await client.ConnectAsync("imap.gmail.com", 993, useSsl: true, cancellationToken: ct);
        await client.AuthenticateAsync(_email, _appPassword, ct);
        await client.Inbox.OpenAsync(FolderAccess.ReadOnly, ct);

        var uids = await client.Inbox.SearchAsync(SearchQuery.NotSeen, ct);

        if (!_initialized)
        {
            foreach (var uid in uids)
                _seenUids.Add(uid.Id);
            _initialized = true;
            _logger.LogInformation("EmailService initialized, {Count} existing unread, UIDs snapshotted", uids.Count);
            await client.DisconnectAsync(true, ct);
            return [];
        }

        var newUids = uids.Where(u => !_seenUids.Contains(u.Id)).ToList();

        if (newUids.Count == 0)
        {
            _logger.LogDebug("EmailService: no new emails ({Total} total unread)", uids.Count);
            await client.DisconnectAsync(true, ct);
            return [];
        }

        _logger.LogInformation("EmailService: {New} new email(s) found ({Total} total unread)", newUids.Count, uids.Count);

        // Fetch envelopes + body structure (no body content!)
        var fetched = await client.Inbox.FetchAsync(
            newUids, MessageSummaryItems.Envelope | MessageSummaryItems.BodyStructure, ct);

        var results = new List<EmailSummary>();
        foreach (var msg in fetched)
        {
            var uid = msg.UniqueId.Id;
            var from = msg.Envelope.From.FirstOrDefault()?.Name
                ?? msg.Envelope.From.FirstOrDefault()?.ToString()
                ?? "unknown";
            var subject = msg.Envelope.Subject ?? "(no subject)";
            var to = msg.Envelope.To.Select(a => a.Name ?? a.ToString()).ToArray();
            var cc = msg.Envelope.Cc.Select(a => a.Name ?? a.ToString()).ToArray();
            var date = msg.Envelope.Date ?? DateTimeOffset.UtcNow;

            // Extract attachment info from body structure (no download)
            var attachments = new List<string>();
            if (msg.Body is BodyPartMultipart multipart)
                CollectAttachmentNames(multipart, attachments);

            var summary = new EmailSummary(
                uid, from, subject, to, cc, date,
                attachments.ToArray(), attachments.Count, true
            );

            EvictIfNeeded(_cache, _cacheOrder, uid, MaxSummaries);
            _cache[uid] = summary;
            _cacheOrder.AddLast(uid);
            _seenUids.Add(uid);
            results.Add(summary);

            _logger.LogInformation("  [{Uid}] {From} — {Subject} ({Attachments} allegati, {Date})",
                uid, from, subject, attachments.Count, date.ToString("HH:mm"));
        }

        await client.DisconnectAsync(true, ct);
        TrimSeenUids();
        _logger.LogInformation("EmailService: {Count} new emails cached", results.Count);
        return results;
    }

    public List<EmailSummary> GetCachedEmails() =>
        _cache.Values.OrderByDescending(e => e.Date).ToList();

    public EmailSummary? GetEmail(uint uid) =>
        _cache.GetValueOrDefault(uid);

    public async Task<string?> GetBodyAsync(uint uid, CancellationToken ct)
    {
        if (_bodyCache.TryGetValue(uid, out var cached))
        {
            _logger.LogDebug("GetBody [{Uid}]: serving from cache ({Len} chars)", uid, cached.Length);
            return cached;
        }

        _logger.LogDebug("GetBody [{Uid}]: fetching from IMAP...", uid);

        using var client = new ImapClient();
        await client.ConnectAsync("imap.gmail.com", 993, useSsl: true, cancellationToken: ct);
        await client.AuthenticateAsync(_email, _appPassword, ct);
        await client.Inbox.OpenAsync(FolderAccess.ReadOnly, ct);

        var message = await client.Inbox.GetMessageAsync(new MailKit.UniqueId(uid), ct);
        await client.DisconnectAsync(true, ct);

        var body = message.TextBody ?? message.HtmlBody ?? "(empty)";
        var originalLen = body.Length;

        // Truncate to save tokens
        if (body.Length > 5000)
            body = body[..5000] + "\n...(troncato)";

        EvictIfNeeded(_bodyCache, _bodyCacheOrder, uid, MaxBodies);
        _bodyCache[uid] = body;
        _bodyCacheOrder.AddLast(uid);
        _logger.LogInformation("GetBody [{Uid}]: {From} — {Subject} ({OrigLen} chars{Trunc})",
            uid,
            message.From.FirstOrDefault()?.Name ?? message.From.FirstOrDefault()?.ToString() ?? "?",
            message.Subject ?? "(no subject)",
            originalLen,
            originalLen > 5000 ? ", troncato a 5000" : "");
        return body;
    }

    public async Task<(string FileName, byte[] Data, string ContentType)?> GetAttachmentAsync(
        uint uid, int index, CancellationToken ct)
    {
        _logger.LogDebug("GetAttachment [{Uid}] index {Index}: fetching...", uid, index);

        using var client = new ImapClient();
        await client.ConnectAsync("imap.gmail.com", 993, useSsl: true, cancellationToken: ct);
        await client.AuthenticateAsync(_email, _appPassword, ct);
        await client.Inbox.OpenAsync(FolderAccess.ReadOnly, ct);

        var message = await client.Inbox.GetMessageAsync(new MailKit.UniqueId(uid), ct);
        await client.DisconnectAsync(true, ct);

        var attachments = message.Attachments.ToList();
        if (index < 0 || index >= attachments.Count)
        {
            _logger.LogWarning("GetAttachment [{Uid}] index {Index}: not found ({Total} attachments available)",
                uid, index, attachments.Count);
            return null;
        }

        var attachment = attachments[index];
        var fileName = attachment.ContentDisposition?.FileName
            ?? attachment.ContentType.Name
            ?? $"attachment_{index}";
        var contentType = attachment.ContentType.MimeType;

        using var ms = new MemoryStream();
        if (attachment is MimePart part)
            await part.Content.DecodeToAsync(ms, ct);

        _logger.LogInformation("GetAttachment [{Uid}] index {Index}: {FileName} ({ContentType}, {Size} bytes)",
            uid, index, fileName, contentType, ms.Length);

        return (fileName, ms.ToArray(), contentType);
    }

    private static void EvictIfNeeded<T>(Dictionary<uint, T> dict, LinkedList<uint> order, uint newKey, int max)
    {
        if (dict.ContainsKey(newKey)) return;
        while (dict.Count >= max && order.First != null)
        {
            dict.Remove(order.First.Value);
            order.RemoveFirst();
        }
    }

    private void TrimSeenUids()
    {
        if (_seenUids.Count <= MaxSeenUids) return;
        // Keep only the highest UIDs (most recent)
        var sorted = _seenUids.OrderByDescending(u => u).Take(MaxSeenUids).ToHashSet();
        _seenUids.Clear();
        _seenUids.UnionWith(sorted);
        _logger.LogDebug("Trimmed _seenUids to {Count}", _seenUids.Count);
    }

    private static void CollectAttachmentNames(BodyPartMultipart multipart, List<string> names)
    {
        foreach (var part in multipart.BodyParts)
        {
            if (part is BodyPartMultipart nested)
            {
                CollectAttachmentNames(nested, names);
            }
            else if (part is BodyPartBasic basic &&
                     (basic.IsAttachment ||
                      basic.ContentDisposition?.Disposition == "attachment"))
            {
                names.Add(basic.FileName ?? basic.ContentType.Name ?? $"file.{basic.ContentType.MediaSubtype}");
            }
        }
    }
}
