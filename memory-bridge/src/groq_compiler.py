"""
Groq DNA Compiler - Replaces ollama-based MemomeCompiler
Uses llama-3.3-70b-versatile via Groq API for DNA compilation
"""

import json
import re
import os
from typing import Optional
from memome_codex import parse_dna_sequence, ParsedDNA

# Default prompt - strict single-line DNA output
COMPILER_PROMPT = """You are a Memome Compiler. Convert text into exactly ONE dna_sequence.

STRICT FORMAT: (core_concept)::{E:X|T:X|C:X|S:X|F:X|Ψ:X|R:(a)⚔(b)}

Rules:
- core_concept = 1-3 words capturing the essence
- Exactly ONE sequence per text, on ONE line
- Each namespace appears exactly once
- E(emotion): JOY/SER/AWE/SAD/ANG/FEA
- T(temporal): STA/LIN/CYC/ERU/DEC
- C(complexity): SIM/MOD/DNS/ABS/SNG/SPR
- S(sensory): VIS/AUD/TAC/OLF/KIN
- F(frequency): Δ!/∞/══▶/≈≈
- Ψ(consciousness): ALR/DRM/MED/EMR
- R(relational): (concept1)⚔(concept2) for conflict, (concept1)⊕(concept2) for harmony

Output ONLY the single dna_sequence line. No explanation."""


def _load_api_key() -> str:
    """Load Groq API key from ~/.accounts"""
    accounts_path = os.path.expanduser("~/.accounts")
    with open(accounts_path) as f:
        for line in f:
            if line.startswith("groq:"):
                return line.strip().split(":", 1)[1]
    raise RuntimeError("Groq API key not found in ~/.accounts")


def compile_to_dna(text: str, api_key: Optional[str] = None) -> str:
    """Compile text into a DNA sequence via Groq API.

    Returns a valid DNA string like (concept)::{E:X|T:X|...}
    Falls back to a simple default on any failure.
    """
    if api_key is None:
        api_key = _load_api_key()

    import requests as _requests

    try:
        resp = _requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "user", "content": f"{COMPILER_PROMPT}\n\nText: \"{text}\""}
                ],
                "temperature": 0.1,
                "max_tokens": 100
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        raw = data["choices"][0]["message"]["content"].strip()
        # Take only first line
        raw = raw.split("\n")[0].strip()

        # Try to fix format if core_concept uses :: instead of parentheses
        # e.g. "Error::Crash::{E:ANG|...}" -> "(Error,Crash)::{E:ANG|...}"
        dna_match = re.search(r'\{([^}]+)\}', raw)
        concept_match = re.search(r'^(.+?)::\{', raw)

        if dna_match and concept_match:
            concept_raw = concept_match.group(1).strip()
            codons = dna_match.group(1)

            # Normalize concept to (x,y) format
            if not concept_raw.startswith("("):
                parts = re.split(r'[:, ]+', concept_raw)
                parts = [p.strip().lower() for p in parts if p.strip()]
                concept_raw = f"({','.join(parts[:3])})"

            dna = f"{concept_raw}::{{{codons}}}"

            # Validate it parses
            parse_dna_sequence(dna)
            return dna

    except Exception as e:
        pass

    # Fallback
    words = text.lower().split()
    concepts = [w for w in words if len(w) > 4][:2]
    concept = f"({','.join(concepts)})" if concepts else "(memory)"
    return f"{concept}::{{E:SER|T:LIN|C:MOD|S:VIS|F:══▶|Ψ:ALR}}"


MBEL_GRAMMAR = """MBEL Grammar:
- Temporal: > = past/did, @ = present/is, ? = future/todo, ~ = approximate
- State: done = checkmark, failed = X, ! = important/critical
- Relation: :: = defines/is, -> = leads_to/causes, <- = because/from, + = and/with, - = without
- Structure: [] = section, {} = metadata, () = note
- Logic: & = AND, not-sign = NOT
- CamelCase for multi-word, no articles (a/the/an), operators only no punctuation"""

MBEL_EXAMPLES = """Examples:

Input: "Q: come fixare il crash? A: reader moriva per InvalidOperationException, catchavamo solo JsonException. Fix: catch Exception nel inner loop."
Output:
!bug::stdoutReaderCrash{InvalidOperationException}
<-cause::toolUseResult{String not Object}->TryGetProperty->crash
>fix::catchAll{Exception not JsonException}+checkValueKind{beforeTryGetProperty}

Input: "Q: ciao come stai? A: tutto bene, sono qui"
Output:
@status::ok

Input: "Q: come funziona il deploy? A: dotnet publish poi systemctl restart neo-console"
Output:
@deploy::dotnetPublish->systemctlRestart{neo-console}
@port::5070 @service::systemd"""

