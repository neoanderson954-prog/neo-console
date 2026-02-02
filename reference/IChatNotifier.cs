namespace Zerox.Ai.Core.Contracts;

/// <summary>
/// Chat event notifier - broadcasts AI events via SignalR.
/// </summary>
public interface IChatNotifier
{
    Task OnUserMessageReceivedAsync(IMessageContext context, string message);
    Task OnAiMessageReceivedAsync(IMessageContext context, string message);
    Task OnAiThinkingAsync(IMessageContext context, AiThinkingType thinkingType);
    Task OnChatClosedAsync(IMessageContext context);
}

/// <summary>
/// AI thinking/processing state.
/// </summary>
public enum AiThinkingType
{
    Idle,
    ThinkingUserRequest,
    ThinkingSystemNotification,
    ToolUse,
    WritingResponse
}
