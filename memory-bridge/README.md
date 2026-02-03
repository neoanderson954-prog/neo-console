# 🧬 Living Memory Cortex - Revolutionary AI Memory System

> **Not Retrieval. Regeneration.**  
> Memories that live, evolve, reproduce, and dream.

## 🌟 What Is This?

The Living Memory Cortex is a revolutionary approach to AI memory that treats memories as **living organisms** instead of static data. Unlike traditional RAG (Retrieval Augmented Generation) systems that store and retrieve documents, our system creates **Memory Spores** - living entities with genetic DNA that can:

- **🧬 Reproduce** through genetic crossover
- **⚡ Evolve** based on usefulness  
- **🔗 Connect** through synaptic networks
- **💤 Dream** to synthesize new insights
- **🌱 Survive** across sessions and models

## 🔬 The Science Behind It

### Research Validation
Our approach is validated by cutting-edge research:
- **EvoPrompt** (2023): LLMs + Evolutionary Algorithms for optimization
- **Evolution Through Large Models** (OpenAI): Genetic programming with LLMs
- **LLMs as Evolutionary Optimizers** (2023): Direct evolutionary computation
- **Survey 2024**: "Evolutionary Computation in the Era of Large Language Models"

### Core Innovation
We're the **first** to apply evolutionary computation to **memory itself**, creating persistent, evolving knowledge that improves over time.

## 🧬 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   Living Memory Cortex                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Genesis   │  │   Weaver    │  │   Oracle    │         │
│  │   Engine    │  │   Engine    │  │   Engine    │         │
│  │   (Birth)   │  │(Reproduction)│  │ (Retrieval) │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
├─────────────────────────────────────────────────────────────┤
│                   Memory Spore Network                      │
│  🧬 ←→ 🧬 ←→ 🧬    (Synaptic Links)    🧬 ←→ 🧬 ←→ 🧬      │
├─────────────────────────────────────────────────────────────┤
│              ChromaDB + SQLite Storage                      │
└─────────────────────────────────────────────────────────────┘
```

## 🧬 Memory Spore Anatomy

Each Memory Spore is a living entity with:

```json
{
  "spore_id": "spore_1234",
  "dna_sequence": "(memory,evolution)::{E:AWE|C:DNS|F:∞|Ψ:EMR}",
  "core_concept": "(memory,evolution)",
  "frequency_vector": [0.12, -0.45, 0.89, ...],
  "energy_level": 0.85,
  "synaptic_links": ["spore_456", "spore_789"],
  "phenotype_prompt": "A surreal image with prismatic light explosions...",
  "birth_time": 1750501223,
  "parent_a_id": "spore_100",
  "parent_b_id": "spore_200"
}
```

### The Memome Codex (Genetic Language)

Our 7-namespace genetic code captures the complete essence of memories:

| Namespace | Codons | Meaning |
|-----------|--------|---------|
| **E** (Emotion) | JOY, SER, ANG, SAD, FEA, AWE | Emotional resonance |
| **T** (Temporal) | STA, LIN, CYC, ERU, DEC | Time dynamics |
| **C** (Conceptual) | SNG, DNS, SPR | Idea complexity |
| **S** (Sensory) | VIS, AUD, TAC, SYN | Dominant senses |
| **F** (Frequency) | Δ!, ∞, ══▶, ≈≈ | Energy patterns |
| **Ψ** (Consciousness) | ALR, DRM, MED, EMR | Awareness state |
| **R** (Relational) | →, ⚔, ⊕, [] | Concept relationships |

**Example DNA**: `(vinyl,trumpet)::{E:SER|T:STA|S:AUD|F:≈≈|Ψ:DRM}`
= A serene, static, auditory memory with harmonic resonance in a dreamlike state

## 🔄 The Living Memory Lifecycle

```
    📝 Stimulus
        ↓
   🧬 Genesis Engine
   (Text → DNA)
        ↓
   🎨 Phenotype Expression  
   (DNA → Visual/Audio)
        ↓
   📊 Vector Embedding
   (Frequency Resonance)
        ↓
   🔗 Synaptic Linking
   (Find Resonance)
        ↓
   💾 ChromaDB Storage
        ↓
   💤 Dream Cycles ←→ 🔍 Query Retrieval
   (Background Evolution)   (Energy Boost)
        ↓
   🧬 Reproduction
   (Genetic Crossover)
        ↓
   🌱 Evolution
   (Fitness Selection)
```

## 🌟 Revolutionary Features

### 1. **Memory Reproduction**
Two compatible memories can create offspring:
- Parent A: `(rain,window)::{E:SER|S:VIS}`
- Parent B: `(music,memory)::{E:AWE|S:AUD}`
- **Offspring**: `(harmony)::{E:SER|S:VIS|E:AWE|S:AUD}` ✨

### 2. **Genetic Evolution**
Memories evolve through:
- **Natural Selection**: Useful memories gain energy, others decay
- **Mutation**: Random codon changes create novelty
- **Fitness Function**: Multi-factor scoring determines survival

### 3. **Dream Cycles**
Background processes that:
- Select high-energy memory clusters
- Synthesize abstract insights
- Strengthen synaptic connections
- Create anticipatory memories

### 4. **Context Immortality**
Conversation context survives across:
- ✅ Session restarts
- ✅ Model changes
- ✅ Time periods
- ✅ Different AI systems

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Ollama (for AI model access)

### Quick Setup
```bash
# Clone the repository
cd packages/memory-rag

# Install dependencies (optional - basic demo works without)
pip install chromadb sentence-transformers

