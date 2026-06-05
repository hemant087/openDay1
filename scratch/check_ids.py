import os
import json

data_dir = "cleaned_data"
files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json'))

missing_id_count = 0
total_chunks = 0

for filename in files:
    filepath = os.path.join(data_dir, filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        if not isinstance(chunks, list):
            chunks = [chunks]
        for idx, chunk in enumerate(chunks):
            total_chunks += 1
            if "id" not in chunk or not chunk["id"]:
                print(f"Missing ID: {filename} at index {idx}")
                missing_id_count += 1
    except Exception as e:
        print(f"Error reading {filename}: {e}")

print(f"Checked {total_chunks} chunks. Missing IDs: {missing_id_count}")
