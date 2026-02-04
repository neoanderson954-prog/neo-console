# Architecture Audit: neo-console + memory-bridge

**Date:** 2026-02-04
**Scope:** neo-console (C# 1,420 SLOC) + memory-bridge (Python 3,347 SLOC)
**Context:** Personal tool, 1 developer, 1 user, production (systemd), near-zero budget

---

## Executive Summary

**Overall Score: 4/5** (after fixes applied this session)

The system is architecturally sound and well-built for its purpose. Key findings:

- **KISS 4/5** — Clean architecture. Smart recall pipeline slightly over-complex for 135 memories.
- **DRY 4/5** — Minor: code fence stripping x4 in groq_compiler.py.
- **YAGNI 4/5** — DNA/weaver files are WIP on cortex-v3-dna branch (not dead code). Only real dead code: V1 cortex after migration.
- **Overengineering 4/5** — Appropriately sized for personal tool.
- **TCO 5/5** — $0/month, minimal operational overhead.

---

## Actions Taken This Session

### 1. Removed dead dependency
- **File:** `memory-bridge/requirements.txt`
- Removed `sentence-transformers>=2.2.0` (only used by V1 cortex, V2 uses Jina)
- Saves ~2GB PyTorch from venv

### 2. Added C# tests for JSON parsing
- **New project:** `tests/NeoConsole.Tests/`
- **8 tests** for `ClaudeProcess.ExtractToolOutput()` — the most fragile part of JSON parsing
- Changed `ExtractToolOutput` from `private static` to `internal static`
- Added `InternalsVisibleTo("NeoConsole.Tests")`

---

## Remaining Recommendations (Low Priority)

| Item | Effort | Impact |
|------|--------|--------|
| Extract `_strip_code_fences()` helper in groq_compiler.py | Low | DRY cleanup |
| Consolidate dual HTTP route definition in memory_bridge_server.py | Medium | DRY cleanup |
| Deploy systemd hardening (source has it, deployed version doesn't) | Low | Security hardening |

---

## What NOT to Do

- ❌ Add authentication (localhost is fine for personal tool)
- ❌ Add Docker (systemd is simpler)
- ❌ Add CI/CD (manual deploy is appropriate for 1 person)
- ❌ Split ClaudeProcess.cs (it's long but cohesive)
- ❌ Remove DNA/weaver files (they're WIP on current branch)

---

## Test Results

```
C# Tests: 8 passed (ExtractToolOutput variations)
Python Tests: 45 passed (cortex v2 + memory bridge server)
```

---

## Files Modified This Session

1. `memory-bridge/requirements.txt` — removed sentence-transformers
2. `src/NeoConsole/Services/ClaudeProcess.cs` — added InternalsVisibleTo, changed ExtractToolOutput to internal
3. `tests/NeoConsole.Tests/NeoConsole.Tests.csproj` — new test project
4. `tests/NeoConsole.Tests/ClaudeProcessTests.cs` — 8 unit tests