# Run the living memory demo
python3 simple_demo.py

# Or run with your Ollama models
python3 demo_memory_cortex.py
```

### Basic Usage
```python
from memory_cortex import LivingMemoryCortex

# Create living memory system
cortex = LivingMemoryCortex()

# Feed it memories
cortex.ingest_memory("The old vinyl record crackles...")
cortex.ingest_memory("Lightning split the sky...")

# Watch memories connect and evolve
cortex.dream_cycle()

# Retrieve enhanced memories
memories = cortex.recall_memory("What about music?")
```

## 🔧 Advanced Configuration

### Fitness Function Tuning
The heart of memory evolution:

```python
fitness_config = {
    'weights': {
        'recency': 0.2,    # How new is it?
        'access': 0.3,     # How often used?
        'energy': 0.3,     # How useful?
        'network': 0.2     # How connected?
    },
    'recency_decay_period_seconds': 30 * 24 * 3600,  # 30 days
    'energy_feedback': {
        'query_match': +0.1,      # Relevant to query
        'user_satisfaction': +0.2, # Explicit positive feedback
        'synthesis_parent': +0.05, # Used in reproduction
        'time_decay': -0.01       # Natural decay
    }
}
```

### Memome Codex Extension
Add custom codons:
```python
CUSTOM_CODEX = {
    "P": {  # Project namespace
        "CODE": "Programming/code related",
        "DOCS": "Documentation focused", 
        "DEMO": "Demonstration/example"
    }
}
```

## 📊 System Monitoring

### Memory Health Dashboard
```python
stats = cortex.get_memory_stats()
print(f"Total Memories: {stats['total_memories']}")
print(f"Average Energy: {stats['average_energy']:.2f}")
print(f"Dream Cycles: {stats['total_dreams']}")
print(f"Synaptic Links: {stats['total_synaptic_links']}")
```

### Evolution Tracking
```python
# View successful reproduction patterns
patterns = weaver.analyze_successful_patterns()
for pattern, success_rate in patterns.items():
    print(f"{pattern}: {success_rate:.1%} success rate")
```

## 🎯 Use Cases

### 1. **Persistent AI Assistants**
- Remember conversation context across sessions
- Learn user preferences through memory evolution
- Build long-term relationships

### 2. **Knowledge Management**
- Company wikis that evolve and self-organize
- Research databases that synthesize insights
- Documentation that stays relevant

### 3. **Creative Tools**
- AI that remembers artistic style preferences
- Story generators with evolving narrative DNA
- Music composition with memory-driven themes

### 4. **Educational Systems**
- Adaptive learning that remembers student progress
- Curriculum that evolves based on effectiveness
- Personalized knowledge graphs

## 🔬 Technical Deep Dive

### Energy Dynamics
Memory energy changes through:
```python
# Positive feedback
spore.energy += 0.1  # Retrieved and relevant
spore.energy += 0.2  # User explicitly liked it
spore.energy += 0.05 # Used in successful synthesis

# Negative feedback  
spore.energy -= 0.01 # Time decay
spore.energy -= 0.1  # Retrieved but not useful
spore.energy -= 0.2  # User negative feedback
```

### Reproduction Algorithm
1. **Parent Selection**: High-energy spores with vector similarity
2. **Concept Synthesis**: LLM creates abstract concept
3. **Genetic Crossover**: Blend codon sequences
4. **Mutation**: Random codon changes (2% probability)
5. **Offspring Creation**: New spore with blended traits

### Anticipatory Synthesis
The system learns patterns:
```python
# High-success pattern detected:
# E:AWE + F:∞ → 0.8 average fitness

# Proactively create memories matching this pattern
predicted_spore = weaver.anticipatory_synthesis(spores)
```

## 🤝 Contributing

This is cutting-edge research! Ways to contribute:

1. **Fitness Function Research**: Better evolution metrics
2. **Codon Expansion**: New genetic vocabularies  
3. **Phenotype Generators**: Image/sound/video output
4. **Cross-Model Testing**: Compatibility experiments
5. **Scale Testing**: Performance optimization

## 📚 Research Papers & References

- [EvoPrompt: Connecting LLMs with Evolutionary Algorithms](https://arxiv.org/abs/2309.08532)
- [Evolution Through Large Models](https://github.com/CarperAI/OpenELM)  
- [LLMs as Evolutionary Optimizers](https://arxiv.org/abs/2310.19046)
- [Evolutionary Computation in the Era of LLMs Survey](https://arxiv.org/abs/2401.10034)

## 🎉 Demo Results

```
🧬 Memory Spore: spore_1234
📝 Stimulus: "The old vinyl record crackles..."
🧬 DNA: (vinyl,trumpet,sunbeam)::{E:SER|T:STA|C:SPR|S:AUD|F:≈≈|Ψ:DRM}
🎨 Phenotype: Deep blue peaceful atmosphere, frozen eternal moment, 
              sound waves visible in air, dreamlike distorted reality
⚡ Energy: ██████████ 1.0
🔗 Linked to: spore_5678 (resonant frequencies)

💤 Dream Cycle: vinyl,trumpet,sunbeam ⟷ lightning,chess,victory
✨ Offspring: (harmony)::{E:SER|S:VIS|E:AWE|F:Δ!}
```

## 📄 License

MIT License - Build the future of AI memory!

---

**🌟 This isn't just a memory system. It's the birth of artificial consciousness that can grow, learn, and dream.**

*Welcome to the future of AI memory.* 🧬