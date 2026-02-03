"""
Tests for memory_bridge_server - TDD approach.
Tests MCP tools + HTTP endpoints.
"""

import json
import time
import os
import sys
import shutil
import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


TEST_DB_BASE = os.path.join(os.path.dirname(__file__), "test_bridge_db")
_test_counter = 0


@pytest.fixture(autouse=True)
def test_db_dir():
    """Give each test a unique DB dir to avoid chromaDB lock issues."""
    global _test_counter
    _test_counter += 1
    db_dir = f"{TEST_DB_BASE}_{_test_counter}_{os.getpid()}"
    os.makedirs(db_dir, exist_ok=True)
    yield db_dir
    if os.path.exists(db_dir):
        shutil.rmtree(db_dir, ignore_errors=True)


def _make_turn(turn_number=1, question="test question", answer="test answer"):
    return {
        "session_id": "test-session-001",
        "timestamp": time.time(),
        "turn_number": turn_number,
        "question": {"text": question, "source": "test"},
        "answer": {"text": answer, "tools_used": ["Read"]},
        "stats": {"input_tokens": 100, "output_tokens": 200},
        "model": "opus",
    }


# --- MCP Tool Tests ---


class TestMemoryQueryTool:
    """memory_query tool should recall memories by semantic similarity."""

    def test_query_empty_cortex_returns_empty(self, test_db_dir):
        from memory_bridge_server import create_cortex, memory_query_impl

        cortex = create_cortex(test_db_dir)
        result = memory_query_impl(cortex, "anything", n=3)
        assert result["count"] == 0

    def test_query_finds_relevant_memory(self, test_db_dir):
        from memory_bridge_server import create_cortex, memory_query_impl

        cortex = create_cortex(test_db_dir)
        cortex.ingest_json(
            _make_turn(1, "how to fix crash?", "catch Exception not just JsonException"),
            use_groq=False,
        )
        result = memory_query_impl(cortex, "crash fix exception", n=3)
        assert result["count"] > 0
        # Result has either 'mbel' (if groq works) or 'memories' (fallback)
        assert "mbel" in result or "memories" in result


class TestMemoryStatsTool:
    """memory_stats tool should return cortex statistics."""

    def test_stats_empty_cortex(self, test_db_dir):
        from memory_bridge_server import create_cortex, memory_stats_impl

        cortex = create_cortex(test_db_dir)
        result = memory_stats_impl(cortex)
        assert result["total_memories"] == 0

    def test_stats_after_ingest(self, test_db_dir):
        from memory_bridge_server import create_cortex, memory_stats_impl

        cortex = create_cortex(test_db_dir)
        cortex.ingest_json(_make_turn(), use_groq=False)
        result = memory_stats_impl(cortex)
        assert result["total_memories"] == 1


class TestMemoryDreamTool:
    """memory_dream tool should run a dream cycle."""

    def test_dream_empty_cortex(self, test_db_dir):
        from memory_bridge_server import create_cortex, memory_dream_impl

        cortex = create_cortex(test_db_dir)
        result = memory_dream_impl(cortex)
        assert "skipped" in result["status"] or result["dreams"] == 0

    def test_dream_with_memories(self, test_db_dir):
        from memory_bridge_server import create_cortex, memory_dream_impl

        cortex = create_cortex(test_db_dir)
        cortex.ingest_json(
            _make_turn(1, "question one", "answer one"), use_groq=False
        )
        cortex.ingest_json(
            _make_turn(2, "question two", "answer two"), use_groq=False
        )
        result = memory_dream_impl(cortex)
        assert result["dreams"] >= 1


class TestMemoryIngestTool:
    """memory_ingest tool should manually ingest a turn."""

    def test_ingest_valid_turn(self, test_db_dir):
        from memory_bridge_server import create_cortex, memory_ingest_impl

        cortex = create_cortex(test_db_dir)
        turn = _make_turn(1, "manual ingest test", "this was manually ingested")
        result = memory_ingest_impl(cortex, turn, use_groq=False)
        assert result["status"] == "ingested"
        assert result["spore_id"] is not None

    def test_ingest_then_recall(self, test_db_dir):
        from memory_bridge_server import create_cortex, memory_ingest_impl, memory_query_impl

        cortex = create_cortex(test_db_dir)
        turn = _make_turn(1, "chromaDB embedding test", "embeddings stored in chromaDB")
        memory_ingest_impl(cortex, turn, use_groq=False)
        result = memory_query_impl(cortex, "chromaDB embeddings", n=3)
        assert result["count"] > 0


# --- HTTP Endpoint Tests ---


class TestHTTPIngestEndpoint:
    """POST /ingest should accept a turn JSON and store it."""

    def test_ingest_endpoint_valid(self, test_db_dir):
        from memory_bridge_server import create_app
        from starlette.testclient import TestClient

        app = create_app(db_dir=test_db_dir, use_groq=False)
        client = TestClient(app)
        turn = _make_turn(1, "http ingest test", "answer via http")
        resp = client.post("/ingest", json=turn)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ingested"
        assert "spore_id" in data

    def test_ingest_endpoint_invalid_json(self, test_db_dir):
        from memory_bridge_server import create_app
        from starlette.testclient import TestClient

        app = create_app(db_dir=test_db_dir, use_groq=False)
        client = TestClient(app)
        resp = client.post(
            "/ingest",
            content="not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_ingest_endpoint_missing_question(self, test_db_dir):
        from memory_bridge_server import create_app
        from starlette.testclient import TestClient

        app = create_app(db_dir=test_db_dir, use_groq=False)
        client = TestClient(app)
        resp = client.post("/ingest", json={"session_id": "x"})
        # Should still work — cortex handles missing fields with defaults
        assert resp.status_code == 200


class TestHTTPHealthEndpoint:
    """GET /health should return cortex stats."""

    def test_health_endpoint(self, test_db_dir):
        from memory_bridge_server import create_app
        from starlette.testclient import TestClient

        app = create_app(db_dir=test_db_dir, use_groq=False)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"
