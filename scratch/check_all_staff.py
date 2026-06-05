import os
import json
import re

data_dir = r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\cleaned_data"

all_names = set()
names_with_context = []

pattern = re.compile(r'\b(Dr\.|Dr|Prof\.|Prof|Professor|Mr\.|Mr|Ms\.|Ms|Mrs\.|Mrs)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)')

for filename in sorted(os.listdir(data_dir)):
    if filename.endswith(".json"):
        path = os.path.join(data_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            try:
                chunks = json.load(f)
                for chunk in chunks:
                    text = chunk.get("text", "")
                    title = chunk.get("title", "")
                    topic = chunk.get("topic", "")
                    
                    for match in pattern.finditer(text + " " + title):
                        full_match = match.group(0)
                        title_prefix = match.group(1)
                        name = match.group(2)
                        
                        # Clean name
                        name = re.sub(r'\s+', ' ', name).strip()
                        full_name = f"{title_prefix} {name}"
                        
                        if full_name not in all_names:
                            all_names.add(full_name)
                            names_with_context.append({
                                "name": full_name,
                                "topic": topic,
                                "file": filename,
                                "chunk_index": chunk.get("chunk_index"),
                                "context": text[max(0, match.start() - 50):min(len(text), match.end() + 100)]
                            })
            except Exception as e:
                pass

print(f"Found {len(all_names)} candidate names:")
for nc in sorted(names_with_context, key=lambda x: x["name"]):
    print(f"Name: {nc['name']}")
    print(f"  Topic: {nc['topic']} | File: {nc['file']} | Chunk: {nc['chunk_index']}")
    print(f"  Context: ...{nc['context'].strip().replace('\n', ' ')}...")
    print("-" * 50)
