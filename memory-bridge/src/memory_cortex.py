"""
Memory Cortex - The Living Memory Organism
Combines Genesis Engine, ChromaDB storage, and Dream Cycles
"""

import asyncio
import time
import json
import uuid
from typing import List, Dict, Optional, Tuple
from dataclasses import asdict
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import numpy as np
from genesis_engine import GenesisEngine, MemorySpore
from spore_visualizer import SporeVisualizer
from rich.console import Console

console = Console()

class MemoryCortex:
    """The living memory organism with spore network"""
    
    def __init__(self, 
                 collection_name: str = "memory_spores",
                 persist_directory: str = "./memory_cortex_db",
                 embedding_model: str = "all-MiniLM-L6-v2"):
        
        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(collection_name)
            console.print(f"[green]Connected to existing memory cortex: {collection_name}[/green]")
        except:
            self.collection = self.client.create_collection(collection_name)
            console.print(f"[yellow]Created new memory cortex: {collection_name}[/yellow]")
        
        # Initialize components
        self.genesis_engine = GenesisEngine()
        self.visualizer = SporeVisualizer()
        self.embedder = SentenceTransformer(embedding_model)
        
        # Dream cycle state
        self.dream_active = False
        self.total_dreams = 0
    
    async def ingest_memory(self, stimulus: str) -> MemorySpore:
        """Ingest a new memory into the cortex"""
        console.print(f"\n[bold cyan]🧠 Ingesting new memory...[/bold cyan]")
        
        # Create spore through Genesis Engine
        spore = await self.genesis_engine.create_spore(stimulus)
        
        # Generate embedding (frequency vector)
        embedding = self.embedder.encode(stimulus).tolist()
        spore.frequency_vector = embedding
        
        # Store in ChromaDB
        self.collection.add(
            ids=[spore.spore_id],
            embeddings=[embedding],
            metadatas=[{
                "dna_sequence": spore.dna_sequence,
                "phenotype_prompt": spore.phenotype_prompt,
                "energy_level": spore.energy_level,
                "timestamp": time.time(),
                "stimulus": stimulus
            }],
            documents=[stimulus]
        )
        
        console.print(f"[green]✓ Memory ingested as {spore.spore_id}[/green]")
        
        # Visualize the new spore
        self.visualizer.visualize_dna(spore.dna_sequence)
        
        # Find resonant memories
        await self._find_resonance(spore)
        
        return spore
    
    async def _find_resonance(self, spore: MemorySpore, n_results: int = 3):
        """Find memories that resonate with this spore"""
        if spore.frequency_vector:
            results = self.collection.query(
                query_embeddings=[spore.frequency_vector],
                n_results=n_results + 1  # +1 because it will include itself
            )
            
            if results['ids'][0]:
                resonant_ids = [id for id in results['ids'][0] if id != spore.spore_id]
                if resonant_ids:
                    console.print(f"\n[magenta]🔗 Found resonant memories: {resonant_ids}[/magenta]")
                    
                    # Create synaptic links
                    spore.synaptic_links = resonant_ids[:2]  # Link to top 2
                    
                    # Update in database
                    self.collection.update(
                        ids=[spore.spore_id],
                        metadatas=[{"synaptic_links": json.dumps(spore.synaptic_links)}]
                    )
    
    async def recall_memory(self, query: str, n_results: int = 5) -> List[Dict]:
        """Recall memories based on a query"""
        console.print(f"\n[bold cyan]🔍 Recalling memories for: \"{query}\"[/bold cyan]")
        
        # Embed query
        query_embedding = self.embedder.encode(query).tolist()
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        memories = []
        if results['ids'][0]:
            for i, spore_id in enumerate(results['ids'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if results['distances'] else 0
                
                memory = {
                    'spore_id': spore_id,
                    'dna_sequence': metadata.get('dna_sequence', ''),
                    'stimulus': metadata.get('stimulus', ''),
                    'energy_level': metadata.get('energy_level', 1.0),
                    'resonance_score': 1.0 - distance,  # Convert distance to similarity
                    'synaptic_links': json.loads(metadata.get('synaptic_links', '[]'))
                }
                memories.append(memory)
        
        # Visualize recalled memories
        if memories:
            console.print(f"\n[green]Found {len(memories)} resonant memories:[/green]")
            self.visualizer.visualize_spore_network(memories[:3])  # Show top 3
        else:
            console.print("[yellow]No memories found[/yellow]")
        
        return memories
    
    async def dream_cycle(self, duration_seconds: int = 10):
        """Run a dream cycle to synthesize and consolidate memories"""
        console.print(f"\n[bold magenta]💤 Entering dream cycle for {duration_seconds}s...[/bold magenta]")
        self.dream_active = True
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds and self.dream_active:
            # Get all memories
            all_data = self.collection.get()
            if not all_data['ids']:
                await asyncio.sleep(1)
                continue
            
            # Pick a random high-energy memory
            energies = [m.get('energy_level', 1.0) for m in all_data['metadatas']]
            if max(energies) < 0.5:
                console.print("[dim]All memories low energy, skipping dream...[/dim]")
                break
            
            # Select memory weighted by energy
            weights = np.array(energies) / sum(energies)
            selected_idx = np.random.choice(len(all_data['ids']), p=weights)
            seed_id = all_data['ids'][selected_idx]
            
            console.print(f"\n[cyan]Dream seed: {seed_id}[/cyan]")
            
            # Find connected memories
            seed_meta = all_data['metadatas'][selected_idx]
            links = json.loads(seed_meta.get('synaptic_links', '[]'))
            
            if links:
                # Traverse synaptic links
                dream_cluster = [seed_id] + links[:2]
                console.print(f"[cyan]Dream cluster: {dream_cluster}[/cyan]")
                
                # Boost energy of participating memories
                for spore_id in dream_cluster:
                    try:
                        current_meta = self.collection.get(ids=[spore_id])['metadatas'][0]
                        new_energy = min(1.0, current_meta.get('energy_level', 1.0) + 0.1)
                        self.collection.update(
                            ids=[spore_id],
                            metadatas=[{"energy_level": new_energy}]
                        )
                    except:
                        pass
                
                self.total_dreams += 1
                console.print(f"[green]✨ Dream #{self.total_dreams} synthesized[/green]")
            
            # Decay energy of non-participating memories
            for i, spore_id in enumerate(all_data['ids']):
                if spore_id not in dream_cluster:
                    current_energy = all_data['metadatas'][i].get('energy_level', 1.0)
                    new_energy = max(0.0, current_energy - 0.05)
                    self.collection.update(
                        ids=[spore_id],
                        metadatas=[{"energy_level": new_energy}]
                    )
            
            await asyncio.sleep(2)
        
        self.dream_active = False
        console.print("[bold magenta]💤 Dream cycle complete[/bold magenta]")
    
    def get_memory_stats(self) -> Dict:
        """Get statistics about the memory cortex"""
        all_data = self.collection.get()
        
        if not all_data['ids']:
            return {
                'total_memories': 0,
                'average_energy': 0,
                'total_dreams': self.total_dreams
            }
        
        energies = [m.get('energy_level', 1.0) for m in all_data['metadatas']]
        
        return {
            'total_memories': len(all_data['ids']),
            'average_energy': sum(energies) / len(energies),
            'highest_energy': max(energies),
            'lowest_energy': min(energies),
            'total_dreams': self.total_dreams,
            'total_synaptic_links': sum(
                len(json.loads(m.get('synaptic_links', '[]'))) 
                for m in all_data['metadatas']
            )
        }

# Interactive test
async def interactive_test():
    """Interactive test of the Memory Cortex"""
    cortex = MemoryCortex()
    
    console.print("[bold cyan]🧠 Memory Cortex Interactive Test[/bold cyan]")
    console.print("Commands: 'add <memory>', 'recall <query>', 'dream', 'stats', 'quit'\n")
    
    while True:
        command = input("cortex> ").strip()
        
        if command.startswith("add "):
            memory_text = command[4:]
            await cortex.ingest_memory(memory_text)
            
        elif command.startswith("recall "):
            query = command[7:]
            await cortex.recall_memory(query)
            
        elif command == "dream":
            await cortex.dream_cycle(duration_seconds=5)
            
        elif command == "stats":
            stats = cortex.get_memory_stats()
            console.print("\n[yellow]Memory Cortex Statistics:[/yellow]")
            for key, value in stats.items():
                console.print(f"  {key}: {value}")
            
        elif command == "quit":
            break
        
        else:
            console.print("[red]Unknown command[/red]")

if __name__ == "__main__":
    asyncio.run(interactive_test())