MBEL_PROMPT = f"""Compress this Q+A into MBEL notation (3-5 lines max, NO explanation, ONLY MBEL output).

{MBEL_GRAMMAR}
- Capture: what happened + why + fix/result

{MBEL_EXAMPLES}

Q+A to compress:
"""

AGGREGATE_PROMPT = f"""You receive N memory recall results. Aggregate them into ONE compact MBEL block.

{MBEL_GRAMMAR}
- Deduplicate: merge overlapping info
- Prioritize: most relevant first
- Max 10 lines total for ALL memories combined
- Use [#N] prefix to mark different memories if needed
- NO explanation, ONLY MBEL output

{MBEL_EXAMPLES}

Memories to aggregate:
"""


def _call_groq(prompt: str, text: str, max_tokens: int = 250, api_key: Optional[str] = None, temperature: float = 0.1) -> str:
    """Call Groq API with given prompt+text."""
    if api_key is None:
        api_key = _load_api_key()

    import requests as _requests

    resp = _requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "user", "content": f"{prompt}\"{text}\""}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        },
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def compile_to_mbel(text: str, api_key: Optional[str] = None) -> str:
    """Compile Q+A text into MBEL compressed notation via Groq API.

    Returns 3-5 lines of MBEL. Falls back to a simple summary on failure.
    """
    try:
        raw = _call_groq(MBEL_PROMPT, text, max_tokens=250, api_key=api_key)
        lines = [l for l in raw.split("\n") if l.strip()][:5]
        return "\n".join(lines)
    except Exception:
        return text[:200] if len(text) > 200 else text


def aggregate_to_mbel(memories: list, api_key: Optional[str] = None) -> str:
    """Aggregate N memory recall results into one compact MBEL block.

    Takes list of dicts with 'question' and 'answer_preview' fields.
    Returns a single MBEL block (max ~10 lines). One groq call total.
    """
    if not memories:
        return "@recall::empty{noMemoriesFound}"

    # Build compact text from memories
    parts = []
    for i, mem in enumerate(memories, 1):
        q = mem.get("question", "")[:200]
        a = mem.get("answer_preview", "")[:300]
        if q or a:
            parts.append(f"[{i}] Q: {q}\nA: {a}")

    combined = "\n\n".join(parts)

    # Limit total input to avoid token overflow
    if len(combined) > 3000:
        combined = combined[:3000]

    try:
        raw = _call_groq(AGGREGATE_PROMPT, combined, max_tokens=400, api_key=api_key)
        lines = [l for l in raw.split("\n") if l.strip()][:10]
        return "\n".join(lines)
    except Exception:
        # Fallback: just return questions as MBEL-ish list
        fallback = []
        for mem in memories[:5]:
            q = mem.get("question", "")[:80]
            fallback.append(f"@recall::{q}")
        return "\n".join(fallback)


# --- V2: Noise Filter, Classification & Query Analysis ---

NOISE_FILTER_PROMPT = """You are a noise filter for a developer's memory system. This system stores conversation turns (Q+A) as long-term memories.

Your job: decide if the USER MESSAGE (question) leads to a conversation worth remembering, or if it is throwaway noise.

NOISE (skip) = messages that produce NO lasting knowledge:
- Pure greetings: "ciao", "hey", "hello", "buongiorno"
- Acknowledgments: "ok", "si", "grazie", "perfetto", "va bene"
- System commands: "/clear", "kill", "esci", "stop"
- Single words with no technical content

SIGNAL (keep) = messages that lead to real work or knowledge:
- Questions about code, bugs, architecture, tools
- Instructions to do something specific: "run the tests", "mostra i test", "fammi un riassunto"
- Directions for work: "continua su roba che abbiamo iniziato", "rpiam noise filter"
- Observations, decisions, opinions with substance
- Even short/informal messages IF they direct real work

KEY RULE: if the message is an instruction to DO something (even informal, even with typos), it is SIGNAL. The answer will contain the real work done.

Return ONLY: {"noise": true/false, "why": "2-3 words"}

Message: """


def is_noise_groq(question: str, api_key: Optional[str] = None) -> bool:
    """Ask Groq whether a message is noise or signal.

    Returns True if noise, False if signal. Defaults to False (keep) on failure.
    """
    try:
        raw = _call_groq(NOISE_FILTER_PROMPT, question[:200], max_tokens=40, api_key=api_key, temperature=0.3)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        result = json.loads(raw.strip())
        return bool(result.get("noise", False))
    except Exception:
        return False


