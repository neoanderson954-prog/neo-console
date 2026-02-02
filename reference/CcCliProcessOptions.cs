using System.Runtime.InteropServices;

namespace Zerox.Ai.Domain.Options;

/// <summary>
/// Configuration options for CC-CLI process (BB7).
/// </summary>
public class CcCliProcessOptions
{
    public const string Section = "ZeroxAi:CcCli";

    /// <summary>
    /// Path to claude CLI executable.
    /// Default: "claude" (assumes in PATH).
    /// On Windows, automatically resolves to "claude.cmd" if needed.
    /// </summary>
    public string CcCliPath { get; set; } = "claude";

    /// <summary>
    /// Base URL for MCP server (BB-W1 endpoints).
    /// Example: "http://localhost:5200/mcp".
    /// </summary>
    public string BaseUrl { get; set; } = string.Empty;

    /// <summary>
    /// JWT token for Authorization header.
    /// </summary>
    public string JwtToken { get; set; } = string.Empty;

    /// <summary>
    /// Deadman timer timeout in minutes.
    /// Default: 15 minutes.
    /// </summary>
    public double DeadmanTimeoutMinutes { get; set; } = 15;

    /// <summary>
    /// Model to use (e.g., "sonnet", "opus", "haiku").
    /// Default: "sonnet" (cheaper, sufficient for editing).
    /// </summary>
    public string Model { get; set; } = "sonnet";

    /// <summary>
    /// Whether to disable MCP servers in .mcp.json.
    /// Set to true in tests to avoid connection delays.
    /// Default: false (MCP servers enabled).
    /// </summary>
    public bool DisableMcpServers { get; set; } = false;

    /// <summary>
    /// Base folder for temporary CC-CLI session folders.
    /// Default: null (uses Path.GetTempPath() which is cross-platform).
    /// Windows: C:\Users\{user}\AppData\Local\Temp\
    /// Linux: /tmp/
    /// </summary>
    public string? TempFolderBase { get; set; }

    /// <summary>
    /// Gets the temp folder path for a specific chat session.
    /// Cross-platform: uses Path.GetTempPath() if TempFolderBase is not set.
    /// </summary>
    public string GetTempFolder(Guid chatId)
    {
        var basePath = string.IsNullOrEmpty(TempFolderBase)
            ? Path.GetTempPath()
            : TempFolderBase;
        return Path.Combine(basePath, $"cc-cli-{chatId}");
    }

    /// <summary>
    /// Gets the resolved executable path for the CC-CLI.
    /// On Windows: resolves "claude" to "claude.cmd" if not already absolute.
    /// On Linux: returns CcCliPath as-is.
    /// </summary>
    public string GetResolvedCcCliPath()
    {
        // If it's already an absolute path, return as-is
        if (Path.IsPathRooted(CcCliPath))
            return CcCliPath;

        // On Windows, Process.Start doesn't resolve .cmd files automatically
        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            // If user already specified extension, use as-is
            if (CcCliPath.EndsWith(".cmd", StringComparison.OrdinalIgnoreCase) ||
                CcCliPath.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ||
                CcCliPath.EndsWith(".bat", StringComparison.OrdinalIgnoreCase))
            {
                return CcCliPath;
            }

            // Try to find the .cmd version in PATH
            var pathEnv = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
            var pathDirs = pathEnv.Split(Path.PathSeparator);

            foreach (var dir in pathDirs)
            {
                var cmdPath = Path.Combine(dir, CcCliPath + ".cmd");
                if (File.Exists(cmdPath))
                    return cmdPath;

                var exePath = Path.Combine(dir, CcCliPath + ".exe");
                if (File.Exists(exePath))
                    return exePath;
            }

            // Fallback: try .cmd extension (npm installs use .cmd on Windows)
            return CcCliPath + ".cmd";
        }

        // Linux/macOS: return as-is
        return CcCliPath;
    }

    public void Validate()
    {
        // Only validate BaseUrl if it's been set (not empty/whitespace)
        // This allows backward compatibility where BaseUrl is set via DI/manual registration
        if (!string.IsNullOrWhiteSpace(BaseUrl))
        {
            if (!Uri.TryCreate(BaseUrl, UriKind.Absolute, out _))
                throw new InvalidOperationException("CcCliProcessOptions.BaseUrl must be a valid URL");
        }
    }
}
