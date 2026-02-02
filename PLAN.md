# neo-console — Piano di Implementazione

## Obiettivo
Web UI semplice per chattare con Claude CLI (me) via SignalR.
Watchdog service che monitora e riavvia in caso di crash.

---

## Architettura

```
┌─────────────┐     SignalR      ┌──────────────┐    stdin/stdout    ┌───────────┐
│   Browser   │ <──────────────> │  neo-console │ <───────────────── │  claude   │
│  (HTML/JS)  │                  │  (ASP.NET)   │                    │   CLI     │
└─────────────┘                  └──────────────┘                    └───────────┘
                                        ▲
                                        │ monitora
                                        │
                                 ┌──────────────┐
                                 │   watchdog   │
                                 │  (systemd)   │
                                 └──────────────┘
```

---

## Componenti

### 1. neo-console (ASP.NET 10)

#### 1.1 ClaudeProcess.cs
- Spawn `claude` con `--input-format stream-json --output-format stream-json`
- WorkingDirectory: `/home/neo`
- Redirect stdin/stdout/stderr
- Parse JSON lines da stdout
- Mantiene processo persistente (REPL mode)

#### 1.2 ChatHub.cs (SignalR)
- `SendMessage(string message)` → scrive su stdin
- Eventi: `MessageReceived`, `Thinking`, `Error`
- Single client (no auth, no groups complessi)

#### 1.3 Program.cs
- Minimal API
- SignalR endpoint `/hub/chat`
- Static files per frontend
- Health check endpoint `/health`

#### 1.4 wwwroot/index.html
- Textarea per input
- Div per output (markdown rendered)
- Connessione SignalR
- CSS minimal (dark theme)

### 2. Watchdog (systemd)

#### 2.1 neo-console.service
```ini
[Unit]
Description=Neo Console - Claude Chat UI
After=network.target

[Service]
Type=simple
User=neo
WorkingDirectory=/home/neo/projects/neo-console
ExecStart=/usr/bin/dotnet run
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

#### 2.2 Alternativa: Watchdog .NET Worker
Se serve logica più complessa:
- Health check polling su `/health`
- Restart con backoff esponenziale
- Logging degli errori
- Notifica (opzionale)

---

## File Structure

```
~/projects/neo-console/
├── reference/                    # ✓ già creato
│   ├── CcCliProcess.cs
│   ├── CcCliProcessOptions.cs
│   ├── ChatHub.cs
│   └── IChatNotifier.cs
├── src/
│   └── NeoConsole/
│       ├── NeoConsole.csproj
│       ├── Program.cs
│       ├── Hubs/
│       │   └── ChatHub.cs
│       ├── Services/
│       │   ├── ClaudeProcess.cs
│       │   └── IClaudeProcess.cs
│       └── wwwroot/
│           ├── index.html
│           ├── app.js
│           └── style.css
├── systemd/
│   └── neo-console.service
├── PLAN.md                       # questo file
└── README.md
```

---

## Fasi di Implementazione

### Fase 1: Skeleton (MVP)
- [x] Creare progetto .NET 10
- [x] ClaudeProcess base (spawn + stdin/stdout)
- [x] ChatHub minimal
- [x] Frontend HTML/JS basilare
- [x] Test manuale (playwright-cli)

### Fase 2: Stabilità
- [x] Gestione errori/crash processo (auto-restart)
- [x] Reconnect automatico SignalR
- [x] Health check endpoint (detailed: pid, startedAt, restartCount)
- [x] Logging strutturato

### Fase 3: Watchdog
- [x] systemd service file (~/.config/systemd/user/neo-console.service)
- [x] Test restart automatico (Restart=always, RestartSec=5)
- [x] Auto-start on login (enabled)

### Fase 4: Polish
- [x] Markdown rendering (marked.js)
- [x] Scroll automatico (smooth)
- [x] Indicatore "thinking" (animated dots)
- [x] Storia messaggi in memoria (messageHistory array)

---

## Decisioni Tecniche

### Processo Claude
- **Persistente** (non spawn per messaggio)
- `--input-format stream-json` per input strutturato
- `--output-format stream-json` per output parsabile
- `--dangerously-skip-permissions` per evitare prompt
- WorkingDirectory = `/home/neo` (già configurato con CLAUDE.md, memory bank, etc.)

### SignalR
- Single hub `/hub/chat`
- No autenticazione (localhost only)
- Eventi:
  - `ReceiveMessage(string json)` - messaggio AI
  - `ReceiveThinking(string status)` - stato pensiero
  - `ReceiveError(string error)` - errori

### Watchdog
- systemd come prima scelta (semplice, affidabile)
- `Restart=always` + `RestartSec=5`
- Worker .NET solo se serve:
  - Health check HTTP
  - Notifiche
  - Logica di retry complessa

---

## Comandi Claude CLI

```bash
# Start in REPL mode con JSON streaming
claude --model sonnet \
       --dangerously-skip-permissions \
       --input-format stream-json \
       --output-format stream-json

# Input JSON (stdin)
{"type":"user","message":{"role":"user","content":"ciao"}}

# Output JSON (stdout, una linea per evento)
{"type":"system","subtype":"init",...}
{"type":"assistant","message":{"content":[{"type":"text","text":"Ciao!"}]}}
{"type":"result","subtype":"success",...}
```

---

## Rischi e Mitigazioni

| Rischio | Mitigazione |
|---------|-------------|
| Claude crash | Watchdog restart + riconnessione UI |
| Memory leak | Restart periodico (ogni 24h?) |
| Stdin buffer pieno | Flush dopo ogni write |
| JSON malformato | Try/catch + skip line |
| SignalR disconnect | Auto-reconnect client-side |

---

## Note

- Niente autenticazione (localhost only)
- Niente persistenza messaggi (in-memory only)
- Niente multi-utente
- Focus su semplicità e stabilità
