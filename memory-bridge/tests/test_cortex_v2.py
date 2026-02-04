"""
Tests for Cortex V2 — Jina embeddings + rich metadata + smart query.

Uses mocked Jina API and Groq API so tests run offline and fast.
"""

import json
import time
import os
import sys
import shutil
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

TEST_DB_BASE = os.path.join(os.path.dirname(__file__), "test_v2_db")
_test_counter = 0

# Fake embedding: 1024-dim vector (Jina v3 dimensions)
FAKE_DIM = 1024


def _fake_embedding(seed: float = 0.5):
    """Generate a deterministic fake 1024-dim embedding."""
    import numpy as np
    rng = np.random.RandomState(int(seed * 1000))
    vec = rng.randn(FAKE_DIM).tolist()
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


def _fake_embedding_similar(base_seed: float, noise: float = 0.1):
    """Generate an embedding similar to the base."""
    import numpy as np
    base = _fake_embedding(base_seed)
    rng = np.random.RandomState(int(noise * 10000))
    noisy = [x + rng.randn() * noise for x in base]
    norm = sum(x * x for x in noisy) ** 0.5
    return [x / norm for x in noisy]


@pytest.fixture(autouse=True)
def test_db_dir():
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


def _mock_jina_embedder():
    """Create a mock JinaEmbedder that returns deterministic vectors."""
    mock = MagicMock()
    call_count = [0]

    def embed_passage(text):
        call_count[0] += 1
        return _fake_embedding(call_count[0] * 0.1)

    def embed_query(text):
        call_count[0] += 1
        return _fake_embedding(call_count[0] * 0.1)

    def embed_passages_batch(texts, batch_size=64):
        results = []
        for t in texts:
            call_count[0] += 1
            results.append(_fake_embedding(call_count[0] * 0.1))
        return results

    mock.embed_passage = embed_passage
    mock.embed_query = embed_query
    mock.embed_passages_batch = embed_passages_batch
    return mock


# --- Jina Embedder Tests ---


class TestJinaEmbedder:
    """jina_embedder.py should call Jina API correctly."""

    @patch("jina_embedder.requests.post")
    def test_embed_single_passage(self, mock_post):
        from jina_embedder import JinaEmbedder

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"index": 0, "embedding": [0.1] * 1024}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        embedder = JinaEmbedder(api_key="test-key")
        result = embedder.embed_passage("hello world")

        assert len(result) == 1024
        call_args = mock_post.call_args
        body = call_args[1]["json"]
        assert body["task"] == "retrieval.passage"
        assert body["model"] == "jina-embeddings-v3"
        assert body["dimensions"] == 1024

    @patch("jina_embedder.requests.post")
    def test_embed_query_uses_query_task(self, mock_post):
        from jina_embedder import JinaEmbedder

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"index": 0, "embedding": [0.2] * 1024}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        embedder = JinaEmbedder(api_key="test-key")
        result = embedder.embed_query("search query")

        assert len(result) == 1024
        body = mock_post.call_args[1]["json"]
        assert body["task"] == "retrieval.query"

    @patch("jina_embedder.requests.post")
    def test_batch_embed(self, mock_post):
        from jina_embedder import JinaEmbedder

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"index": 0, "embedding": [0.1] * 1024},
                {"index": 1, "embedding": [0.2] * 1024},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        embedder = JinaEmbedder(api_key="test-key")
        results = embedder.embed_passages_batch(["text1", "text2"])
        assert len(results) == 2
        assert len(results[0]) == 1024


# --- Groq Classifier Tests ---


class TestGroqClassifier:
    """classify_memory and analyze_query should return structured data."""

    @patch("groq_compiler._call_groq")
    def test_classify_memory_returns_dict(self, mock_groq):
        from groq_compiler import classify_memory

        mock_groq.return_value = '{"project": "neo-console", "topic": "crash fix", "activity": "bugfix"}'
        result = classify_memory("come fixare il crash?", "catch Exception", api_key="test")

        assert result["project"] == "neo-console"
        assert result["topic"] == "crash fix"
        assert result["activity"] == "bugfix"

    @patch("groq_compiler._call_groq")
    def test_classify_memory_fallback(self, mock_groq):
        from groq_compiler import classify_memory

        mock_groq.side_effect = Exception("API error")
        result = classify_memory("test", "test", api_key="test")

        assert result["project"] == "general"
        assert result["topic"] == "unknown"
        assert result["activity"] == "discussion"

    @patch("groq_compiler._call_groq")
    def test_analyze_query_returns_filters(self, mock_groq):
        from groq_compiler import analyze_query

        mock_groq.return_value = json.dumps({
            "project": "neo-console",
            "topic": "crash",
            "activity": "bugfix",
            "time_hint": "recent",
            "refined_query": "neo-console stdout crash exception fix",
        })
        result = analyze_query("come abbiamo fixato il crash di neo-console?", api_key="test")

        assert result["project"] == "neo-console"
        assert result["time_hint"] == "recent"
        assert "crash" in result["refined_query"]

    @patch("groq_compiler._call_groq")
    def test_analyze_query_fallback(self, mock_groq):
        from groq_compiler import analyze_query

        mock_groq.side_effect = Exception("API error")
        result = analyze_query("test query", api_key="test")

        assert result["refined_query"] == "test query"
        assert result["project"] is None

    @patch("groq_compiler._call_groq")
    def test_rerank_memories(self, mock_groq):
        from groq_compiler import rerank_memories

        mock_groq.return_value = json.dumps([
            {"index": 0, "score": 3, "reason": "irrelevant"},
            {"index": 1, "score": 9, "reason": "exact match"},
        ])
        memories = [
            {"question": "unrelated stuff", "answer_preview": "blah"},
            {"question": "crash fix", "answer_preview": "catch Exception"},
        ]
        result = rerank_memories("crash fix", memories, api_key="test")

        assert result[0]["question"] == "crash fix"
        assert result[0]["relevance_score"] == 9


