import os
import json

data_dir = "cleaned_data"
chunk_id = "https://www.delhi.southampton.ac.uk/programmes/data-science-msc/#chunk-0"

files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json'))
print(f"Found {len(files)} files.")

found = False
for filename in files:
    filepath = os.path.join(data_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    
    if not isinstance(chunks, list):
        print(f"{filename} is not a list")
        continue
    
    for c in chunks:
        # Print a few to check structure
        if "id" in c and c["id"] == chunk_id:
            print(f"Match found in {filename}!")
            found = True
            break
    if found:
        break

if not found:
    print("No match found.")
