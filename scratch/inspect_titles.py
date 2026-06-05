import os
import json
from collections import defaultdict

data_dir = r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\cleaned_data"
by_slug = defaultdict(list)

for filename in sorted(os.listdir(data_dir)):
    if filename.endswith(".json"):
        path = os.path.join(data_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            try:
                chunks = json.load(f)
                for chunk in chunks:
                    p = chunk.get("path", "")
                    # Check if the path indicates a faculty profile
                    # e.g., /team/dr-aparna-pasumarthy or /study/our-team/ or similar
                    if "/team/" in p:
                        parts = p.split("/team/")
                        slug = parts[1].strip("/")
                        if slug:
                            by_slug[slug].append(chunk)
                    elif "/study/our-team" in p:
                        # Let's inspect these chunks as well to see if they are individual profiles
                        by_slug["study-our-team"].append(chunk)
            except Exception as e:
                print(f"Error loading {filename}: {e}")

for slug, chunks in sorted(by_slug.items()):
    print(f"Slug: {slug} ({len(chunks)} chunks)")
    for i, c in enumerate(chunks):
        print(f"  [{i}] Title: {c.get('title')} | Path: {c.get('path')} | ChunkIdx: {c.get('chunk_index')}")
    print("-" * 60)
