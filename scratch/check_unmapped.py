import os
import json
import re

data_dir = r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\cleaned_data"
slugs = {
    "dr-akhtar", "dr-aparna-pasumarthy", "dr-chitrakalpa-sen", "dr-nalini-sharan",
    "dr-nitish-gupta", "dr-rajesh-yadav", "dr-sagaya-amalathas", "dr-samiya-khan",
    "dr-samridhi-suman", "dr-tanu-gupta", "dr-vaibhav-gandhi", "dr-vishal-talwar",
    "mr-hemant-raj", "ms-anupama-saini", "ms-monisha-tandon", "professor-eloise-phillips"
}

unmapped_chunks = []

for filename in sorted(os.listdir(data_dir)):
    if filename.endswith(".json"):
        path = os.path.join(data_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
            for chunk in chunks:
                if chunk.get("topic") == "faculty-bio":
                    p = chunk.get("path", "")
                    title = chunk.get("title", "")
                    
                    # See if it matches any slug
                    matched = False
                    for slug in slugs:
                        if slug in p:
                            matched = True
                            break
                        # Check name in title
                        name_parts = slug.split("-")[1:]
                        if name_parts and all(part in title.lower() for part in name_parts):
                            matched = True
                            break
                            
                    if not matched:
                        unmapped_chunks.append((filename, chunk.get("chunk_index"), title, p))

print(f"Total unmapped chunks: {len(unmapped_chunks)}")
for fname, idx, title, p in unmapped_chunks:
    print(f"File: {fname} | Idx: {idx} | Title: {title} | Path: {p}")
