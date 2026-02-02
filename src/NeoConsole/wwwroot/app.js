const connection = new signalR.HubConnectionBuilder()
    .withUrl("/hub/chat")
    .withAutomaticReconnect([0, 1000, 2000, 5000, 10000, 30000])
    .build();

const messagesEl = document.getElementById("messages");
const input = document.getElementById("input");
const form = document.getElementById("chat-form");
const thinking = document.getElementById("thinking");
const thinkingText = document.getElementById("thinking-text");
const connectionStatus = document.getElementById("connection-status");
const processInfo = document.getElementById("process-info");
const statsEl = document.getElementById("stats");
const toolsList = document.getElementById("tools-list");
const modelSelect = document.getElementById("model-select");

const messageHistory = [];
const toolsHistory = [];
let totalCost = 0;
let totalTokens = 0;
let currentStreamingMessage = null;
let currentStreamingText = "";
let currentThinkingMessage = null;
let currentThinkingText = "";

marked.setOptions({ breaks: true, gfm: true });

function addMessage(content, type, render = true) {
    const msg = { content, type, timestamp: Date.now() };
    messageHistory.push(msg);

    const div = document.createElement("div");
    div.className = `message ${type}`;

    if (type === "ai" && render) {
        div.innerHTML = marked.parse(content);
    } else {
        div.textContent = content;
    }

    messagesEl.appendChild(div);
    scrollToBottom();
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        messagesEl.scrollTop = messagesEl.scrollHeight;
    });
}

function setConnectionStatus(text, type) {
    connectionStatus.textContent = text;
    connectionStatus.className = `status-${type}`;
}

function showThinking(text = "Thinking...") {
    thinkingText.textContent = text;
    thinking.classList.remove("hidden");
    scrollToBottom();
}

function hideThinking() {
    thinking.classList.add("hidden");
}

function updateStats(stats) {
    totalCost += stats.costUsd || 0;
    totalTokens += (stats.inputTokens || 0) + (stats.outputTokens || 0);

    statsEl.innerHTML = `
        <span class="stat-item">Tokens: ${totalTokens.toLocaleString()}</span>
        <span class="stat-item">Cost: $${totalCost.toFixed(4)}</span>
        <span class="stat-item">${stats.durationMs || 0}ms</span>
    `;
}

const toolElements = new Map();

function addToolUse(tool) {
    toolsHistory.push({ ...tool, timestamp: Date.now() });

    const div = document.createElement("div");
    div.className = "tool-item";
    div.dataset.toolId = tool.id;

    let inputPreview = "";
    try {
        const parsed = JSON.parse(tool.input);
        if (parsed.command) {
            inputPreview = parsed.command.substring(0, 100);
        } else if (parsed.pattern) {
            inputPreview = `pattern: ${parsed.pattern}`;
        } else if (parsed.file_path) {
            inputPreview = parsed.file_path;
        } else if (parsed.query) {
            inputPreview = parsed.query.substring(0, 80);
        } else {
            inputPreview = tool.input.substring(0, 80);
        }
    } catch {
        inputPreview = (tool.input || "").substring(0, 80);
    }

    div.innerHTML = `
        <div class="tool-header" onclick="toggleToolOutput('${tool.id}')">
            <div class="tool-name">${escapeHtml(tool.name)}</div>
            <div class="tool-input">${escapeHtml(inputPreview)}${inputPreview.length >= 80 ? '...' : ''}</div>
            <div class="tool-time">${new Date().toLocaleTimeString()}</div>
        </div>
        <div class="tool-output" id="output-${tool.id}" style="display:none;"></div>
    `;

    toolElements.set(tool.id, div);
    toolsList.insertBefore(div, toolsList.firstChild);
    while (toolsList.children.length > 50) {
        const last = toolsList.lastChild;
        if (last.dataset.toolId) toolElements.delete(last.dataset.toolId);
        toolsList.removeChild(last);
    }
}

function toggleToolOutput(toolId) {
    const output = document.getElementById(`output-${toolId}`);
    if (output) {
        output.style.display = output.style.display === 'none' ? 'block' : 'none';
    }
}

window.toggleToolOutput = toggleToolOutput;

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function updateProcessInfo() {
    try {
        const res = await fetch('/health');
        const data = await res.json();
        if (data.claude) {
            const uptime = data.claude.startedAt
                ? Math.floor((Date.now() - new Date(data.claude.startedAt).getTime()) / 1000)
                : 0;
            processInfo.innerHTML = `
                <span class="info-item">PID: ${data.claude.pid || '-'}</span>
                <span class="info-item">Up: ${formatUptime(uptime)}</span>
                <span class="info-item">↻${data.claude.restartCount}</span>
            `;
            if (data.claude.model && modelSelect.value !== data.claude.model) {
                modelSelect.value = data.claude.model;
            }
        }
    } catch (e) {
        processInfo.textContent = '';
    }
}

