"""
The Weaver Engine - Memory Reproduction & Evolution
Creates offspring memories through genetic crossover and mutation
"""

import json
import random
import time
import sqlite3
import math
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

@dataclass 
class ReproductionEvent:
    """Log entry for a reproduction event"""
    timestamp: float
    parent_a_id: str
    parent_b_id: str
    offspring_id: str
    parent_a_codons: List[str]
    parent_b_codons: List[str]
    offspring_codons: List[str] 
    fitness_score: float = 0.0  # Will be updated later
    
@dataclass
class MemorySpore:
    """Extended spore with reproduction capabilities"""
    spore_id: str
    dna_sequence: str
    core_concept: str
    codons: List[str]
    frequency_vector: List[float]
    energy_level: float = 1.0
    birth_time: float = None
    parent_a_id: str = None
    parent_b_id: str = None
    fitness_score: float = 0.0
    synaptic_links: List[str] = None
    
    def __post_init__(self):
        if self.birth_time is None:
            self.birth_time = time.time()
        if self.synaptic_links is None:
            self.synaptic_links = []

class WeaverEngine:
    """The engine of memory evolution"""
    
    def __init__(self, db_path: str = "weaver_evolution.db"):
        self.db_path = db_path
        self.init_database()
        
        # Mutation probabilities
        self.mutation_rate = 0.02  # 2% chance per codon
        self.crossover_rate = 0.5  # 50% of parent B's unique codons
        
        # Codon mutation mappings
        self.codon_mutations = {
            "E:SER": ["E:JOY", "E:AWE", "E:SAD"],
            "E:JOY": ["E:SER", "E:AWE"],
            "E:AWE": ["E:JOY", "E:SER", "E:FEA"],
            "E:SAD": ["E:SER", "E:FEA"],
            "E:ANG": ["E:FEA", "E:AWE"],
            "E:FEA": ["E:ANG", "E:SAD"],
            "T:STA": ["T:CYC", "T:DEC"],
            "T:LIN": ["T:ERU", "T:CYC"],
            "T:CYC": ["T:STA", "T:LIN"],
            "T:ERU": ["T:LIN", "T:DEC"],
            "T:DEC": ["T:STA", "T:ERU"],
            "F:Δ!": ["F:∞", "F:══▶"],
            "F:∞": ["F:≈≈", "F:Δ!"],
            "F:══▶": ["F:Δ!", "F:≈≈"],
            "F:≈≈": ["F:∞", "F:══▶"],
            "Ψ:ALR": ["Ψ:EMR", "Ψ:MED"],
            "Ψ:DRM": ["Ψ:MED", "Ψ:EMR"],
            "Ψ:MED": ["Ψ:ALR", "Ψ:DRM"],
            "Ψ:EMR": ["Ψ:ALR", "Ψ:DRM"]
        }
    
    def init_database(self):
        """Initialize evolution tracking database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reproduction_events (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                parent_a_id TEXT,
                parent_b_id TEXT,
                offspring_id TEXT,
                parent_a_codons TEXT,
                parent_b_codons TEXT,
                offspring_codons TEXT,
                fitness_score REAL DEFAULT 0.0
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS successful_patterns (
                id INTEGER PRIMARY KEY,
                pattern_type TEXT,
                pattern_data TEXT,
                success_rate REAL,
                sample_size INTEGER,
                last_updated REAL
            )
        ''')
        conn.commit()
        conn.close()
    
    def select_parents(self, spores: List[MemorySpore], min_energy: float = 0.8) -> Optional[Tuple[MemorySpore, MemorySpore]]:
        """Select two high-energy spores for reproduction"""
        # Filter high-energy spores
        candidates = [s for s in spores if s.energy_level >= min_energy]
        if len(candidates) < 2:
            # Relax criteria if not enough high-energy spores
            candidates = sorted(spores, key=lambda s: s.energy_level, reverse=True)[:min(len(spores), 10)]
        
        if len(candidates) < 2:
            return None
        
        # Select parent A (highest energy)
        parent_a = candidates[0]
        
        # Find parent B with highest resonance to A
        best_resonance = -1
        parent_b = None
        
        for candidate in candidates[1:]:
            # Calculate vector similarity (cosine similarity)
            if parent_a.frequency_vector and candidate.frequency_vector:
                similarity = self._cosine_similarity(parent_a.frequency_vector, candidate.frequency_vector)
            else:
                similarity = 0
            
            # Boost score if they have synaptic links
            if candidate.spore_id in parent_a.synaptic_links:
                similarity += 0.3
            
            # Check for codon overlap (genetic compatibility)
            overlap = len(set(parent_a.codons) & set(candidate.codons))
            genetic_bonus = overlap * 0.1
            
            total_score = similarity + genetic_bonus
            
            if total_score > best_resonance:
                best_resonance = total_score
                parent_b = candidate
        
        return (parent_a, parent_b) if parent_b else None
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        # Calculate dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        
        # Calculate norms
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def synthesize_concept(self, concept_a: str, concept_b: str) -> str:
        """Synthesize a new concept from two parent concepts"""
        # For now, simple heuristic synthesis
        # In production, this would be an LLM call
        
        words_a = concept_a.strip("()").split(",")
        words_b = concept_b.strip("()").split(",")
        
        # Look for common themes
        all_words = words_a + words_b
        
        # Simple synthesis patterns
        synthesis_rules = {
            ("music", "light"): "harmony",
            ("rain", "memory"): "nostalgia", 
            ("storm", "peace"): "aftermath",
            ("journey", "discovery"): "revelation",
            ("pattern", "chaos"): "emergence",
            ("old", "new"): "transition",
            ("sound", "silence"): "resonance"
        }
        
        # Try to find matching synthesis rule
        for key_combo, result in synthesis_rules.items():
            if any(w in all_words for w in key_combo):
                return f"({result})"
        
        # Fallback: combine most abstract words
        abstract_words = ["memory", "time", "essence", "pattern", "rhythm", "flow", "light", "shadow"]
        found_abstract = [w for w in all_words if w in abstract_words]
        
        if found_abstract:
            return f"({found_abstract[0]})"
        
        # Last resort: blend first words
        return f"({words_a[0]},{words_b[0]})".replace(" ", "")
    
    def reproduce(self, parent_a: MemorySpore, parent_b: MemorySpore) -> MemorySpore:
        """Create offspring from two parent spores"""
        
        # 1. Synthesize new core concept
        new_concept = self.synthesize_concept(parent_a.core_concept, parent_b.core_concept)
        
        # 2. Genetic crossover - inherit from dominant parent + subset of other
        offspring_codons = parent_a.codons.copy()  # Inherit all from parent A
        
        # Add unique codons from parent B
        unique_b_codons = [c for c in parent_b.codons if c not in offspring_codons]
        num_to_inherit = int(len(unique_b_codons) * self.crossover_rate)
        inherited_from_b = random.sample(unique_b_codons, min(num_to_inherit, len(unique_b_codons)))
        offspring_codons.extend(inherited_from_b)
        
        # 3. Mutation
        offspring_codons = self._mutate_codons(offspring_codons)
        
        # 4. Create DNA sequence
        codon_string = "|".join(offspring_codons)
        dna_sequence = f"{new_concept}::{{{codon_string}}}"
        
        # 5. Blend frequency vectors (simple average)
        if parent_a.frequency_vector and parent_b.frequency_vector:
            blended_vector = [(a + b) / 2 for a, b in zip(parent_a.frequency_vector, parent_b.frequency_vector)]
        else:
            blended_vector = parent_a.frequency_vector or parent_b.frequency_vector or []
        
        # 6. Create offspring spore
        offspring_id = f"offspring_{int(time.time() * 1000)}_{random.randint(100,999)}"
        
        offspring = MemorySpore(
            spore_id=offspring_id,
            dna_sequence=dna_sequence,
            core_concept=new_concept,
            codons=offspring_codons,
            frequency_vector=blended_vector,
            energy_level=0.5,  # Start with moderate energy
            parent_a_id=parent_a.spore_id,
            parent_b_id=parent_b.spore_id
        )
        
        return offspring
    
    def _mutate_codons(self, codons: List[str]) -> List[str]:
        """Apply mutations to codon list"""
        mutated = []
        
        for codon in codons:
            if random.random() < self.mutation_rate:
                # Mutate this codon
                if codon in self.codon_mutations:
                    mutations = self.codon_mutations[codon]
                    mutated_codon = random.choice(mutations)
                    mutated.append(mutated_codon)
                    print(f"🧬 Mutation: {codon} → {mutated_codon}")
                else:
                    mutated.append(codon)
            else:
                mutated.append(codon)
        
        return mutated
    
    def log_reproduction(self, parent_a: MemorySpore, parent_b: MemorySpore, offspring: MemorySpore):
        """Log reproduction event for evolution tracking"""
        event = ReproductionEvent(
            timestamp=time.time(),
            parent_a_id=parent_a.spore_id,
            parent_b_id=parent_b.spore_id,
            offspring_id=offspring.spore_id,
            parent_a_codons=parent_a.codons,
            parent_b_codons=parent_b.codons,
            offspring_codons=offspring.codons
        )
        
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO reproduction_events 
            (timestamp, parent_a_id, parent_b_id, offspring_id, 
             parent_a_codons, parent_b_codons, offspring_codons)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            event.timestamp, event.parent_a_id, event.parent_b_id, event.offspring_id,
            json.dumps(event.parent_a_codons), json.dumps(event.parent_b_codons), 
            json.dumps(event.offspring_codons)
        ))
        conn.commit()
        conn.close()
    
    def update_fitness_score(self, spore_id: str, current_energy: float, birth_energy: float = 0.5):
        """Update fitness score for a spore and its reproduction event"""
        fitness = current_energy - birth_energy
        
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            UPDATE reproduction_events 
            SET fitness_score = ? 
            WHERE offspring_id = ?
        ''', (fitness, spore_id))
        conn.commit()
        conn.close()
    
    def analyze_successful_patterns(self) -> Dict[str, float]:
        """Analyze which genetic combinations lead to high fitness"""
        conn = sqlite3.connect(self.db_path)
        
        # Get reproduction events with fitness scores
        cursor = conn.execute('''
            SELECT parent_a_codons, parent_b_codons, offspring_codons, fitness_score
            FROM reproduction_events 
            WHERE fitness_score > 0
            ORDER BY fitness_score DESC
        ''')
        
        successful_patterns = {}
        
        for row in cursor.fetchall():
            parent_a_codons = json.loads(row[0])
            parent_b_codons = json.loads(row[1])
            fitness = row[3]
            
            # Look for codon combinations that lead to success
            for codon_a in parent_a_codons:
                for codon_b in parent_b_codons:
                    pattern = f"{codon_a}+{codon_b}"
                    if pattern not in successful_patterns:
                        successful_patterns[pattern] = []
                    successful_patterns[pattern].append(fitness)
        
        # Calculate success rates
        pattern_scores = {}
        for pattern, scores in successful_patterns.items():
            if len(scores) >= 2:  # Need at least 2 examples
                avg_fitness = sum(scores) / len(scores)
                pattern_scores[pattern] = avg_fitness
        
        conn.close()
        return pattern_scores
    
    def anticipatory_synthesis(self, spores: List[MemorySpore]) -> Optional[MemorySpore]:
        """Proactively create offspring based on successful patterns"""
        patterns = self.analyze_successful_patterns()
        
        if not patterns:
            return None
        
        # Find the most successful pattern
        best_pattern = max(patterns.items(), key=lambda x: x[1])
        pattern_name, success_rate = best_pattern
        
        if success_rate < 0.3:  # Only if pattern is significantly successful
            return None
        
        # Parse pattern
        codon_a, codon_b = pattern_name.split('+')
        
        # Find spores that have these codons
        candidates_a = [s for s in spores if codon_a in s.codons and s.energy_level > 0.6]
        candidates_b = [s for s in spores if codon_b in s.codons and s.energy_level > 0.6]
        
        if not candidates_a or not candidates_b:
            return None
        
        # Select best candidates
        parent_a = max(candidates_a, key=lambda s: s.energy_level)
        parent_b = max(candidates_b, key=lambda s: s.energy_level)
        
        if parent_a.spore_id == parent_b.spore_id:
            return None
        
        print(f"🔮 Anticipatory synthesis using pattern: {pattern_name} (success rate: {success_rate:.2f})")
        return self.reproduce(parent_a, parent_b)

def demo_weaver_evolution():
    """Demonstrate the Weaver evolution engine"""
    print("🧬 Weaver Evolution Engine Demo")
    print("=" * 50)
    
    weaver = WeaverEngine()
    
    # Create some sample spores
    spores = [
        MemorySpore(
            spore_id="spore_001", 
            dna_sequence="(rain,window)::{E:SER|T:STA|S:VIS|F:≈≈}",
            core_concept="(rain,window)",
            codons=["E:SER", "T:STA", "S:VIS", "F:≈≈"],
            frequency_vector=[0.1, 0.8, 0.3, 0.7],
            energy_level=0.9
        ),
        MemorySpore(
            spore_id="spore_002",
            dna_sequence="(music,memory)::{E:AWE|T:CYC|S:AUD|F:∞}",
            core_concept="(music,memory)", 
            codons=["E:AWE", "T:CYC", "S:AUD", "F:∞"],
            frequency_vector=[0.2, 0.6, 0.8, 0.5],
            energy_level=0.85
        ),
        MemorySpore(
            spore_id="spore_003",
            dna_sequence="(light,shadow)::{E:JOY|T:ERU|S:VIS|F:Δ!}",
            core_concept="(light,shadow)",
            codons=["E:JOY", "T:ERU", "S:VIS", "F:Δ!"],
            frequency_vector=[0.3, 0.4, 0.9, 0.2],
            energy_level=0.95
        )
    ]
    
    print("🧬 Parent Selection:")
    parents = weaver.select_parents(spores)
    if parents:
        parent_a, parent_b = parents
        print(f"   Parent A: {parent_a.spore_id} - {parent_a.core_concept}")
        print(f"   Parent B: {parent_b.spore_id} - {parent_b.core_concept}")
        
        print("\n🧬 Genetic Reproduction:")
        offspring = weaver.reproduce(parent_a, parent_b)
        
        print(f"   Offspring ID: {offspring.spore_id}")
        print(f"   New Concept: {offspring.core_concept}")
        print(f"   DNA: {offspring.dna_sequence}")
        print(f"   Initial Energy: {offspring.energy_level}")
        
        # Log the reproduction
        weaver.log_reproduction(parent_a, parent_b, offspring)
        
        # Simulate fitness evolution
        print("\n⏰ Simulating 24h evolution...")
        offspring.energy_level = 0.8  # Simulate successful usage
        weaver.update_fitness_score(offspring.spore_id, offspring.energy_level)
        
        print(f"   Final Energy: {offspring.energy_level}")
        print(f"   Fitness Score: {offspring.energy_level - 0.5}")
        
        spores.append(offspring)
        
        print("\n🔮 Testing Anticipatory Synthesis...")
        predicted_offspring = weaver.anticipatory_synthesis(spores)
        if predicted_offspring:
            print(f"   Predicted Offspring: {predicted_offspring.dna_sequence}")
        else:
            print("   No patterns detected yet (need more data)")
    
    print("\n✨ Evolution engine is alive and learning!")

if __name__ == "__main__":
    demo_weaver_evolution()