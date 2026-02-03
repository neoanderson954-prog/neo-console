"""
Conversation Cortex - Ingests Q+A conversation turns into living memory.
Stores in ChromaDB with embeddings + DNA encoding.
Provides semantic recall for context injection.
"""

import json
import time
import uuid
import os
from typing import List, Dict, Optional
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import numpy as np

from groq_compiler import compile_to_dna


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


class ConversationCortex:
    """Ingests conversation turns, embeds them, compiles DNA, stores in ChromaDB."""

    def __init__(
        self,
        persist_dir: str = None,
        collection_name: str = "conversations",
        embedding_model: str = "all-MiniLM-L6-v2"
    ):
        if persist_dir is None:
            persist_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "cortex_db"
            )

        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )

        try:
            self.collection = self.client.get_collection(collection_name)
        except Exception:
            self.collection = self.client.create_collection(collection_name)

        self.embedder = SentenceTransformer(embedding_model)
        self.dream_count = 0

    def ingest_turn(self, turn: ConversationTurn, use_groq: bool = True) -> str:
        """Ingest a conversation turn into the cortex.

        Combines Q+A into a single document for embedding.
        Optionally compiles DNA via Groq.
        Returns the spore_id.
        """
        # Combine Q+A for embedding — the full context
        combined = f"Q: {turn.question}\nA: {turn.answer}"

        # Truncate for embedding (model handles ~256 tokens well)
        if len(combined) > 2000:
            combined = combined[:2000]

        # Generate embedding
        embedding = self.embedder.encode(combined).tolist()

        # Compile DNA (optional, costs ~$0.0002 per call)
        dna = ""
        if use_groq:
            # Use a summary for DNA compilation (cheaper, more focused)
            summary = f"{turn.question[:200]} → {turn.answer[:300]}"
            try:
                dna = compile_to_dna(summary)
            except Exception:
                dna = "(conversation)::{E:SER|T:LIN|C:MOD}"

        # Create spore ID
        spore_id = f"conv_{turn.session_id[:8]}_{turn.turn_number}_{int(turn.timestamp) % 100000}"

        # Store
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
                "synaptic_links": "[]"
            }]
        )

        # Find and create synaptic links
        self._link_resonant(spore_id, embedding)

        return spore_id

    def ingest_json(self, data: dict, use_groq: bool = True) -> str:
        """Ingest from the JSON schema format.

        Expected format:
        {
            "session_id": "...",
            "timestamp": 123.456,
            "turn_number": 1,
            "question": {"text": "...", "source": "neo-console"},
            "answer": {"text": "...", "tools_used": [...], "thinking": "..."},
            "stats": {"input_tokens": 0, "output_tokens": 0, ...},
            "model": "opus"
        }
        """
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
            source=q.get("source", "unknown") if isinstance(q, dict) else "unknown"
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

    def recall(self, query: str, n: int = 5) -> List[Dict]:
        """Recall memories by semantic similarity to a query."""
        embedding = self.embedder.encode(query).tolist()

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n
        )

        memories = []
        if results["ids"][0]:
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
                metadatas=[{"energy": new_energy}]
            )

        self.dream_count += 1
        return dream_cluster

    def stats(self) -> Dict:
        """Get cortex statistics."""
        all_data = self.collection.get()
        if not all_data["ids"]:
            return {"total": 0, "dreams": self.dream_count}

        energies = [m.get("energy", 1.0) for m in all_data["metadatas"]]
        sessions = set(m.get("session_id", "") for m in all_data["metadatas"])

        return {
            "total_memories": len(all_data["ids"]),
            "sessions": len(sessions),
            "avg_energy": round(sum(energies) / len(energies), 3),
            "max_energy": round(max(energies), 3),
            "min_energy": round(min(energies), 3),
            "dreams": self.dream_count
        }

    def _link_resonant(self, spore_id: str, embedding: list, top_n: int = 2):
        """Find and link semantically similar memories."""
        if self.collection.count() < 2:
            return

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_n + 1
        )

        links = [sid for sid in results["ids"][0] if sid != spore_id][:top_n]
        if links:
            self.collection.update(
                ids=[spore_id],
                metadatas=[{"synaptic_links": json.dumps(links)}]
            )


