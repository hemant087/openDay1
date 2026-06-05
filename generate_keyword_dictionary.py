import json
import os
from collections import defaultdict

DATA_DIR = "cleaned_data"
OUTPUT_FILE = "keyword_dictionary_compact.json"

def generate_keyword_dictionary():
    keyword_to_ids = defaultdict(list)
    id_to_summary = {}
    
    if not os.path.exists(DATA_DIR):
        print(f"Error: {DATA_DIR} not found.")
        return

    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.json')]
    print(f"Processing {len(files)} files...")
    
    for filename in files:
        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                chunks = json.load(f)
            except Exception as e:
                print(f"Skipping {filename}: {e}")
                continue
                
            for chunk in chunks:
                # Use a unique identifier for each chunk
                chunk_id = chunk.get("id") or str(chunk.get("chunk_index"))
                if not chunk_id:
                    continue
                    
                summary = chunk.get("summary", "")
                if not summary:
                    summary = chunk.get("text", "")[:150].strip() + "..."
                    
                # 1. Store the summary exactly ONCE
                id_to_summary[chunk_id] = summary
                
                # 2. Map keywords to the ID, not the raw text!
                keywords = chunk.get("keywords", [])
                for kw in keywords:
                    if chunk_id not in keyword_to_ids[kw]:
                        keyword_to_ids[kw].append(chunk_id)

    # Combine into a single structured, relational JSON
    final_output = {
        "chunks": id_to_summary,
        "keywords": dict(keyword_to_ids)
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully generated {OUTPUT_FILE}.")
    print(f"  - Unique Summaries (Chunks): {len(id_to_summary)}")
    print(f"  - Unique Keywords: {len(keyword_to_ids)}")

if __name__ == "__main__":
    generate_keyword_dictionary()
