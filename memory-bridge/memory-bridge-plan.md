§MBEL:5.0

# MemoryBridge::DevelopmentPlan{v2}

## [Goal]
@purpose::neo-console{Q+A}→chromaDB{embeddings+DNA}→recall{viaMCP}
@flow::wrapper{captureQ+A}→HTTP→cortex{embed+DNA+store}→MCP{query+dream}

## [Architecture]
```
neo-console (C#)                       memory-bridge (Python)
     │                                       │
     ├─ ClaudeProcess.cs                     ├─ FastMCP server (stdio)
     │   ├─ captures user Q                  │   ├─ tool: memory_query(q,n)
     │   ├─ accumulates assistant A          │   ├─ tool: memory_stats()
     │   ├─ captures stats/result            │   ├─ tool: memory_dream()
     │   └─ on turn complete:                │   └─ tool: memory_ingest(turn)
     │       POST localhost:5071/ingest      │
     │                                       ├─ HTTP server (uvicorn :5071)
     │                                       │   └─ POST /ingest → cortex.ingest_json()
     │                                       │   └─ GET  /health → stats
     │                                       │
     └─ Claude uses MCP tools ←──────────── └─ ConversationCortex (existing)
        memory_query("crash fix")                 ├─ chromaDB + embeddings
        memory_stats()                            ├─ groq DNA compiler
        memory_dream()                            └─ dream cycles + synaptic links
```

## [TwoChannels]
!automatic::wrapper→POST /ingest→cortex{ogni turno Q+A→salvato senza intervento}
!voluntary::Claude→MCP tools→cortex{query+stats+dream quando vuole}
@separation::ingest=automatico | recall=volontario

## [Phases]

### Phase1::ConversationIngest ✓DONE
@what::ricevere+salvare coppie Q+A in chromaDB
@files::src/conversation_cortex.py✓ + src/groq_compiler.py✓
@status::tested+working{chromaDB+embeddings+groqDNA+dreamCycles}

### Phase2::MCPServer+HTTPEndpoint
@what::FastMCP server con tools + HTTP endpoint per wrapper
@files::
  - src/memory_bridge_server.py{new}→FastMCP+uvicorn
@tasks::
  1→pip install fastmcp uvicorn
  2→FastMCP server con 4 tools{memory_query, memory_stats, memory_dream, memory_ingest}
  3→HTTP endpoint POST /ingest{riceve JSON dal wrapper C#}
  4→HTTP endpoint GET /health{stats del cortex}
  5→entrambi usano stessa istanza ConversationCortex
  6→test::MCP tools via fastmcp CLI
  7→test::HTTP endpoint via curl

### Phase3::WrapperHook{C#}
@what::modificare ClaudeProcess.cs per catturare+inviare Q+A
@files::
  - src/NeoConsole/Services/ClaudeProcess.cs{modify}
@tasks::
  1→accumulare user question{da SendMessageAsync}
  2→accumulare assistant answer{da HandleAssistantMessage, concatena text blocks}
  3→accumulare tools_used{da HandleToolUse}
  4→on result message{tipo "result"}→comporre ConversationTurn JSON
  5→HttpClient.PostAsync("http://localhost:5071/ingest", turnJson)
  6→fire-and-forget{¬bloccare il flusso principale}
  7→graceful fail{se cortex non risponde→log+skip, ¬crash}
  8→test::send message via neo-console→verify appare in chromaDB

### Phase4::SystemdService
@what::memory-bridge come servizio persistente
@tasks::
  1→systemd unit file{memory-bridge.service}
  2→auto-start con neo-console
  3→periodic dream cycles{ogni N ore}

### Phase5::WakeReload
@what::on session start→query cortex→inject relevant memories in MB
@tasks::
  1→recall_for_context(currentFocus)→top memories
  2→format as MBEL→inject in activeContext or dedicated section
  3→hook in CLAUDE.md or session start

## [JSON Schema::ConversationTurn]
```json
{
  "session_id": "uuid",
  "timestamp": 1234567890.123,
  "turn_number": 1,
  "question": {
    "text": "user message raw",
    "source": "neo-console"
  },
  "answer": {
    "text": "assistant response full",
    "tools_used": ["Read", "Bash"]
  },
  "stats": {
    "input_tokens": 1234,
    "output_tokens": 567,
    "cost_usd": 0.01,
    "duration_ms": 5000
  },
  "model": "opus"
}
```

## [Priorities]
!P2::next{MCP server+HTTP=ponte tra i due mondi}
!P3::then{wrapper hook=flusso automatico}
?P4::nice{systemd=persistenza}
?P5::later{wake reload=full loop}

## [Dependencies]
@existing::
  - conversation_cortex.py✓{ingest+recall+dream+stats}
  - groq_compiler.py✓{DNA compilation via Groq API}
  - chromadb✓ + sentence-transformers✓
@new::
  - fastmcp{pip install fastmcp}
  - uvicorn{pip install uvicorn}
  - httpx or aiohttp{per async HTTP in fastmcp}
@csharp::
  - HttpClient{già disponibile in ASP.NET}
  - ¬nuovi pacchetti necessari

## [Constraints]
!noOllama→useGroq{already tested+working}
!embeddings→local{sentence-transformers}→¬sendDataToAPI
!wrapper→fire-and-forget{¬bloccare main loop}
!cortex down→graceful skip{¬crash neo-console}
!MCP→stdio{standard Claude MCP protocol}
!HTTP→localhost only{¬esporre su rete}