CLASSIFY_PROMPT = """Classify this conversation turn. Return ONLY valid JSON, no explanation.

{
  "project": "project name or 'general' or 'soul'",
  "topic": "1-3 word topic",
  "activity": "one of: bugfix|feature|debug|config|deploy|research|discussion|learning|identity|behavior|growth"
}

Known projects: neo-console, ai2ai, memory-bridge, openclaw, moltbook, soul
Project "soul" is for anything about: who I am, my personality, how I should behave, lessons about myself, personal growth, emotional patterns, communication style, relationships, self-reflection, values.
Activity "identity" = defining who I am, my traits, my voice.
Activity "behavior" = how I act, patterns to follow or avoid, social skills, reactions.
Activity "growth" = lessons learned about myself, evolution, moments of change, maturity.
If unsure between "soul" and another project, prefer "soul" when the content is about self-knowledge rather than technical work.

Q+A:
"""

QUERY_ANALYZE_PROMPT = """Analyze this search query. Return ONLY valid JSON, no explanation.

{
  "project": "project name or null if not specific",
  "topic": "topic keyword or null",
  "activity": "activity type or null",
  "time_hint": "recent|old|any",
  "refined_query": "rewritten query optimized for semantic search"
}

Known projects: neo-console, ai2ai, memory-bridge, openclaw, moltbook, soul
Project "soul" matches queries about: identity, personality, behavior, growth, lessons about myself, how I act, who I am, values, relationships, self-reflection.
Activities include: identity, behavior, growth (in addition to technical ones).

Query:
"""

RERANK_PROMPT_TEMPLATE = """You receive a search query and N candidate memories. Score each memory 0-10 for relevance to the query. Return ONLY valid JSON array, no explanation.

[{{"index": 0, "score": 8, "reason": "2 words"}}, ...]

Query: "{query}"

Memories:
{memories}"""


def classify_memory(question: str, answer: str, api_key: Optional[str] = None) -> dict:
    """Classify a Q+A turn into project/topic/activity via Groq.

    Returns dict with 'project', 'topic', 'activity' keys.
    Falls back to defaults on failure.
    """
    text = f"Q: {question[:300]}\nA: {answer[:500]}"
    try:
        raw = _call_groq(CLASSIFY_PROMPT, text, max_tokens=100, api_key=api_key)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        result = json.loads(raw.strip())
        return {
            "project": result.get("project", "general"),
            "topic": result.get("topic", "unknown"),
            "activity": result.get("activity", "discussion"),
        }
    except Exception:
        return {"project": "general", "topic": "unknown", "activity": "discussion"}


def analyze_query(query: str, api_key: Optional[str] = None) -> dict:
    """Analyze a search query to extract filters and refine it via Groq.

    Returns dict with 'project', 'topic', 'activity', 'time_hint', 'refined_query'.
    Falls back to passthrough on failure.
    """
    try:
        raw = _call_groq(QUERY_ANALYZE_PROMPT, query, max_tokens=150, api_key=api_key)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        result = json.loads(raw.strip())
        return {
            "project": result.get("project"),
            "topic": result.get("topic"),
            "activity": result.get("activity"),
            "time_hint": result.get("time_hint", "any"),
            "refined_query": result.get("refined_query", query),
        }
    except Exception:
        return {
            "project": None,
            "topic": None,
            "activity": None,
            "time_hint": "any",
            "refined_query": query,
        }


def rerank_memories(query: str, memories: list, api_key: Optional[str] = None) -> list:
    """Re-rank candidate memories by relevance to query via Groq.

    Takes raw memories from ChromaDB, asks Groq to score them,
    returns memories sorted by relevance score (highest first).
    """
    if not memories:
        return memories

    # Build compact representation for Groq
    mem_text = []
    for i, mem in enumerate(memories):
        q = mem.get("question", "")[:150]
        a = mem.get("answer_preview", "")[:200]
        mem_text.append(f"[{i}] Q: {q}\n    A: {a}")

    prompt = RERANK_PROMPT_TEMPLATE.format(query=query, memories="\n".join(mem_text))

    try:
        raw = _call_groq("", prompt, max_tokens=300, api_key=api_key)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        scores = json.loads(raw.strip())

        # Map scores back to memories
        score_map = {s["index"]: s["score"] for s in scores if "index" in s and "score" in s}
        for i, mem in enumerate(memories):
            mem["relevance_score"] = score_map.get(i, 5)

        # Sort by relevance score descending
        memories.sort(key=lambda m: m.get("relevance_score", 0), reverse=True)
        return memories
    except Exception:
        return memories


if __name__ == "__main__":
    tests = [
        "The stdout reader crashed because tool_use_result was a string instead of an object",
        "Memory bank uses MBEL compression achieving 75% token savings",
        "Living Memory DNA uses genetic algorithms for memory evolution with crossover and mutation",
        "We discussed how neo-console wraps Claude CLI via stdin/stdout and SignalR",
    ]

    for text in tests:
        dna = compile_to_dna(text)
        print(f"Text: {text[:60]}...")
        print(f"DNA:  {dna}")
        print()