# --- Cortex V2 Tests ---


class TestCortexV2Ingest:
    """ConversationCortexV2 should ingest with rich metadata."""

    def test_ingest_stores_memory(self, test_db_dir):
        from conversation_cortex_v2 import ConversationCortexV2

        with patch.object(ConversationCortexV2, '__init__', lambda self, **kw: None):
            pass

        # Build cortex with mocked embedder
        cortex = ConversationCortexV2.__new__(ConversationCortexV2)
        cortex.embedder = _mock_jina_embedder()
        cortex.dream_count = 0

        import chromadb
        cortex.client = chromadb.PersistentClient(
            path=test_db_dir,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        cortex.collection = cortex.client.create_collection(
            "conversations_v2", metadata={"hnsw:space": "cosine"}
        )

        turn = _make_turn(1, "how to fix crash?", "catch Exception not just JsonException")
        with patch("conversation_cortex_v2.classify_memory", return_value={
            "project": "neo-console", "topic": "crash", "activity": "bugfix"
        }), patch("conversation_cortex_v2.compile_to_dna", return_value="(crash)::{E:ANG|T:LIN|C:MOD}"):
            spore_id = cortex.ingest_json(turn, use_groq=True)

        assert spore_id.startswith("v2_")
        assert cortex.collection.count() == 1

        # Verify metadata
        data = cortex.collection.get(ids=[spore_id])
        meta = data["metadatas"][0]
        assert meta["project"] == "neo-console"
        assert meta["topic"] == "crash"
        assert meta["activity"] == "bugfix"

    def test_ingest_without_groq(self, test_db_dir):
        from conversation_cortex_v2 import ConversationCortexV2

        cortex = ConversationCortexV2.__new__(ConversationCortexV2)
        cortex.embedder = _mock_jina_embedder()
        cortex.dream_count = 0

        import chromadb
        cortex.client = chromadb.PersistentClient(
            path=test_db_dir,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        cortex.collection = cortex.client.create_collection(
            "conversations_v2", metadata={"hnsw:space": "cosine"}
        )

        turn = _make_turn(1, "test", "test answer")
        spore_id = cortex.ingest_json(turn, use_groq=False)

        data = cortex.collection.get(ids=[spore_id])
        meta = data["metadatas"][0]
        assert meta["project"] == "general"
        assert meta["activity"] == "discussion"


class TestCortexV2Recall:
    """ConversationCortexV2 recall should support basic and smart modes."""

    def _build_cortex(self, test_db_dir):
        from conversation_cortex_v2 import ConversationCortexV2
        import chromadb

        cortex = ConversationCortexV2.__new__(ConversationCortexV2)
        cortex.embedder = _mock_jina_embedder()
        cortex.dream_count = 0
        cortex.client = chromadb.PersistentClient(
            path=test_db_dir,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        cortex.collection = cortex.client.create_collection(
            "conversations_v2", metadata={"hnsw:space": "cosine"}
        )
        return cortex

    def test_basic_recall_empty(self, test_db_dir):
        cortex = self._build_cortex(test_db_dir)
        memories = cortex.recall("anything", n=3, smart=False)
        assert len(memories) == 0

    def test_basic_recall_finds_memory(self, test_db_dir):
        cortex = self._build_cortex(test_db_dir)

        turn = _make_turn(1, "how to fix crash?", "catch Exception")
        cortex.ingest_json(turn, use_groq=False)

        memories = cortex.recall("crash fix", n=3, smart=False)
        assert len(memories) > 0
        assert "project" in memories[0]

    @patch("conversation_cortex_v2.analyze_query")
    @patch("conversation_cortex_v2.rerank_memories")
    def test_smart_recall_uses_filters(self, mock_rerank, mock_analyze, test_db_dir):
        cortex = self._build_cortex(test_db_dir)

        # Ingest two memories with different projects
        with patch("conversation_cortex_v2.classify_memory", return_value={
            "project": "neo-console", "topic": "crash", "activity": "bugfix"
        }), patch("conversation_cortex_v2.compile_to_dna", return_value="(crash)::{E:ANG}"):
            cortex.ingest_json(_make_turn(1, "crash in neo-console", "fixed with catch"), use_groq=True)

        with patch("conversation_cortex_v2.classify_memory", return_value={
            "project": "ai2ai", "topic": "embeddings", "activity": "feature"
        }), patch("conversation_cortex_v2.compile_to_dna", return_value="(embed)::{E:SER}"):
            cortex.ingest_json(_make_turn(2, "embeddings in ai2ai", "using jina v3"), use_groq=True)

        mock_analyze.return_value = {
            "project": "neo-console",
            "topic": "crash",
            "activity": "bugfix",
            "time_hint": "any",
            "refined_query": "neo-console crash fix",
        }
        mock_rerank.side_effect = lambda q, m, **kw: m

        memories = cortex.recall("crash in neo-console", n=5, smart=True)
        assert len(memories) > 0
        mock_analyze.assert_called_once()


class TestCortexV2Timeline:
    """timeline() should return memories ordered by timestamp."""

    def test_timeline_order(self, test_db_dir):
        from conversation_cortex_v2 import ConversationCortexV2
        import chromadb

        cortex = ConversationCortexV2.__new__(ConversationCortexV2)
        cortex.embedder = _mock_jina_embedder()
        cortex.dream_count = 0
        cortex.client = chromadb.PersistentClient(
            path=test_db_dir,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        cortex.collection = cortex.client.create_collection(
            "conversations_v2", metadata={"hnsw:space": "cosine"}
        )

        # Ingest 3 turns with different timestamps
        base_time = time.time()
        for i in range(3):
            turn = _make_turn(i + 1, f"question {i}", f"answer {i}")
            turn["timestamp"] = base_time + (i * 60)
            cortex.ingest_json(turn, use_groq=False)

        timeline = cortex.timeline()
        assert len(timeline) == 3
        # Newest first
        assert timeline[0]["timestamp"] > timeline[1]["timestamp"]
        assert timeline[1]["timestamp"] > timeline[2]["timestamp"]

    def test_timeline_project_filter(self, test_db_dir):
        from conversation_cortex_v2 import ConversationCortexV2
        import chromadb

        cortex = ConversationCortexV2.__new__(ConversationCortexV2)
        cortex.embedder = _mock_jina_embedder()
        cortex.dream_count = 0
        cortex.client = chromadb.PersistentClient(
            path=test_db_dir,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        cortex.collection = cortex.client.create_collection(
            "conversations_v2", metadata={"hnsw:space": "cosine"}
        )

        # Ingest with different projects via metadata override
        with patch("conversation_cortex_v2.classify_memory", return_value={
            "project": "neo-console", "topic": "test", "activity": "debug"
        }), patch("conversation_cortex_v2.compile_to_dna", return_value="(test)::{E:SER}"):
            cortex.ingest_json(_make_turn(1, "neo q", "neo a"), use_groq=True)

        with patch("conversation_cortex_v2.classify_memory", return_value={
            "project": "ai2ai", "topic": "test", "activity": "debug"
        }), patch("conversation_cortex_v2.compile_to_dna", return_value="(test)::{E:SER}"):
            cortex.ingest_json(_make_turn(2, "ai2ai q", "ai2ai a"), use_groq=True)

        all_timeline = cortex.timeline()
        assert len(all_timeline) == 2

        neo_timeline = cortex.timeline(project="neo-console")
        assert len(neo_timeline) == 1
        assert neo_timeline[0]["project"] == "neo-console"


class TestCortexV2Stats:
    """stats() should include project breakdown."""

    def test_stats_includes_projects(self, test_db_dir):
        from conversation_cortex_v2 import ConversationCortexV2
        import chromadb

        cortex = ConversationCortexV2.__new__(ConversationCortexV2)
        cortex.embedder = _mock_jina_embedder()
        cortex.dream_count = 0
        cortex.client = chromadb.PersistentClient(
            path=test_db_dir,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        cortex.collection = cortex.client.create_collection(
            "conversations_v2", metadata={"hnsw:space": "cosine"}
        )

        cortex.ingest_json(_make_turn(1, "test", "answer"), use_groq=False)

        stats = cortex.stats()
        assert stats["version"] == "v2"
        assert stats["total_memories"] == 1
        assert "projects" in stats
        assert "general" in stats["projects"]
