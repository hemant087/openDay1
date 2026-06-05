import urllib.request
import json
import time

url_create = "http://localhost:8000/api/university/create-chunk"
url_delete = "http://localhost:8000/api/university/delete-chunk"

# 1. Create a new chunk
payload_create = {
    "title": "Test Chunk Title",
    "topic": "overview",
    "text": "This is a temporary test chunk text containing at least thirty characters to pass validation.",
    "keywords": ["test", "temporary"]
}

data_create = json.dumps(payload_create).encode('utf-8')
req_create = urllib.request.Request(
    url_create,
    data=data_create,
    headers={'Content-Type': 'application/json'},
    method='POST'
)

print("Sending create request...")
try:
    with urllib.request.urlopen(req_create) as res:
        print(f"Create Status: {res.status}")
        body = res.read().decode('utf-8')
        print(f"Create Body: {body}")
        res_data = json.loads(body)
except Exception as e:
    print(f"Create Error: {e}")
    if hasattr(e, 'read'):
        print(f"Create Error Body: {e.read().decode('utf-8')}")
    exit(1)

# Wait a brief moment for the index to rebuild
time.sleep(2)

# 2. Find the chunk id from user-created chunks
import os
filepath = "cleaned_data/chunk_user_created.json"
if not os.path.exists(filepath):
    print("Error: chunk_user_created.json was not created!")
    exit(1)

with open(filepath, 'r', encoding='utf-8') as f:
    chunks = json.load(f)

test_chunk = [c for c in chunks if c.get("title") == "Test Chunk Title"]
if not test_chunk:
    print("Error: Test chunk not found in chunk_user_created.json!")
    exit(1)

chunk_id = test_chunk[0]["id"]
print(f"Found created chunk ID: {chunk_id}")

# 3. Delete the chunk
payload_delete = {"id": chunk_id}
data_delete = json.dumps(payload_delete).encode('utf-8')
req_delete = urllib.request.Request(
    url_delete,
    data=data_delete,
    headers={'Content-Type': 'application/json'},
    method='POST'
)

print("Sending delete request...")
try:
    with urllib.request.urlopen(req_delete) as res:
        print(f"Delete Status: {res.status}")
        print(f"Delete Body: {res.read().decode('utf-8')}")
except Exception as e:
    print(f"Delete Error: {e}")
    if hasattr(e, 'read'):
        print(f"Delete Error Body: {e.read().decode('utf-8')}")
    exit(1)

print("Flow test completed successfully!")