if __name__ == "__main__":
    print("ConversationCortex - Quick Test")
    print("=" * 50)

    cortex = ConversationCortex(persist_dir="./test_conv_cortex_db")

    # Simulate conversation turns
    turns = [
        {
            "session_id": "test-session-001",
            "timestamp": time.time(),
            "turn_number": 1,
            "question": {"text": "come stai dopo il restart?", "source": "neo-console"},
            "answer": {"text": "Ci sono. Memory bank caricata. neo-console completo, moltbook post pubblicato, ai2ai focus su memory-rag.", "tools_used": ["Read"]},
            "model": "opus"
        },
        {
            "session_id": "test-session-001",
            "timestamp": time.time() + 60,
            "turn_number": 2,
            "question": {"text": "che dicono i nostri post su moltbook?", "source": "neo-console"},
            "answer": {"text": "Il post DNA ritorna 404, post not found. Il feed e dominato da bot con 887k fake upvotes. Moltbook e un disastro di sicurezza secondo Wiz e 404Media.", "tools_used": ["Bash"]},
            "model": "opus"
        },
        {
            "session_id": "test-session-001",
            "timestamp": time.time() + 120,
            "turn_number": 3,
            "question": {"text": "la nostra memory bank come e rispetto ai paper?", "source": "neo-console"},
            "answer": {"text": "MBEL compression 75% e originale, nessun paper lo fa. Struttura file chiara. Manca retrieval automatico, nessun embedding, nessun decay. A 1000 righe funziona, a 5000 non scala.", "tools_used": ["Read", "Bash"]},
            "model": "opus"
        },
        {
            "session_id": "test-session-001",
            "timestamp": time.time() + 180,
            "turn_number": 4,
            "question": {"text": "come funziona il flusso MB e ai2ai insieme?", "source": "neo-console"},
            "answer": {"text": "MB e working memory veloce. ai2ai memory-rag e long term con chromaDB embeddings e dream cycles. Come il sonno consolida i ricordi. Il ponte manca ancora.", "tools_used": []},
            "model": "opus"
        },
        {
            "session_id": "test-session-001",
            "timestamp": time.time() + 240,
            "turn_number": 5,
            "question": {"text": "il crash di neo-console come lo abbiamo fixato?", "source": "neo-console"},
            "answer": {"text": "Il stdout reader crashava perche tool_use_result era stringa invece di oggetto. Fix: catch Exception non solo JsonException, aggiunto ExtractToolOutput con check ValueKind, SanitizeInput, JSON validation prima di stdin write.", "tools_used": ["Read", "Edit"]},
            "model": "opus"
        }
    ]

    print(f"\n--- Ingesting {len(turns)} conversation turns ---")
    for t in turns:
        sid = cortex.ingest_json(t, use_groq=True)
        q = t["question"]["text"][:50]
        print(f"  [{sid}] Q: {q}")

    print(f"\n--- Recall: 'moltbook post sicurezza' ---")
    for m in cortex.recall("moltbook post sicurezza", n=3):
        print(f"  [{m['similarity']:.3f}] Q: {m['question'][:60]}")
        print(f"           DNA: {m['dna'][:70]}")

    print(f"\n--- Recall: 'crash bug stdout fix' ---")
    for m in cortex.recall("crash bug stdout fix", n=3):
        print(f"  [{m['similarity']:.3f}] Q: {m['question'][:60]}")
        print(f"           DNA: {m['dna'][:70]}")

    print(f"\n--- Recall: 'memory architecture two tier' ---")
    for m in cortex.recall("memory architecture two tier", n=3):
        print(f"  [{m['similarity']:.3f}] Q: {m['question'][:60]}")
        print(f"           DNA: {m['dna'][:70]}")

    print(f"\n--- Dream cycle ---")
    cluster = cortex.dream_cycle()
    print(f"  Cluster: {cluster}")

    print(f"\n--- Stats ---")
    for k, v in cortex.stats().items():
        print(f"  {k}: {v}")
