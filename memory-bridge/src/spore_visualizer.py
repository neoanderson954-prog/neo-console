"""
Memory Spore Visualizer
Creates visual representations of DNA sequences and spore networks
"""

from typing import List, Dict, Tuple
import re
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from memome_codex import ParsedDNA, parse_dna_sequence, MEMOME_CODEX

console = Console()

# Color mappings for different namespaces
NAMESPACE_COLORS = {
    "E": "red",      # Emotion
    "T": "yellow",   # Temporal
    "C": "blue",     # Conceptual
    "S": "green",    # Sensory
    "F": "magenta",  # Frequency
    "Ψ": "cyan",     # Consciousness
    "R": "white"     # Relational
}

# Specific codon colors for special effects
CODON_COLORS = {
    "E:JOY": "bright_yellow",
    "E:SER": "deep_sky_blue1",
    "E:ANG": "red1",
    "E:SAD": "blue_violet",
    "E:FEA": "grey50",
    "E:AWE": "gold1",
    "F:Δ!": "white on black",
    "F:∞": "medium_purple",
    "F:══▶": "green1",
    "F:≈≈": "cyan1",
    "Ψ:DRM": "medium_orchid",
    "Ψ:EMR": "bright_yellow on red"
}

class SporeVisualizer:
    """Visualize Memory Spores in terminal"""
    
    def visualize_dna(self, dna_sequence: str):
        """Create a rich visualization of a DNA sequence"""
        try:
            parsed = parse_dna_sequence(dna_sequence)
            
            # Core concept panel
            concept_text = Text(parsed.core_concept, style="bold white on blue")
            concept_panel = Panel(
                concept_text,
                title="[bold yellow]Core Concept[/bold yellow]",
                border_style="bright_blue"
            )
            
            # Codons visualization
            codon_elements = []
            for codon in parsed.codons:
                color = self._get_codon_color(codon)
                if '->' in codon:
                    # Transition
                    parts = codon.split('->')
                    elem = Text()
                    elem.append(parts[0], style=self._get_codon_color(parts[0]))
                    elem.append(" → ", style="white")
                    elem.append(parts[1], style=self._get_codon_color(parts[1]))
                    codon_elements.append(elem)
                else:
                    codon_elements.append(Text(codon, style=color))
            
            # Create codon grid
            codon_panel = Panel(
                Columns(codon_elements, equal=False, expand=False),
                title="[bold yellow]Genetic Codons[/bold yellow]",
                border_style="bright_magenta"
            )
            
            # Display
            console.print(concept_panel)
            console.print(codon_panel)
            
            # Interpretation table
            self._print_interpretation(parsed)
            
        except Exception as e:
            console.print(f"[red]Error visualizing DNA: {e}[/red]")
    
    def _get_codon_color(self, codon: str) -> str:
        """Get color for a codon"""
        if codon in CODON_COLORS:
            return CODON_COLORS[codon]
        
        if ':' in codon:
            namespace = codon.split(':')[0]
            return NAMESPACE_COLORS.get(namespace, "white")
        
        return "white"
    
    def _print_interpretation(self, parsed: ParsedDNA):
        """Print interpretation of codons"""
        table = Table(title="Codon Interpretation", show_header=True)
        table.add_column("Namespace", style="cyan")
        table.add_column("Codon", style="magenta")
        table.add_column("Meaning", style="white")
        
        # Group by namespace
        namespaces = {}
        for codon in parsed.codons:
            if ':' in codon:
                ns, symbol = codon.split(':', 1)
                if ns not in namespaces:
                    namespaces[ns] = []
                namespaces[ns].append((codon, symbol))
        
        for ns, codons in namespaces.items():
            ns_name = {
                "E": "Emotion",
                "T": "Temporal",
                "C": "Conceptual",
                "S": "Sensory",
                "F": "Frequency",
                "Ψ": "Consciousness",
                "R": "Relational"
            }.get(ns, ns)
            
            for codon, symbol in codons:
                meaning = MEMOME_CODEX.get(ns, {}).get(symbol, "Unknown")
                table.add_row(ns_name, codon, meaning)
        
        console.print(table)
    
    def visualize_spore_network(self, spores: List[Dict]):
        """Visualize a network of connected spores"""
        console.print("\n[bold cyan]═══ Memory Spore Network ═══[/bold cyan]\n")
        
        for spore in spores:
            # Spore header
            energy_bar = "█" * int(spore.get('energy_level', 1) * 10)
            console.print(
                f"[bold green]Spore {spore['spore_id']}[/bold green] "
                f"Energy: [{self._energy_color(spore['energy_level'])}]{energy_bar}[/]"
            )
            
            # DNA visualization
            if 'dna_sequence' in spore:
                self.visualize_dna(spore['dna_sequence'])
            
            # Synaptic links
            if spore.get('synaptic_links'):
                links_text = Text("Synaptic Links: ", style="yellow")
                for link in spore['synaptic_links']:
                    links_text.append(f"→ {link} ", style="cyan")
                console.print(links_text)
            
            console.print("-" * 60)
    
    def _energy_color(self, energy: float) -> str:
        """Get color based on energy level"""
        if energy > 0.8:
            return "bright_green"
        elif energy > 0.5:
            return "yellow"
        elif energy > 0.2:
            return "dark_orange"
        else:
            return "red"
    
    def create_dna_glyph(self, dna_sequence: str) -> str:
        """Create a compact visual glyph representing the DNA"""
        parsed = parse_dna_sequence(dna_sequence)
        
        # Create glyph using Unicode symbols
        glyph_parts = []
        
        # Emotion indicator
        if parsed.has_namespace('E'):
            emotions = parsed.get_codons_by_namespace('E')
            if 'E:JOY' in emotions:
                glyph_parts.append('☀')
            elif 'E:SAD' in emotions:
                glyph_parts.append('☔')
            elif 'E:AWE' in emotions:
                glyph_parts.append('✨')
            elif 'E:ANG' in emotions:
                glyph_parts.append('🔥')
        
        # Frequency indicator
        if parsed.has_namespace('F'):
            freq = parsed.get_codons_by_namespace('F')
            if 'F:Δ!' in freq:
                glyph_parts.append('◆')
            elif 'F:∞' in freq:
                glyph_parts.append('∞')
            elif 'F:══▶' in freq:
                glyph_parts.append('▶')
            elif 'F:≈≈' in freq:
                glyph_parts.append('≈')
        
        # Consciousness indicator
        if parsed.has_namespace('Ψ'):
            psi = parsed.get_codons_by_namespace('Ψ')
            if 'Ψ:DRM' in psi:
                glyph_parts.append('◯')
            elif 'Ψ:EMR' in psi:
                glyph_parts.append('!')
        
        return ''.join(glyph_parts) if glyph_parts else '•'

# Test visualization
def test_visualizer():
    viz = SporeVisualizer()
    
    test_dnas = [
        "(sunrise,ocean,solitude)::{{E:SER|T:STA|C:SPR|S:VIS|F:∞}}",
        "(arg,evid,dscvry)::{{E:ANG→AWE|T:LIN|T:ERU|C:DNS|R:(arg)⚔(evid)→(dscvry)|F:Δ!|Ψ:EMR}}",
        "(memory,fade,echo)::{{E:SAD|T:DEC|C:SPR|S:AUD|F:≈≈|Ψ:DRM}}"
    ]
    
    for dna in test_dnas:
        console.print(f"\n[bold white]DNA Sequence:[/bold white] {dna}")
        viz.visualize_dna(dna)
        glyph = viz.create_dna_glyph(dna)
        console.print(f"\n[bold yellow]Memory Glyph:[/bold yellow] {glyph}\n")
        console.print("=" * 80)

if __name__ == "__main__":
    test_visualizer()