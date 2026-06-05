#!/usr/bin/env python3
"""
build_rag_index.py — Pre-build the RAG inverted index for RoboGreet.

Reads all cleaned_data/chunk_*.json files, strips unused metadata,
builds an inverted index with IDF values, and writes a single
rag_index.json for instant server startup.

Usage:
    python build_rag_index.py
"""

import os
import json
import math
import time
from collections import defaultdict

# ── Configuration ──────────────────────────────────────────────────────────
DATA_DIR = "cleaned_data"
OUTPUT_FILE = "rag_index.json"

# Stop words — common English words that add noise to retrieval
_STOP = frozenset(
    "the is at in of and to for a an on it by as or be was are with that this "
    "from but not have has had can will what how who when where which about "
    "your you they their there been would could should does did its also than "
    "then very just more do our we all any each few some most other into over "
    "such only these those through between during before after above below up "
    "down out off no nor so too own same both if while".split()
)

MIN_WORD_LEN = 2  # Ignore words shorter than this


def tokenize(text):
    """Lowercase, strip punctuation, filter stopwords and short words."""
    words = set()
    for word in text.lower().split():
        clean = word.strip(".,;:!?()[]{}\"'-/\\@#$%^&*~`+=<>|")
        if len(clean) >= MIN_WORD_LEN and clean not in _STOP:
            words.add(clean)
    return words


def build_index():
    """Main build pipeline: read chunks → build index → write output."""
    if not os.path.exists(DATA_DIR):
        print(f"[ERROR] '{DATA_DIR}' folder not found. Run from the project root.")
        return

    t0 = time.time()

    # ── Phase 1: Load and strip chunks ─────────────────────────────────
    chunks = []        # [{text, title}, ...]
    raw_files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith('.json'))
    skipped = 0

    print(f"[1/3] Reading {len(raw_files)} chunk files from '{DATA_DIR}'...")

    for filename in raw_files:
        filepath = os.path.join(DATA_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                file_chunks = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  [WARN] Skipping {filename}: {e}")
            skipped += 1
            continue

        for chunk in file_chunks:
            text = chunk.get("text", "").strip()
            title = chunk.get("title", "").strip()
            keywords = chunk.get("keywords", [])
            topic = chunk.get("topic", "")

            # Skip empty or boilerplate chunks (e.g. cookie policy)
            if not text or len(text) < 30:
                skipped += 1
                continue

            chunks.append({
                "text": text,
                "title": title,
                "keywords": keywords,
                "topic": topic,
            })

    print(f"    -> {len(chunks)} chunks loaded, {skipped} skipped")

    # ── Phase 2: Build inverted index + compute IDF ────────────────────
    print(f"[2/3] Building inverted index...")

    inverted = defaultdict(list)  # word → [chunk_idx, ...]
    doc_lengths = []              # token count per chunk (for BM25)
    N = len(chunks)

    for idx, chunk in enumerate(chunks):
        # Combine text + title + keywords for indexing
        combined = chunk["text"] + " " + chunk["title"]
        combined += " " + " ".join(chunk["keywords"])

        tokens = tokenize(combined)
        doc_lengths.append(len(combined.split()))  # raw word count for BM25

        for token in tokens:
            inverted[token].append(idx)

    # Compute IDF for each term: log((N - df + 0.5) / (df + 0.5) + 1)
    idf = {}
    for term, postings in inverted.items():
        df = len(set(postings))  # document frequency (unique docs)
        idf[term] = round(math.log((N - df + 0.5) / (df + 0.5) + 1), 4)

    # Deduplicate posting lists (a term can appear once per doc)
    index = {}
    for term, postings in inverted.items():
        index[term] = sorted(set(postings))

    avg_dl = sum(doc_lengths) / N if N > 0 else 1

    print(f"    -> {len(index)} unique terms indexed")
    print(f"    -> Avg document length: {avg_dl:.1f} words")

    # ── Phase 3: Write output ──────────────────────────────────────────
    print(f"[3/3] Writing '{OUTPUT_FILE}'...")

    # Strip keywords from chunks (only needed during indexing, not at runtime)
    slim_chunks = [{"text": c["text"], "title": c["title"]} for c in chunks]

    output = {
        "meta": {
            "chunk_count": N,
            "term_count": len(index),
            "avg_doc_length": round(avg_dl, 2),
            "doc_lengths": doc_lengths,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "chunks": slim_chunks,
        "index": index,
        "idf": idf,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    elapsed = (time.time() - t0) * 1000

    print(f"\nDone in {elapsed:.0f}ms")
    print(f"   Output: {OUTPUT_FILE} ({size_kb:.0f} KB)")
    print(f"   Chunks: {N}  |  Terms: {len(index)}  |  Avg doc len: {avg_dl:.1f}")
    print(f"\n   Server will now load this single file instead of {len(raw_files)} separate files.")


if __name__ == "__main__":
    build_index()
