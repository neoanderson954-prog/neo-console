"""
Genesis Engine v0.1
Transforms text into Memory Spores through DNA encoding and phenotype expression
"""

import json
import asyncio
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import ollama
from memome_codex import (
    ParsedDNA, parse_dna_sequence, MEMOME_CODEX, 
    CODON_TO_PROMPT, validate_codon
)

@dataclass
class MemorySpore:
    """A living memory unit"""
    spore_id: str
    dna_sequence: str
    frequency_vector: Optional[List[float]] = None
    phenotype_prompt: Optional[str] = None
    stimulus: Optional[str] = None
    energy_level: float = 1.0
    synaptic_links: List[str] = None
    
    def __post_init__(self):
        if self.synaptic_links is None:
            self.synaptic_links = []

class MemomeCompiler:
    """The Seer v0.1 - Compiles text into DNA sequences"""
    
    def __init__(self, model_name: str = "mistral:latest"):
        self.model_name = model_name
        self.compiler_prompt = self._create_compiler_prompt()
    
    def _create_compiler_prompt(self) -> str:
        """Generate the system prompt for the compiler"""
        codex_text = "**Codon Dictionary v0.2:**\n"
        
        for namespace, codons in MEMOME_CODEX.items():
            codon_list = []
            for symbol, desc in codons.items():
                codon_list.append(f"{symbol} ({desc})")
            codex_text += f"* **{namespace}**: {', '.join(codon_list)}\n"
        
        return f"""You are a Memome Compiler. Your sole function is to convert text into a structured dna_sequence.

Format: (core_concept)::{{[NAMESPACE:CODON|...]}}
- core_concept: 1-3 word essence
- Multiple codons separated by |
- Use transitions like E:ANG→AWE for changes
- Use relations like R:(concept1)⚔(concept2) for dynamics

{codex_text}

Analyze deeply for:
1. Emotional journey (E namespace)
2. Temporal flow (T namespace)  
3. Conceptual structure (C namespace)
4. Sensory dominance (S namespace)
5. Frequency/energy (F namespace)
6. Consciousness state (Ψ namespace)
7. Relationships between concepts (R namespace)

Output ONLY the dna_sequence, nothing else."""
    
    async def compile_to_dna(self, text: str) -> str:
        """Compile text into a DNA sequence"""
        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=f"{self.compiler_prompt}\n\n**Text:** \"{text}\"",
                options={
                    "temperature": 0.7,
                    "num_predict": 200
                }
            )
            
            dna = response['response'].strip()
            # Validate by parsing
            parsed = parse_dna_sequence(dna)
            return dna
            
        except Exception as e:
            print(f"Compilation error: {e}")
            # Fallback to simple DNA
            return "(unknown)::{{E:AWE|T:STA|C:SNG}}"

