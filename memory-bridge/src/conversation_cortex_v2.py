"""
Conversation Cortex V2 — Evolved memory with:
  - Jina embeddings v3 (1024d, multilingual, task adapters)
  - Rich metadata (project, topic, activity) via Groq classification
  - Smart query: Groq pre-filter → ChromaDB where → Groq re-rank
  - Timeline support via timestamp filters

Runs alongside v1 in a separate collection ('conversations_v2').
Migration script converts v1 → v2.
"""

import json
import time
import uuid
import os
from typing import List, Dict, Optional
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings
import numpy as np

from jina_embedder import JinaEmbedder
from groq_compiler import (
    compile_to_dna,
    classify_memory,
    analyze_query,
    rerank_memories,
    aggregate_to_mbel,
)


@dataclass
class ConversationTurn:
    """A single Q+A turn from a conversation."""
    session_id: str
    timestamp: float
    turn_number: int
    question: str
    answer: str
    tools_used: List[str]
    model: str = "opus"
    input_tokens: int = 0
    output_tokens: int = 0
    source: str = "neo-console"


class ConversationCortexV2:
    """V2 cortex: Jina embeddings + rich metadata + smart query."""

    def __init__(
        self,
        persist_dir: str = None,
        collection_name: str = "conversations_v2",
        jina_api_key: Optional[str] = None,
    ):
        if persist_dir is None:
            persist_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "cortex_db",
            )

        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        try:
            self.collection = self.client.get_collection(collection_name)
        except Exception:
            self.collection = self.client.create_collection(
                collection_name,
                metadata={"hnsw:space": "cosine"},
            )

        self.embedder = JinaEmbedder(api_key=jina_api_key)
        self.dream_count = 0

    def ingest_turn(self, turn: ConversationTurn, use_groq: bool = True) -> str:
        """Ingest a conversation turn with rich metadata.

        1. Embed Q+A via Jina (retrieval.passage)
        2. Classify project/topic/activity via Groq
        3. Compile DNA via Groq
        4. Store with rich metadata
        5. Create synaptic links
        """
        combined = f"Q: {turn.question}\nA: {turn.answer}"
        if len(combined) > 8000:
            combined = combined[:8000]

        # Jina embedding (passage mode for indexing)
        embedding = self.embedder.embed_passage(combined)

        # Classify via Groq
        classification = {"project": "general", "topic": "unknown", "activity": "discussion"}
        if use_groq:
            classification = classify_memory(turn.question, turn.answer)

        # DNA compilation
        dna = ""
        if use_groq:
            summary = f"{turn.question[:200]} → {turn.answer[:300]}"
            try:
                dna = compile_to_dna(summary)
            except Exception:
                dna = "(conversation)::{E:SER|T:LIN|C:MOD}"

        # Spore ID
        spore_id = f"v2_{turn.session_id[:8]}_{turn.turn_number}_{int(turn.timestamp) % 100000}"

        # Store with rich metadata
        self.collection.add(
            ids=[spore_id],
            embeddings=[embedding],
            documents=[combined],
            metadatas=[{
                "session_id": turn.session_id,
                "timestamp": turn.timestamp,
                "turn_number": turn.turn_number,
                "question": turn.question[:500],
                "answer_preview": turn.answer[:500],
                "tools_used": json.dumps(turn.tools_used),
                "model": turn.model,
                "dna": dna,
                "energy": 1.0,
                "source": turn.source,
                "project": classification["project"],
                "topic": classification["topic"],
                "activity": classification["activity"],
                "synaptic_links": "[]",
            }],
        )

        # Synaptic links
        self._link_resonant(spore_id, embedding)

        return spore_id

    def ingest_json(self, data: dict, use_groq: bool = True) -> str:
        """Ingest from JSON schema (same format as v1 for compatibility)."""
        q = data.get("question", {})
        a = data.get("answer", {})
        stats = data.get("stats", {})

        turn = ConversationTurn(
            session_id=data.get("session_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            turn_number=data.get("turn_number", 0),
            question=q.get("text", "") if isinstance(q, dict) else str(q),
            answer=a.get("text", "") if isinstance(a, dict) else str(a),
            tools_used=a.get("tools_used", []) if isinstance(a, dict) else [],
            model=data.get("model", "opus"),
            input_tokens=stats.get("input_tokens", 0),
            output_tokens=stats.get("output_tokens", 0),
            source=q.get("source", "unknown") if isinstance(q, dict) else "unknown",
        )

        return self.ingest_turn(turn, use_groq=use_groq)

    def ingest_jsonl(self, path: str, use_groq: bool = True) -> List[str]:
        """Ingest all turns from a JSONL file."""
        ids = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                spore_id = self.ingest_json(data, use_groq=use_groq)
                ids.append(spore_id)
        return ids

    def recall(self, query: str, n: int = 5, smart: bool = True) -> List[Dict]:
        """Recall memories with optional smart filtering.

        Smart mode (default):
          1. Groq analyzes query → extracts project/topic/activity/time filters
          2. Jina embeds refined query (retrieval.query mode)
          3. ChromaDB searches with where filters
          4. Groq re-ranks results by relevance

        Basic mode (smart=False):
          Pure vector similarity, like v1 but with Jina embeddings.
        """
        if smart:
            return self._smart_recall(query, n)
        return self._basic_recall(query, n)

    def _basic_recall(self, query: str, n: int = 5) -> List[Dict]:
        """Simple vector similarity recall with Jina query embedding."""
        embedding = self.embedder.embed_query(query)

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n,
        )

        return self._parse_results(results)

    def _smart_recall(self, query: str, n: int = 5) -> List[Dict]:
        """Smart recall: analyze → filter → search → re-rank."""
        # Step 1: Groq analyzes the query
        try:
            analysis = analyze_query(query)
        except Exception:
            return self._basic_recall(query, n)

        refined = analysis.get("refined_query", query)

        # Step 2: Jina embeds the refined query
        embedding = self.embedder.embed_query(refined)

        # Step 3: Build ChromaDB where filters
        where_filters = self._build_where_filters(analysis)

        # Fetch more candidates than needed for re-ranking
        fetch_n = min(n * 3, 20)

        try:
            if where_filters:
                results = self.collection.query(
                    query_embeddings=[embedding],
                    n_results=fetch_n,
                    where=where_filters,
                )
                # If filtered search returns too few, fall back to unfiltered
                if not results["ids"][0] or len(results["ids"][0]) < 2:
                    results = self.collection.query(
                        query_embeddings=[embedding],
                        n_results=fetch_n,
                    )
            else:
                results = self.collection.query(
                    query_embeddings=[embedding],
                    n_results=fetch_n,
                )
        except Exception:
            # ChromaDB filter error → fall back to unfiltered
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=fetch_n,
            )

        memories = self._parse_results(results)

        # Step 4: Groq re-ranks by relevance
        if len(memories) > 1:
            try:
                memories = rerank_memories(query, memories)
            except Exception:
                pass

        return memories[:n]

    def _build_where_filters(self, analysis: dict) -> Optional[dict]:
        """Build ChromaDB where clause from query analysis."""
        conditions = []

        project = analysis.get("project")
        if project:
            conditions.append({"project": {"$eq": project}})

        activity = analysis.get("activity")
        if activity:
            conditions.append({"activity": {"$eq": activity}})

        time_hint = analysis.get("time_hint", "any")
        if time_hint == "recent":
            # Last 7 days
            cutoff = time.time() - (7 * 24 * 3600)
            conditions.append({"timestamp": {"$gte": cutoff}})
        elif time_hint == "old":
            # Older than 7 days
            cutoff = time.time() - (7 * 24 * 3600)
            conditions.append({"timestamp": {"$lt": cutoff}})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _parse_results(self, results: dict) -> List[Dict]:
        """Parse ChromaDB query results into memory dicts."""
        memories = []
        if not results["ids"][0]:
            return memories

        for i, spore_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            dist = results["distances"][0][i]
            memories.append({
                "spore_id": spore_id,
                "question": meta.get("question", ""),
                "answer_preview": meta.get("answer_preview", ""),
                "dna": meta.get("dna", ""),
                "energy": meta.get("energy", 1.0),
                "similarity": 1.0 - dist,
                "session_id": meta.get("session_id", ""),
                "timestamp": meta.get("timestamp", 0),
                "model": meta.get("model", ""),
                "tools_used": json.loads(meta.get("tools_used", "[]")),
                "project": meta.get("project", "general"),
                "topic": meta.get("topic", "unknown"),
                "activity": meta.get("activity", "discussion"),
            })

        return memories

    def dream_cycle(self):
        """Run one dream cycle: boost accessed memories, decay others."""
        all_data = self.collection.get()
        if not all_data["ids"] or len(all_data["ids"]) < 2:
            return

        energies = [m.get("energy", 1.0) for m in all_data["metadatas"]]
        seed_idx = int(np.argmax(energies))
        seed_id = all_data["ids"][seed_idx]
        links = json.loads(all_data["metadatas"][seed_idx].get("synaptic_links", "[]"))
        dream_cluster = set([seed_id] + links)

        for i, sid in enumerate(all_data["ids"]):
            energy = all_data["metadatas"][i].get("energy", 1.0)
            if sid in dream_cluster:
                new_energy = min(1.0, energy + 0.1)
            else:
                new_energy = max(0.05, energy - 0.03)
            self.collection.update(
                ids=[sid],
                metadatas=[{"energy": new_energy}],
            )

        self.dream_count += 1
        return dream_cluster

    def stats(self) -> Dict:
        """Get cortex v2 statistics."""
        all_data = self.collection.get()
        if not all_data["ids"]:
            return {"total_memories": 0, "dreams": self.dream_count}

        energies = [m.get("energy", 1.0) for m in all_data["metadatas"]]
        sessions = set(m.get("session_id", "") for m in all_data["metadatas"])
        projects = {}
        for m in all_data["metadatas"]:
            p = m.get("project", "general")
            projects[p] = projects.get(p, 0) + 1

        return {
            "total_memories": len(all_data["ids"]),
            "sessions": len(sessions),
            "avg_energy": round(sum(energies) / len(energies), 3),
            "max_energy": round(max(energies), 3),
            "min_energy": round(min(energies), 3),
            "dreams": self.dream_count,
            "projects": projects,
            "version": "v2",
        }

    def _link_resonant(self, spore_id: str, embedding: list, top_n: int = 2):
        """Find and link semantically similar memories."""
        if self.collection.count() < 2:
            return

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_n + 1,
        )

        links = [sid for sid in results["ids"][0] if sid != spore_id][:top_n]
        if links:
            self.collection.update(
                ids=[spore_id],
                metadatas=[{"synaptic_links": json.dumps(links)}],
            )

    def timeline(self, project: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Get memories ordered by timestamp (newest first).

        Optional project filter.
        """
        all_data = self.collection.get()
        if not all_data["ids"]:
            return []

        memories = []
        for i, sid in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][i]
            if project and meta.get("project", "general") != project:
                continue
            memories.append({
                "spore_id": sid,
                "question": meta.get("question", ""),
                "answer_preview": meta.get("answer_preview", ""),
                "timestamp": meta.get("timestamp", 0),
                "project": meta.get("project", "general"),
                "topic": meta.get("topic", "unknown"),
                "activity": meta.get("activity", "discussion"),
                "energy": meta.get("energy", 1.0),
            })

        memories.sort(key=lambda m: m["timestamp"], reverse=True)
        return memories[:limit]
