"""
Neo MCP Server — FastMCP shell that aggregates tools from modules.

Imports:
  - memory-bridge: cortex, memory tools, HTTP endpoints
  - tools/email: email tools (future)
  - tools/*: future tools

This file is thin — just FastMCP registration. Business logic stays in modules.
"""

import sys
import os
import logging

# Add module paths
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "memory-bridge", "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "email"))

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# Import memory module
from conversation_cortex_v2 import ConversationCortexV2
from groq_compiler import aggregate_to_mbel

# Import email module
try:
    from email_tools import email_list, email_read, email_send
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    logger.warning("email_tools not available")

logger = logging.getLogger("neo-mcp")

DEFAULT_DB_DIR = os.path.join(REPO_ROOT, "memory-bridge", "cortex_db")


def create_cortex(db_dir: str = None) -> ConversationCortexV2:
    if db_dir is None:
        db_dir = DEFAULT_DB_DIR
    return ConversationCortexV2(persist_dir=db_dir)


# --- Memory tool implementations (from memory-bridge) ---

def memory_query_impl(cortex: ConversationCortexV2, query: str, n: int = 5) -> dict:
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


def memory_ingest_impl(cortex: ConversationCortexV2, turn: dict, use_groq: bool = True) -> dict:
    spore_id = cortex.ingest_json(turn, use_groq=use_groq)
    if not spore_id:
        return {"status": "skipped", "reason": "noise"}
    return {"status": "ingested", "spore_id": spore_id}


def memory_timeline_impl(cortex: ConversationCortexV2, n: int = 5, project: str = None) -> dict:
    """Get most recent memories by timestamp."""
    memories = cortex.timeline(project=project, limit=n)
    result = {"count": len(memories), "memories": memories}
    if memories:
        try:
            result["mbel"] = aggregate_to_mbel(memories)
        except Exception as e:
            logger.warning(f"MBEL aggregation failed: {e}")
    return result


# --- FastMCP Server ---

def create_mcp_server(db_dir: str = None, use_groq: bool = True, cortex: ConversationCortexV2 = None) -> FastMCP:
    """Create the FastMCP server with all tools."""
    if cortex is None:
        cortex = create_cortex(db_dir)

    mcp = FastMCP(
        "neo-mcp",
        instructions="Neo's MCP server. Memory cortex, email tools, and more.",
    )

    # --- Memory Tools ---

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

    @mcp.tool()
    def memory_timeline(n: int = 10, project: str = None) -> dict:
        """Get most recent memories by timestamp (newest first).

        Use this at session start to load recent context, or to see what happened lately.

        Args:
            n: Number of recent memories to return (default 10)
            project: Optional filter by project name
        """
        return memory_timeline_impl(cortex, n=n, project=project)

    # --- Email Tools ---
    if EMAIL_AVAILABLE:
        @mcp.tool()
        def email_list_tool(n: int = 10, folder: str = "INBOX", unread_only: bool = False) -> dict:
            """List recent emails from inbox.

            Args:
                n: Number of emails to return (default 10)
                folder: IMAP folder to list from (default INBOX)
                unread_only: If true, only return unread emails (default false)
            """
            return email_list(n=n, folder=folder, unread_only=unread_only)

        @mcp.tool()
        def email_read_tool(uid: str, folder: str = "INBOX") -> dict:
            """Read a specific email by UID.

            Args:
                uid: The email UID to read
                folder: IMAP folder (default INBOX)
            """
            return email_read(uid=uid, folder=folder)

        @mcp.tool()
        def email_send_tool(to: str, subject: str, body: str, html: bool = False) -> dict:
            """Send an email.

            Args:
                to: Recipient email address
                subject: Email subject
                body: Email body text
                html: If true, send as HTML email
            """
            return email_send(to=to, subject=subject, body=body, html=html)

    # --- HTTP Routes for Memory (neo-console needs these) ---

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

    @mcp.custom_route("/timeline", methods=["GET"])
    async def http_timeline(request: Request) -> JSONResponse:
        n = int(request.query_params.get("n", "5"))
        project = request.query_params.get("project")
        try:
            result = memory_timeline_impl(cortex, n=n, project=project)
            return JSONResponse(result)
        except Exception as e:
            logger.exception("timeline failed")
            return JSONResponse({"error": str(e)}, status_code=500)

    return mcp


def start_http_server(cortex: ConversationCortexV2, host: str = "127.0.0.1", port: int = 5071, use_groq: bool = True):
    """Start HTTP server in a daemon thread, sharing the given cortex instance."""
    import threading
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route

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

    async def timeline_handler(request: Request) -> JSONResponse:
        n = int(request.query_params.get("n", "5"))
        project = request.query_params.get("project")
        try:
            result = memory_timeline_impl(cortex, n=n, project=project)
            return JSONResponse(result)
        except Exception as e:
            logger.exception("timeline failed")
            return JSONResponse({"error": str(e)}, status_code=500)

    app = Starlette(
        routes=[
            Route("/ingest", ingest_handler, methods=["POST"]),
            Route("/health", health_handler, methods=["GET"]),
            Route("/query", query_handler, methods=["GET"]),
            Route("/timeline", timeline_handler, methods=["GET"]),
        ]
    )

    def _run():
        uvicorn.run(app, host=host, port=port, log_level="info")

    t = threading.Thread(target=_run, daemon=True, name="http-server")
    t.start()
    logger.info(f"HTTP server started on {host}:{port}")
    return t


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    use_groq = "--no-groq" not in sys.argv

    if mode == "http":
        mcp = create_mcp_server(use_groq=use_groq)
        mcp.run(transport="streamable-http", host="127.0.0.1", port=5071)
    else:
        # Unified mode: ONE cortex, TWO channels (MCP stdio + HTTP)
        cortex = create_cortex()
        start_http_server(cortex, use_groq=use_groq)
        mcp = create_mcp_server(use_groq=use_groq, cortex=cortex)
        mcp.run(transport="stdio")
