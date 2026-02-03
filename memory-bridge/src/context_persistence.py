"""
Context Persistence using Memory Spore DNA
Encode conversation context into living memory DNA and retrieve it
"""

import json
import time
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime
from memome_codex import MEMOME_CODEX, parse_dna_sequence

class ContextPersistence:
    """Persist and retrieve context using Memory DNA encoding"""
    
    def __init__(self, db_path: str = "memory_context.db"):
        self.db_path = db_path
        self.init_database()
        
        # Context type to codon mappings
        self.context_mappings = {
            # Emotional context
            "excited": "E:JOY",
            "calm": "E:SER",
            "frustrated": "E:ANG",
            "confused": "E:FEA",
            "amazed": "E:AWE",
            "sad": "E:SAD",
            
            # Temporal context
            "just_started": "T:ERU",
            "ongoing": "T:LIN",
            "repeated": "T:CYC",
            "ending": "T:DEC",
            "frozen": "T:STA",
            
            # Cognitive context
            "simple": "C:SNG",
            "complex": "C:DNS",
            "abstract": "C:SPR",
            
            # Activity context
            "exploring": "Ψ:DRM",
            "focused": "Ψ:ALR",
            "reflecting": "Ψ:MED",
            "discovering": "Ψ:EMR",
            
            # Communication style
            "flowing": "F:∞",
            "sharp": "F:Δ!",
            "rhythmic": "F:══▶",
            "resonant": "F:≈≈"
        }
    
    def init_database(self):
        """Initialize context storage"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS context_memories (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                timestamp REAL,
                raw_context TEXT,
                dna_sequence TEXT,
                core_concepts TEXT,
                energy_level REAL DEFAULT 1.0,
                retrieved_count INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()
    
    def analyze_context(self, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze context and determine relevant codons"""
        codons = []
        concepts = []
        
        # Analyze current state
        if "user_emotion" in context_data:
            emotion = context_data["user_emotion"].lower()
            if emotion in self.context_mappings:
                codons.append(self.context_mappings[emotion])
        
        if "task_complexity" in context_data:
            complexity = context_data["task_complexity"].lower()
            if complexity in self.context_mappings:
                codons.append(self.context_mappings[complexity])
        
        if "interaction_stage" in context_data:
            stage = context_data["interaction_stage"].lower()
            if stage in self.context_mappings:
                codons.append(self.context_mappings[stage])
        
        # Extract key concepts
        if "main_topics" in context_data:
            concepts = context_data["main_topics"][:3]  # Top 3 concepts
        
        # Analyze conversation flow
        if "conversation_style" in context_data:
            style = context_data["conversation_style"].lower()
            if style in self.context_mappings:
                codons.append(self.context_mappings[style])
        
        return {
            "codons": codons,
            "concepts": concepts
        }
    
    def encode_context_to_dna(self, context_data: Dict[str, Any]) -> str:
        """Encode context into Memory DNA format"""
        analysis = self.analyze_context(context_data)
        
        # Create core concept
        if analysis["concepts"]:
            core_concept = f"({','.join(analysis['concepts'])})"
        else:
            core_concept = "(context)"
        
        # Create codon sequence
        if analysis["codons"]:
            codon_string = "|".join(analysis["codons"])
        else:
            codon_string = "C:SNG|T:STA"  # Default: simple, static
        
        dna_sequence = f"{core_concept}::{{{codon_string}}}"
        return dna_sequence
    
    def persist_context(self, session_id: str, context_data: Dict[str, Any]) -> str:
        """Persist context as Memory DNA"""
        # Encode to DNA
        dna_sequence = self.encode_context_to_dna(context_data)
        
        # Extract concepts for storage
        analysis = self.analyze_context(context_data)
        concepts_json = json.dumps(analysis["concepts"])
        
        # Store in database
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO context_memories 
            (session_id, timestamp, raw_context, dna_sequence, core_concepts)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            session_id,
            time.time(),
            json.dumps(context_data),
            dna_sequence,
            concepts_json
        ))
        conn.commit()
        conn.close()
        
        return dna_sequence
    
    def retrieve_context(self, session_id: Optional[str] = None, 
                        concepts: Optional[List[str]] = None,
                        time_window: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve context memories by various criteria"""
        conn = sqlite3.connect(self.db_path)
        
        query = "SELECT * FROM context_memories WHERE 1=1"
        params = []
        
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        
        if concepts:
            # Search for any matching concept
            concept_conditions = []
            for concept in concepts:
                concept_conditions.append("core_concepts LIKE ?")
                params.append(f"%{concept}%")
            query += f" AND ({' OR '.join(concept_conditions)})"
        
        if time_window:
            # Get contexts from last N seconds
            query += " AND timestamp > ?"
            params.append(time.time() - time_window)
        
        query += " ORDER BY timestamp DESC LIMIT 10"
        
        cursor = conn.execute(query, params)
        results = []
        
        for row in cursor.fetchall():
            # Parse DNA to get detailed info
            dna_sequence = row[4]
            parsed_dna = parse_dna_sequence(dna_sequence)
            
            # Increment retrieval count
            conn.execute(
                "UPDATE context_memories SET retrieved_count = retrieved_count + 1 WHERE id = ?",
                (row[0],)
            )
            
            results.append({
                "session_id": row[1],
                "timestamp": row[2],
                "raw_context": json.loads(row[3]),
                "dna_sequence": dna_sequence,
                "parsed_dna": {
                    "core_concept": parsed_dna.core_concept,
                    "codons": parsed_dna.codons
                },
                "energy_level": row[6],
                "retrieved_count": row[7]
            })
        
        conn.commit()
        conn.close()
        return results
    
    def decode_dna_to_context(self, dna_sequence: str) -> Dict[str, Any]:
        """Decode DNA back into human-readable context"""
        parsed = parse_dna_sequence(dna_sequence)
        
        # Reverse mapping from codons to context
        reverse_mapping = {v: k for k, v in self.context_mappings.items()}
        
        decoded = {
            "main_topics": parsed.core_concept.strip("()").split(","),
            "context_attributes": []
        }
        
        for codon in parsed.codons:
            if codon in reverse_mapping:
                decoded["context_attributes"].append(reverse_mapping[codon])
            else:
                # Interpret codon meaning
                namespace, value = codon.split(":", 1) if ":" in codon else ("?", codon)
                if namespace == "E":
                    decoded["emotion"] = value.lower()
                elif namespace == "T":
                    decoded["temporal"] = value.lower()
                elif namespace == "C":
                    decoded["complexity"] = value.lower()
                elif namespace == "Ψ":
                    decoded["consciousness"] = value.lower()
                elif namespace == "F":
                    decoded["frequency"] = value
        
        return decoded

def demo_context_persistence():
    """Demonstrate context persistence and retrieval"""
    print("🧬 Context Persistence Demo - Living Memory DNA")
    print("=" * 60)
    
    persister = ContextPersistence()
    session_id = f"session_{int(time.time())}"
    
    # Example 1: Persist current conversation context
    print("\n📝 Persisting current context...")
    
    context1 = {
        "user_emotion": "amazed",
        "task_complexity": "complex", 
        "interaction_stage": "ongoing",
        "main_topics": ["memory", "evolution", "DNA"],
        "conversation_style": "flowing",
        "user_message": "how it works? how we can use it?",
        "ai_focus": "explaining living memory system"
    }
    
    dna1 = persister.persist_context(session_id, context1)
    print(f"✅ Context encoded to DNA: {dna1}")
    
    # Example 2: Different context state
    print("\n📝 Persisting evolved context...")
    
    context2 = {
        "user_emotion": "excited",
        "task_complexity": "complex",
        "interaction_stage": "discovering", 
        "main_topics": ["reproduction", "weaver", "anticipation"],
        "conversation_style": "sharp",
        "user_discovery": "memories can reproduce and evolve"
    }
    
    dna2 = persister.persist_context(session_id, context2)
    print(f"✅ Context encoded to DNA: {dna2}")
    
    # Example 3: Retrieve contexts
    print("\n🔍 Retrieving contexts about 'memory'...")
    
    memories = persister.retrieve_context(concepts=["memory"])
    
    for memory in memories:
        print(f"\n📚 Retrieved Memory:")
        print(f"   DNA: {memory['dna_sequence']}")
        print(f"   Topics: {memory['parsed_dna']['core_concept']}")
        print(f"   Codons: {' | '.join(memory['parsed_dna']['codons'])}")
        
        # Decode back to human-readable
        decoded = persister.decode_dna_to_context(memory['dna_sequence'])
        print(f"   Decoded: {decoded}")
    
    # Example 4: Retrieve by session
    print(f"\n🔍 Retrieving all contexts from session...")
    
    session_memories = persister.retrieve_context(session_id=session_id)
    print(f"Found {len(session_memories)} context memories in this session")
    
    # Show evolution of context
    if len(session_memories) >= 2:
        print("\n🧬 Context Evolution:")
        for i, memory in enumerate(session_memories):
            concepts = memory['parsed_dna']['core_concept']
            codons = memory['parsed_dna']['codons']
            print(f"   Step {i+1}: {concepts} - Mood: {codons[0] if codons else 'unknown'}")
    
    print("\n✨ Context successfully persisted and retrieved using Memory DNA!")

if __name__ == "__main__":
    demo_context_persistence()