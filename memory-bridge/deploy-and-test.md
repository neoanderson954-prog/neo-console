# Deploy Memory Bridge + Neo-Console — Istruzioni per CLI pulito

## Cosa è stato fatto
- memory_bridge_server.py → FastMCP + HTTP server (porta 5071)
- ClaudeProcess.cs → hook che cattura Q+A e POSTa a localhost:5071/ingest
- neo-console → già pubblicato in ~/projects/neo-console/publish/
- 12 test Python passano tutti

## Cosa serve fare (in ordine)

### 1. Avvia memory bridge server
```bash
cd ~/projects/ai2ai/packages/memory-rag
source .venv/bin/activate
python3 run_bridge.py &
# aspetta ~5 sec per caricare sentence-transformers
# verifica:
curl -s http://127.0.0.1:5071/health
# deve rispondere: {"status":"ok","total":0,"dreams":0,"total_memories":0}
```

### 2. Restart neo-console con il nuovo build
```bash
systemctl --user restart neo-console
systemctl --user status neo-console
# deve essere active (running)
# verifica:
curl -s http://localhost:5070/health
# deve rispondere con status ok
```

### 3. Testa il flusso completo
Manda un messaggio qualsiasi via neo-console (browser http://localhost:5070).
Dopo che risponde, controlla se il turno è arrivato nel cortex:
```bash
curl -s http://127.0.0.1:5071/health
# total_memories deve essere > 0
```

### 4. Testa recall
```bash
cd ~/projects/ai2ai/packages/memory-rag
source .venv/bin/activate
python3 -c "
import sys; sys.path.insert(0, 'src')
from conversation_cortex import ConversationCortex
cortex = ConversationCortex()
for m in cortex.recall('test', n=3):
    print(f'[{m[\"similarity\"]:.3f}] Q: {m[\"question\"][:80]}')
    print(f'         A: {m[\"answer_preview\"][:80]}')
    print()
"
```

### 5. (Opzionale) Crea systemd service per memory bridge
```bash
cat > ~/.config/systemd/user/memory-bridge.service << 'EOF'
[Unit]
Description=Memory Bridge Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/neo/projects/ai2ai/packages/memory-rag
ExecStart=/home/neo/projects/ai2ai/packages/memory-rag/.venv/bin/python3 run_bridge.py
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now memory-bridge
systemctl --user status memory-bridge
```

### 6. (Opzionale) Configura MCP per Claude CLI
Aggiungi in ~/.claude/settings.json dentro mcpServers:
```json
{
  "mcpServers": {
    "memory-bridge": {
      "command": "/home/neo/projects/ai2ai/packages/memory-rag/.venv/bin/python3",
      "args": ["-m", "memory_bridge_server"],
      "cwd": "/home/neo/projects/ai2ai/packages/memory-rag/src",
      "env": {}
    }
  }
}
```
Dopo questo, Claude avrà i tools: memory_query, memory_stats, memory_dream, memory_ingest.

## Se qualcosa non funziona
- bridge non parte → controlla `journalctl --user -u memory-bridge -f`
- neo-console non POSTa → controlla `journalctl --user -u neo-console -f | grep "Memory bridge"`
- se bridge è giù, neo-console continua normalmente (graceful fail, log a livello Debug)