class PhenotypeInterpreter:
    """The Dreamer v0.1 - Interprets DNA into generative prompts"""
    
    def dna_to_phenotype_prompt(self, dna: ParsedDNA) -> str:
        """Convert DNA sequence into detailed image generation prompt"""
        # Start with core concept
        prompt_parts = [
            f"A surreal, artistic visualization of '{dna.core_concept}'."
        ]
        
        # Add codon interpretations
        for codon in dna.codons:
            if codon in CODON_TO_PROMPT:
                prompt_parts.append(CODON_TO_PROMPT[codon])
            elif '→' in codon:
                # Handle transitions
                parts = codon.split('→')
                if len(parts) == 2:
                    from_desc = CODON_TO_PROMPT.get(parts[0], parts[0])
                    to_desc = CODON_TO_PROMPT.get(parts[1], parts[1])
                    prompt_parts.append(
                        f"The scene transitions from {from_desc} to {to_desc}"
                    )
            elif any(op in codon for op in ['⚔', '⊕', '[]']):
                # Handle relational codons
                prompt_parts.append(self._interpret_relation(codon))
        
        # Add style modifiers based on frequency
        if dna.has_namespace('F'):
            freq_codons = dna.get_codons_by_namespace('F')
            if 'F:Δ!' in freq_codons:
                prompt_parts.append("Rendered in sharp, high-contrast style with extreme clarity")
            if 'F:∞' in freq_codons:
                prompt_parts.append("With flowing, infinite patterns that seem to continue forever")
            if 'F:══▶' in freq_codons:
                prompt_parts.append("Showing clear directional movement and progression")
            if 'F:≈≈' in freq_codons:
                prompt_parts.append("Multiple elements vibrating in visual harmony")
        
        # Add consciousness modifiers
        if dna.has_namespace('Ψ'):
            psi_codons = dna.get_codons_by_namespace('Ψ')
            if 'Ψ:DRM' in psi_codons:
                prompt_parts.append("In the style of a lucid dream or surrealist painting")
            if 'Ψ:EMR' in psi_codons:
                prompt_parts.append("Capturing the exact moment of revelation or discovery")
        
        return " ".join(prompt_parts)
    
    def _interpret_relation(self, codon: str) -> str:
        """Interpret relational codons"""
        if '⚔' in codon:
            match = re.match(r'R:\(([^)]+)\)⚔\(([^)]+)\)', codon)
            if match:
                return f"Showing conflict between {match.group(1)} and {match.group(2)}"
        elif '⊕' in codon:
            match = re.match(r'R:\(([^)]+)\)⊕\(([^)]+)\)', codon)
            if match:
                return f"With {match.group(1)} and {match.group(2)} in perfect harmony"
        elif '→' in codon and 'R:' in codon:
            match = re.match(r'R:\(([^)]+)\)→\(([^)]+)\)', codon)
            if match:
                return f"Depicting how {match.group(1)} transforms into {match.group(2)}"
        return ""

class GenesisEngine:
    """The complete engine for creating Memory Spores"""
    
    def __init__(self, compiler_model: str = "mistral:latest"):
        self.compiler = MemomeCompiler(compiler_model)
        self.interpreter = PhenotypeInterpreter()
        self.spore_count = 0
    
    async def create_spore(self, stimulus: str) -> MemorySpore:
        """Create a complete Memory Spore from text stimulus"""
        # Generate unique ID
        self.spore_count += 1
        spore_id = f"spore_{self.spore_count}_{hash(stimulus) % 10000}"
        
        # Compile to DNA
        print(f"🧬 Compiling stimulus to DNA...")
        dna_sequence = await self.compiler.compile_to_dna(stimulus)
        print(f"   DNA: {dna_sequence}")
        
        # Parse and interpret
        parsed_dna = parse_dna_sequence(dna_sequence)
        phenotype_prompt = self.interpreter.dna_to_phenotype_prompt(parsed_dna)
        print(f"🎨 Phenotype prompt generated")
        print(f"   {phenotype_prompt[:100]}...")
        
        # Create spore
        spore = MemorySpore(
            spore_id=spore_id,
            dna_sequence=dna_sequence,
            phenotype_prompt=phenotype_prompt,
            stimulus=stimulus
        )
        
        return spore

# Test functions
async def test_genesis_engine():
    """Test the Genesis Engine with sample memories"""
    engine = GenesisEngine()
    
    test_stimuli = [
        "The old vinyl record crackles, then a lone trumpet begins to play as dust motes dance in the single sunbeam cutting through the dim room.",
        "She realized with sudden clarity that the equation she'd been struggling with for months was actually describing the pattern of her grandmother's knitting.",
        "The server room hummed with a thousand tiny fans, each one singing its part in an electronic symphony of cooling and calculation.",
        "Lightning split the sky just as the final chess piece fell, checkmate achieved in the midst of nature's fury."
    ]
    
    print("🌟 Genesis Engine v0.1 - Creating Memory Spores")
    print("=" * 60)
    
    for stimulus in test_stimuli:
        print(f"\n📝 Stimulus: \"{stimulus}\"")
        spore = await engine.create_spore(stimulus)
        print(f"✨ Spore created: {spore.spore_id}")
        print("-" * 60)

if __name__ == "__main__":
    asyncio.run(test_genesis_engine())