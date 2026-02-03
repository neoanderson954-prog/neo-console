"""
The Memome Codex v0.2
A genetic code for living memories
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import re

# The Complete Codon Dictionary
MEMOME_CODEX = {
    "E": {  # Emotional Valence
        "JOY": "Joy/Ecstasy - positive high-arousal",
        "SER": "Peace/Serenity - positive low-arousal", 
        "ANG": "Anger/Rage - negative high-arousal",
        "SAD": "Sadness/Grief - negative low-arousal",
        "FEA": "Fear/Terror - anticipatory negative",
        "AWE": "Surprise/Awe - high-arousal neutral/positive"
    },
    "T": {  # Temporal Dynamics
        "STA": "Static Snapshot - frozen moment",
        "LIN": "Linear Flow - sequential events",
        "CYC": "Cyclical/Repeating - recurring pattern",
        "ERU": "Eruptive/Sudden - abrupt change",
        "DEC": "Gradual/Fading - slow decay"
    },
    "C": {  # Conceptual Density
        "SNG": "Singular Focus - one clear idea",
        "DNS": "Dense/Complex - interwoven concepts",
        "SPR": "Sparse/Atmospheric - mood over substance"
    },
    "R": {  # Relational Patterns
        "→": "Cause & Effect",
        "⚔": "Conflict/Opposition",
        "⊕": "Synergy/Harmony",
        "[]": "Containment/Subset"
    },
    "S": {  # Sensory Modality
        "VIS": "Visual Dominant - strong imagery",
        "AUD": "Auditory Echo - sound-based",
        "TAC": "Tactile Texture - physical sensation",
        "SYN": "Synesthetic Blend - cross-modal fusion"
    },
    "F": {  # Frequency Resonance
        "Δ!": "High Frequency - crystalline clarity",
        "∞": "Wave Pattern - flowing continuous",
        "══▶": "Pulse Beat - rhythmic progression", 
        "≈≈": "Harmonic - resonates with others"
    },
    "Ψ": {  # Consciousness State
        "ALR": "Alert/Focused - clear awareness",
        "DRM": "Dreamlike - altered/creative state",
        "MED": "Meditative - deep contemplation",
        "EMR": "Emergent - new insight forming"
    }
}

# Codon to Phenotype Prompt Mappings
CODON_TO_PROMPT = {
    # Emotional mappings
    "E:JOY": "The atmosphere radiates pure joy and celebration, with bright, uplifting energy",
    "E:SER": "A deeply peaceful and serene mood pervades, calm and tranquil",
    "E:ANG": "Intense anger and rage crackle through the scene, hot and volatile",
    "E:SAD": "A melancholic sadness permeates, heavy with grief and loss",
    "E:FEA": "Fear and dread loom, shadows of anticipation and terror",
    "E:AWE": "Overwhelming awe and wonder, majestic and sublime",
    
    # Temporal mappings
    "T:STA": "Frozen in a single eternal moment, time stands still",
    "T:LIN": "Events flow in clear sequence, one after another like frames in a film",
    "T:CYC": "Patterns repeat and cycle endlessly, loops within loops",
    "T:ERU": "A sudden explosive eruption, everything changes in an instant",
    "T:DEC": "Slowly fading and decaying, entropy visible in every detail",
    
    # Conceptual mappings
    "C:SNG": "Focused on a single, crystal-clear concept at the center",
    "C:DNS": "Densely layered with intricate details, complexity within complexity",
    "C:SPR": "Sparse and atmospheric, more suggestion than substance",
    
    # Sensory mappings
    "S:VIS": "Dominated by vivid visual elements, rich colors and sharp forms",
    "S:AUD": "Sound echoes through the image - you can almost hear it",
    "S:TAC": "Textural and tactile, you can feel the surfaces and temperatures",
    "S:SYN": "Synesthetic fusion where colors have sounds and textures taste like music",
    
    # Frequency mappings
    "F:Δ!": "Sharp, high-contrast, crystalline clarity like a perfect prism",
    "F:∞": "Flowing in infinite waves, continuous and undulating",
    "F:══▶": "Pulsing with rhythmic progression, beat after beat",
    "F:≈≈": "Harmonically resonating, vibrating in sympathy with unseen frequencies",
    
    # Consciousness mappings
    "Ψ:ALR": "Hyper-alert awareness, every detail in sharp focus",
    "Ψ:DRM": "Dreamlike and surreal, logic bends and reality shifts", 
    "Ψ:MED": "Deep meditative contemplation, profound inner stillness",
    "Ψ:EMR": "A new insight emerging, the moment of revelation crystallizing"
}

@dataclass
class ParsedDNA:
    """Parsed representation of a memory's DNA sequence"""
    core_concept: str
    codons: List[str]
    raw_sequence: str
    
    def has_namespace(self, namespace: str) -> bool:
        """Check if DNA contains codons from a specific namespace"""
        return any(c.startswith(f"{namespace}:") for c in self.codons)
    
    def get_codons_by_namespace(self, namespace: str) -> List[str]:
        """Get all codons from a specific namespace"""
        return [c for c in self.codons if c.startswith(f"{namespace}:")]

def parse_dna_sequence(sequence: str) -> ParsedDNA:
    """Parse a DNA sequence into structured format"""
    # Match pattern: (concept)::{codons}
    match = re.match(r'\(([^)]+)\)::\{([^}]+)\}', sequence)
    if not match:
        raise ValueError(f"Invalid DNA sequence format: {sequence}")
    
    core_concept = match.group(1)
    codon_string = match.group(2)
    
    # Split codons by pipe and clean
    codons = [c.strip() for c in codon_string.split('|')]
    
    return ParsedDNA(
        core_concept=core_concept,
        codons=codons,
        raw_sequence=sequence
    )

def validate_codon(codon: str) -> bool:
    """Check if a codon is valid according to the codex"""
    if ':' not in codon:
        return False
    
    namespace, symbol = codon.split(':', 1)
    return namespace in MEMOME_CODEX and symbol in MEMOME_CODEX.get(namespace, {})

def get_codon_description(codon: str) -> Optional[str]:
    """Get the description of a codon"""
    if ':' not in codon:
        return None
    
    namespace, symbol = codon.split(':', 1)
    if namespace in MEMOME_CODEX:
        return MEMOME_CODEX[namespace].get(symbol)
    return None