function formatUptime(seconds) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h${Math.floor((seconds % 3600) / 60)}m`;
}

async function sendMessage(message) {
    if (!message || connection.state !== signalR.HubConnectionState.Connected) return;

    addMessage(message, "user", false);
    input.value = "";
    showThinking();

    try {
        await connection.invoke("SendMessage", message);
    } catch (err) {
        hideThinking();
        addMessage(`Send error: ${err}`, "error", false);
    }
}

// SignalR events
connection.on("ReceiveMessage", (text) => {
    hideThinking();
    // If we were streaming, finalize that instead of adding duplicate
    if (currentStreamingMessage) {
        finalizeStreamingMessage();
        return; // Don't add duplicate
    }
    addMessage(text, "ai");
});

connection.on("ReceiveThinkingDelta", (delta) => {
    hideThinking();
    if (!currentThinkingMessage) {
        currentThinkingText = "";
        const div = document.createElement("div");
        div.className = "message thinking-content";
        messagesEl.appendChild(div);
        currentThinkingMessage = div;
    }
    currentThinkingText += delta;
    currentThinkingMessage.textContent = currentThinkingText;
    scrollToBottom();
});

connection.on("ReceiveTextDelta", (delta) => {
    hideThinking();
    // Finalize thinking message when text starts
    if (currentThinkingMessage) {
        currentThinkingMessage = null;
        currentThinkingText = "";
    }
    if (!currentStreamingMessage) {
        currentStreamingText = "";
        const div = document.createElement("div");
        div.className = "message ai streaming";
        messagesEl.appendChild(div);
        currentStreamingMessage = div;
    }
    currentStreamingText += delta;
    currentStreamingMessage.textContent = currentStreamingText;
    scrollToBottom();
});

connection.on("ReceiveThinking", (text) => {
    showThinking(text);
});

connection.on("ReceiveToolUse", (tool) => {
    addToolUse(tool);
    showThinking(`Using: ${tool.name}`);
});

connection.on("ReceiveToolResult", (result) => {
    const outputEl = document.getElementById(`output-${result.id}`);
    if (outputEl) {
        outputEl.textContent = result.output || '(no output)';
        // Auto-expand if output is small
        if ((result.output || '').length < 500) {
            outputEl.style.display = 'block';
        }
    }
});

connection.on("ReceiveStats", (stats) => {
    updateStats(stats);
});

connection.on("ReceiveError", (error) => {
    hideThinking();
    addMessage(`Error: ${error}`, "error", false);
});

connection.on("ReceiveComplete", () => {
    hideThinking();
    finalizeStreamingMessage();
});

function finalizeStreamingMessage() {
    if (currentStreamingMessage && currentStreamingText) {
        // Re-render with markdown
        currentStreamingMessage.innerHTML = marked.parse(currentStreamingText);
        currentStreamingMessage.classList.remove("streaming");
        messageHistory.push({ content: currentStreamingText, type: "ai", timestamp: Date.now() });
    }
    currentStreamingMessage = null;
    currentStreamingText = "";
}

// Form submit
form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (message) await sendMessage(message);
});

input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.dispatchEvent(new Event("submit"));
    }
});

// Quick actions
document.querySelectorAll('.action-btn[data-cmd]').forEach(btn => {
    btn.addEventListener('click', () => {
        const cmd = btn.dataset.cmd;
        if (cmd) sendMessage(cmd);
    });
});

document.getElementById('restart-btn').addEventListener('click', async () => {
    if (!confirm('Restart Claude process?')) return;
    try {
        await fetch('/restart', { method: 'POST' });
        addMessage('Process restarted', 'system', false);
        updateProcessInfo();
    } catch (e) {
        addMessage(`Restart failed: ${e}`, 'error', false);
    }
});

modelSelect.addEventListener('change', async () => {
    const model = modelSelect.value;
    if (!confirm(`Switch to ${model}? This will restart Claude.`)) {
        updateProcessInfo();
        return;
    }
    modelSelect.disabled = true;
    try {
        const res = await fetch(`/model/${model}`, { method: 'POST' });
        if (res.ok) {
            addMessage(`Model changed to ${model}`, 'system', false);
        } else {
            const err = await res.json();
            addMessage(`Model change failed: ${err.error}`, 'error', false);
        }
        updateProcessInfo();
    } catch (e) {
        addMessage(`Model change failed: ${e}`, 'error', false);
    } finally {
        modelSelect.disabled = false;
    }
});

// Connection
async function startConnection() {
    try {
        await connection.start();
        setConnectionStatus("Connected", "success");
        input.disabled = false;
        updateProcessInfo();
    } catch (err) {
        setConnectionStatus("Disconnected", "error");
        input.disabled = true;
        setTimeout(startConnection, 5000);
    }
}

connection.onreconnecting(() => {
    setConnectionStatus("Reconnecting...", "warning");
    input.disabled = true;
});

connection.onreconnected(() => {
    setConnectionStatus("Connected", "success");
    input.disabled = false;
    updateProcessInfo();
});

connection.onclose(() => {
    setConnectionStatus("Disconnected", "error");
    input.disabled = true;
    setTimeout(startConnection, 5000);
});

// Exports
window.getMessageHistory = () => messageHistory;
window.getToolsHistory = () => toolsHistory;

// Init
input.disabled = true;
startConnection();
setInterval(updateProcessInfo, 10000);
