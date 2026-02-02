using System.Security.Claims;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using Zerox.Ai.Core.Contracts;

namespace Zerox.Ai.Api.Hubs;

/// <summary>
/// BB5: SignalR Chat Hub - Real-time chat events.
/// Pure infrastructure with SendMessage integration to BB4.
/// </summary>
public class ChatHub : Hub
{
    private readonly IChatService _chatService;
    private readonly ILogger<ChatHub> _logger;

    public ChatHub(IChatService chatService, ILogger<ChatHub> logger)
    {
        logger.LogDebug("BB5 ChatHub constructor START");
        _chatService = chatService;
        _logger = logger;
        logger.LogDebug("BB5 ChatHub constructor DONE");
    }

    /// <summary>
    /// NEW: Client joins user-based group on login (ONCE).
    /// Solves race condition: client is in group BEFORE any snapshot operations.
    /// Group format: "user:{userId}" where userId extracted from JWT token.
    /// </summary>
    /// <param name="userId">Optional user ID for testing. If null, extracts from JWT token.</param>
    public async Task JoinUserGroup(string? userId = null)
    {
        var actualUserId = userId ??
                           Context.User?.FindFirst(ClaimTypes.NameIdentifier)?.Value ??
                           Context.User?.FindFirst("sub")?.Value ??
                           throw new HubException("User ID not found in JWT token");

        var groupName = $"user:{actualUserId}";
        await Groups.AddToGroupAsync(Context.ConnectionId, groupName);

        _logger.LogDebug(
            "ChatHub: Client {ConnectionId} joined GROUP={GroupName} with UserId={UserId}",
            Context.ConnectionId,
            groupName,
            actualUserId
        );
    }

    /// <summary>
    /// DEPRECATED: Client joins chat group to receive messages.
    /// Grouping strategy: Group(chatId) where chatId = snapshotId.
    /// USE JoinUserGroup() instead - this is kept for backward compatibility only.
    /// </summary>
    public async Task JoinChatGroup(Guid chatId)
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, chatId.ToString());
    }

    /// <summary>
    /// Client leaves chat group.
    /// </summary>
    public async Task LeaveChatGroup(Guid chatId)
    {
        await Groups.RemoveFromGroupAsync(Context.ConnectionId, chatId.ToString());
    }

    /// <summary>
    /// Client sends message to AI.
    /// This method calls BB4 (IChatService) directly.
    /// BB4 will orchestrate the message to BB7 → CC-CLI.
    /// </summary>
    public async Task SendMessage(Guid chatId, string userId, string message)
    {
        var context = new MessageContext
        {
            SnapshotId = chatId,
            ActorId = $"signalr-{Context.ConnectionId}",
            UserId = userId,
            MessageType = MessageType.User
        };

        await _chatService.SendMessageAsync(context, message);
    }

    /// <summary>
    /// Auto-cleanup on disconnect.
    /// </summary>
    public override Task OnDisconnectedAsync(Exception? exception)
    {
        return base.OnDisconnectedAsync(exception);
    }
}

/// <summary>
/// Client-side interface for type-safe SignalR events.
/// Server→Client events (broadcast to group).
/// </summary>
public interface IChatHubClient
{
    /// <summary>
    /// User message received (human typed).
    /// </summary>
    Task UserMessageReceived(string message);

    /// <summary>
    /// AI message received (CC-CLI responded).
    /// </summary>
    Task AiMessageReceived(string message);

    /// <summary>
    /// AI thinking/processing status changed.
    /// </summary>
    Task AiThinking(AiThinkingType thinkingType);

    /// <summary>
    /// Chat session closed (edit confirmed or cancelled).
    /// </summary>
    Task ChatClosed();
}

/// <summary>
/// Simple IMessageContext implementation for ChatHub.
/// </summary>
internal class MessageContext : IMessageContext
{
    public Guid SnapshotId { get; set; }
    public string ActorId { get; set; } = string.Empty;
    public string UserId { get; set; } = string.Empty;
    public MessageType MessageType { get; set; } = MessageType.User;
}
