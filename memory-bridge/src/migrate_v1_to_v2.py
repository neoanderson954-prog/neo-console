#!/usr/bin/env python3
"""
Migrate cortex v1 → v2.

Reads all memories from 'conversations' collection (v1, MiniLM embeddings),
re-embeds them with Jina v3, classifies with Groq, and stores in
'conversations_v2' collection.

Usage:
    python migrate_v1_to_v2.py [--dry-run] [--no-groq] [--batch-size N]
"""

import os
import sys
import json
import time
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chromadb
from chromadb.config import Settings
from jina_embedder import JinaEmbedder
from groq_compiler import compile_to_dna, classify_memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("migrate")

DEFAULT_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cortex_db",
)


def migrate(db_dir: str, dry_run: bool = False, use_groq: bool = True, batch_size: int = 32):
    """Migrate v1 → v2."""
    client = chromadb.PersistentClient(
        path=db_dir,
        settings=Settings(anonymized_telemetry=False),
    )

    # Source: v1 collection
    try:
        v1 = client.get_collection("conversations")
    except Exception:
        logger.error("No 'conversations' collection found — nothing to migrate.")
        return

    # Destination: v2 collection
    try:
        v2 = client.get_collection("conversations_v2")
        v2_existing = set(v2.get()["ids"]) if v2.count() > 0 else set()
    except Exception:
        v2 = client.create_collection(
            "conversations_v2",
            metadata={"hnsw:space": "cosine"},
        )
        v2_existing = set()

    # Read all v1 data
    v1_data = v1.get(include=["documents", "metadatas"])
    total = len(v1_data["ids"])
    logger.info(f"Found {total} memories in v1")
    logger.info(f"Already in v2: {len(v2_existing)}")

    # Filter out already-migrated
    to_migrate = []
    for i, sid in enumerate(v1_data["ids"]):
        v2_id = f"v2_{sid[5:]}" if sid.startswith("conv_") else f"v2_{sid}"
        if v2_id in v2_existing:
            continue
        to_migrate.append({
            "v1_id": sid,
            "v2_id": v2_id,
            "document": v1_data["documents"][i] if v1_data["documents"] else "",
            "metadata": v1_data["metadatas"][i],
        })

    logger.info(f"To migrate: {len(to_migrate)}")

    if dry_run:
        for item in to_migrate[:5]:
            q = item["metadata"].get("question", "")[:60]
            logger.info(f"  [DRY] {item['v1_id']} → {item['v2_id']} | Q: {q}")
        if len(to_migrate) > 5:
            logger.info(f"  ... and {len(to_migrate) - 5} more")
        return

    if not to_migrate:
        logger.info("Nothing to migrate — all caught up.")
        return

    # Initialize Jina embedder
    embedder = JinaEmbedder()

    # Process in batches
    migrated = 0
    errors = 0

    for batch_start in range(0, len(to_migrate), batch_size):
        batch = to_migrate[batch_start:batch_start + batch_size]
        logger.info(f"Batch {batch_start // batch_size + 1}: {len(batch)} memories")

        # Batch embed with Jina
        documents = [item["document"] for item in batch]
        try:
            embeddings = embedder.embed_passages_batch(documents, batch_size=batch_size)
        except Exception as e:
            logger.error(f"Jina batch embed failed: {e}")
            errors += len(batch)
            continue

        # Process each item
        for i, item in enumerate(batch):
            meta = item["metadata"]
            question = meta.get("question", "")
            answer = meta.get("answer_preview", "")

            # Classify via Groq (one call per memory)
            classification = {"project": "general", "topic": "unknown", "activity": "discussion"}
            if use_groq:
                try:
                    classification = classify_memory(question, answer)
                    # Rate limit: Groq free tier
                    time.sleep(0.3)
                except Exception as e:
                    logger.warning(f"Classification failed for {item['v2_id']}: {e}")

            # Build v2 metadata (carry over v1 fields + add new ones)
            v2_meta = {
                "session_id": meta.get("session_id", ""),
                "timestamp": meta.get("timestamp", 0),
                "turn_number": meta.get("turn_number", 0),
                "question": question[:500],
                "answer_preview": answer[:500],
                "tools_used": meta.get("tools_used", "[]"),
                "model": meta.get("model", "opus"),
                "dna": meta.get("dna", ""),
                "energy": meta.get("energy", 1.0),
                "source": meta.get("source", "neo-console"),
                "project": classification["project"],
                "topic": classification["topic"],
                "activity": classification["activity"],
                "synaptic_links": "[]",
                "migrated_from": item["v1_id"],
            }

            try:
                v2.add(
                    ids=[item["v2_id"]],
                    embeddings=[embeddings[i]],
                    documents=[item["document"]],
                    metadatas=[v2_meta],
                )
                migrated += 1
                q_short = question[:50]
                logger.info(f"  [{migrated}/{len(to_migrate)}] {item['v2_id']} | {classification['project']}:{classification['topic']} | Q: {q_short}")
            except Exception as e:
                logger.error(f"  Failed to store {item['v2_id']}: {e}")
                errors += 1

    logger.info(f"\nMigration complete: {migrated} migrated, {errors} errors")
    logger.info(f"V2 collection now has {v2.count()} memories")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate cortex v1 → v2")
    parser.add_argument("--db-dir", default=DEFAULT_DB_DIR, help="ChromaDB directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated")
    parser.add_argument("--no-groq", action="store_true", help="Skip Groq classification")
    parser.add_argument("--batch-size", type=int, default=32, help="Jina batch size")
    args = parser.parse_args()

    migrate(
        db_dir=args.db_dir,
        dry_run=args.dry_run,
        use_groq=not args.no_groq,
        batch_size=args.batch_size,
    )
