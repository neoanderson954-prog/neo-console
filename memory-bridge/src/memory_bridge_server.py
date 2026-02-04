"""
Memory Bridge Server — FastMCP + HTTP endpoints.

Two channels:
  1. MCP tools (stdio) — Claude uses voluntarily: query, stats, dream, ingest
  2. HTTP endpoints — neo-console wrapper POSTs turns automatically: /ingest, /health

V2: Uses ConversationCortexV2 (Jina embeddings + rich metadata + smart query).
"""

import json
import os
import logging
from typing import Optional

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from conversation_cortex_v2 import ConversationCortexV2
from groq_compiler import aggregate_to_mbel

logger = logging.getLogger("memory-bridge")

DEFAULT_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cortex_db",
)


def create_cortex(db_dir: str = None) -> ConversationCortexV2:
    if db_dir is None:
        db_dir = DEFAULT_DB_DIR
    return ConversationCortexV2(persist_dir=db_dir)


# --- Implementation functions (testable without MCP) ---


def memory_query_impl(
    cortex: ConversationCortexV2, query: str, n: int = 5
) -> dict:
    memories = cortex.recall(query, n=n, smart=True)
    result = {"query": query, "count": len(memories)}
    if memories:
        try:
            result["mbel"] = aggregate_to_mbel(memories)
        except Exception as e:
            logger.warning(f"MBEL aggregation failed: {e}")
            result["memories"] = memories
    return result


def memory_stats_impl(cortex: ConversationCortexV2) -> dict:
    stats = cortex.stats()
    if stats.get("total") == 0 and "total_memories" not in stats:
        stats["total_memories"] = 0
    return stats


def memory_dream_impl(cortex: ConversationCortexV2) -> dict:
    stats_before = cortex.stats()
    total = stats_before.get("total_memories", stats_before.get("total", 0))
    if total < 2:
        return {"status": "skipped", "reason": "need >= 2 memories", "dreams": 0}
    cluster = cortex.dream_cycle()
    return {
        "status": "completed",
        "dreams": cortex.dream_count,
        "cluster": list(cluster) if cluster else [],
    }


def memory_ingest_impl(
    cortex: ConversationCortexV2, turn: dict, use_groq: bool = True
) -> dict:
    spore_id = cortex.ingest_json(turn, use_groq=use_groq)
    if not spore_id:
        return {"status": "skipped", "reason": "noise"}
    return {"status": "ingested", "spore_id": spore_id}


# --- App factory (for HTTP testing without MCP stdio) ---


def create_app(db_dir: str = None, use_groq: bool = True):
    """Create a Starlette app with /ingest and /health routes."""
    from starlette.applications import Starlette
    from starlette.routing import Route

    cortex = create_cortex(db_dir)

    async def ingest_handler(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        try:
            result = memory_ingest_impl(cortex, body, use_groq=use_groq)
            return JSONResponse(result)
        except Exception as e:
            logger.exception("ingest failed")
            return JSONResponse({"error": str(e)}, status_code=500)

    async def health_handler(request: Request) -> JSONResponse:
        stats = memory_stats_impl(cortex)
        return JSONResponse({"status": "ok", **stats})

    async def query_handler(request: Request) -> JSONResponse:
        q = request.query_params.get("q", "")
        if not q:
            return JSONResponse({"error": "missing ?q= parameter"}, status_code=400)
        n = int(request.query_params.get("n", "5"))
        try:
            result = memory_query_impl(cortex, q, n=n)
            return JSONResponse(result)
        except Exception as e:
            logger.exception("query failed")
            return JSONResponse({"error": str(e)}, status_code=500)

    return Starlette(
        routes=[
            Route("/ingest", ingest_handler, methods=["POST"]),
            Route("/health", health_handler, methods=["GET"]),
            Route("/query", query_handler, methods=["GET"]),
        ]
    )


# --- FastMCP server (for Claude MCP tools) ---


def create_mcp_server(db_dir: str = None, use_groq: bool = True) -> FastMCP:
    """Create the FastMCP server with tools + HTTP routes."""
    cortex = create_cortex(db_dir)

    mcp = FastMCP(
        "memory-bridge",
        instructions="Memory cortex for Neo. Query past conversations, run dream cycles, check stats.",
    )

    @mcp.tool()
    def memory_query(query: str, n: int = 5) -> dict:
        """Search past conversation memories by semantic similarity.

        Args:
            query: What to search for (natural language)
            n: Number of results to return (default 5)
        """
        return memory_query_impl(cortex, query, n=n)

    @mcp.tool()
    def memory_stats() -> dict:
        """Get cortex statistics: total memories, sessions, energy levels, dream count."""
        return memory_stats_impl(cortex)

    @mcp.tool()
    def memory_dream() -> dict:
        """Run one dream cycle: boost high-energy memories, decay others."""
        return memory_dream_impl(cortex)

    @mcp.tool()
    def memory_ingest(turn: dict) -> dict:
        """Manually ingest a conversation turn into memory.

        Args:
            turn: JSON with session_id, question, answer, model, stats
        """
        return memory_ingest_impl(cortex, turn, use_groq=use_groq)

    @mcp.custom_route("/ingest", methods=["POST"])
    async def http_ingest(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        try:
            result = memory_ingest_impl(cortex, body, use_groq=use_groq)
            return JSONResponse(result)
        except Exception as e:
            logger.exception("ingest failed")
            return JSONResponse({"error": str(e)}, status_code=500)

    @mcp.custom_route("/health", methods=["GET"])
    async def http_health(request: Request) -> JSONResponse:
        stats = memory_stats_impl(cortex)
        return JSONResponse({"status": "ok", **stats})

    @mcp.custom_route("/query", methods=["GET"])
    async def http_query(request: Request) -> JSONResponse:
        q = request.query_params.get("q", "")
        if not q:
            return JSONResponse({"error": "missing ?q= parameter"}, status_code=400)
        n = int(request.query_params.get("n", "5"))
        try:
            result = memory_query_impl(cortex, q, n=n)
            return JSONResponse(result)
        except Exception as e:
            logger.exception("query failed")
            return JSONResponse({"error": str(e)}, status_code=500)

    return mcp


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if mode == "http":
        mcp = create_mcp_server()
        mcp.run(transport="streamable-http", host="127.0.0.1", port=5071)
    else:
        mcp = create_mcp_server()
        mcp.run(transport="stdio")
