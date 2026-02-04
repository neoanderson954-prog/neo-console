namespace NeoConsole.Services.Triggers;

public class EmailTrigger : ITrigger
{
    private readonly EmailService _emailService;
    private readonly ILogger<EmailTrigger> _logger;
    private int _consecutiveFailures;

    public string Name => "Email";
    public TimeSpan Interval => TimeSpan.FromMinutes(5);
    public bool Enabled { get; set; } = true;
    public DateTime? LastRun { get; private set; }
    public string? LastError { get; private set; }
    public int ConsecutiveFailures => _consecutiveFailures;

    public EmailTrigger(EmailService emailService, ILogger<EmailTrigger> logger)
    {
        _emailService = emailService;
        _logger = logger;
    }

    public async Task<string?> CheckAsync(CancellationToken ct)
    {
        LastRun = DateTime.UtcNow;

        try
        {
            var newEmails = await _emailService.CheckNewAsync(ct);

            _consecutiveFailures = 0;
            LastError = null;

            if (newEmails.Count == 0)
                return null;

            // Compact notification — minimal tokens
            var lines = newEmails.Take(5).Select(e =>
            {
                var att = e.AttachmentCount > 0 ? $" [{e.AttachmentCount} allegati]" : "";
                return $"  - {e.From}: {e.Subject}{att}";
            });

            var extra = newEmails.Count > 5 ? $"\n  (+{newEmails.Count - 5} altre)" : "";

            return $"[Email: {newEmails.Count} nuovi messaggi]\n"
                + string.Join("\n", lines)
                + extra
                + "\n  Per dettagli usa: curl localhost:5070/email/list";
        }
        catch (Exception ex)
        {
            _consecutiveFailures++;
            LastError = ex.Message;
            throw;
        }
    }
}
