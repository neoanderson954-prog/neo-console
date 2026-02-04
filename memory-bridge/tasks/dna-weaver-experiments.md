# DNA + WeaverEngine Experiments

## Obiettivo
Testare operazioni genetiche (crossover, mutazione, fitness, selezione) in isolamento, poi collegare al cortex reale. Valutare se produce risultati utili prima di integrare.

## Base
`~/projects/neo-console/memory-bridge/`

## Fase 1: Test WeaverEngine isolato
**File:** `tests/test_weaver_engine.py`

Test con MemorySpore sintetici (no cortex, no groq):
- Selezione genitori (energia, risonanza, link sinaptici)
- Crossover (codoni ereditati da A + subset B)
- Mutazione (rate ~2%, codoni validi)
- Sintesi concetti (regole euristiche)
- Blending vettore frequenza
- Log riproduzione → SQLite
- Fitness score update
- Analisi pattern vincenti
- Anticipatory synthesis

~13 test, TDD: scrivo test → rossi → faccio passare

## Fase 2: Test pipeline DNA
**File:** `tests/test_dna_pipeline.py`

Test groq_compiler + memome_codex insieme:
- compile_to_dna → formato valido
- parse_dna_sequence → estrae codoni
- Roundtrip: genera → parse → ricostruisci
- Codoni invalidi → gestione errore
- Mutazione produce solo codoni validi

~8 test. Quelli con groq: mockati o con flag --run-groq per test reali

## Fase 3: Bridge layer
**File:** `src/spore_bridge.py`
**Test:** `tests/test_spore_bridge.py`

Funzione `chromadb_to_spore(metadata, embedding) → MemorySpore`:
- Parsa DNA string → codoni
- Embedding ChromaDB → frequency_vector
- Energy, synaptic_links → campi MemorySpore
- Fallback per DNA invalido/mancante

~5 test

## Fase 4: Integration test
**File:** `tests/test_weaver_integration.py`

Test end-to-end con cortex reale (test DB isolata):
- Ingest 4-5 turns → genera DNA con groq
- Fetch da ChromaDB → converti a MemorySpore
- select_parents → reproduce → offspring
- Log riproduzione → analizza pattern
- Stampa dettagliata di tutto (osservabilita)

~4 test, con output verbose per valutare risultati

## Ordine
1. Fase 1 → weaver funziona?
2. Fase 2 → DNA pipeline robusto?
3. Fase 3 → bridge converte correttamente?
4. Fase 4 → tutto insieme produce risultati sensati?

## File
- `tests/test_weaver_engine.py` (nuovo)
- `tests/test_dna_pipeline.py` (nuovo)
- `src/spore_bridge.py` (nuovo)
- `tests/test_spore_bridge.py` (nuovo)
- `tests/test_weaver_integration.py` (nuovo)
- `src/weaver_engine.py` (fix se servono)

## Verifica
```bash
cd ~/projects/neo-console/memory-bridge
source .venv/bin/activate
pytest tests/test_weaver_engine.py -v
pytest tests/test_dna_pipeline.py -v
pytest tests/test_spore_bridge.py -v
pytest tests/test_weaver_integration.py -v -s
```
