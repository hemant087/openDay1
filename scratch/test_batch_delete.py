import urllib.request
import json
import os

def post_json(url, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as res:
        return res.status, json.loads(res.read().decode('utf-8'))

def main():
    base_url = "http://localhost:8000"
    create_url = f"{base_url}/api/university/create-chunk"
    delete_batch_url = f"{base_url}/api/university/delete-chunks"
    
    print("1. Creating 3 temporary chunks...")
    titles = [
        "Batch Delete Test Chunk A",
        "Batch Delete Test Chunk B",
        "Batch Delete Test Chunk C"
    ]
    
    for title in titles:
        payload = {
            "title": title,
            "topic": "overview",
            "text": f"This is temporary text for {title} used during automated integration testing.",
            "keywords": ["batch", "delete", "test"]
        }
        status, response = post_json(create_url, payload)
        assert status == 200, f"Failed to create chunk {title}"
        print(f"   Created: {title}")
        
    # Read chunk_user_created.json to find IDs
    user_created_path = os.path.join("cleaned_data", "chunk_user_created.json")
    assert os.path.exists(user_created_path), "chunk_user_created.json does not exist!"
    
    with open(user_created_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
        
    test_chunk_ids = []
    for chunk in chunks:
        if chunk.get("title") in titles:
            test_chunk_ids.append(chunk.get("id"))
            
    print(f"2. Found created test chunk IDs: {test_chunk_ids}")
    assert len(test_chunk_ids) == 3, f"Expected 3 test chunks, found {len(test_chunk_ids)}"
    
    print("3. Executing batch delete of the 3 test chunks...")
    payload = {"ids": test_chunk_ids}
    status, response = post_json(delete_batch_url, payload)
    print(f"   Response Status: {status}")
    print(f"   Response Body: {response}")
    
    assert status == 200, "Batch delete request failed"
    assert response.get("status") == "success", "Response did not indicate success"
    
    # Verify they are gone from chunk_user_created.json
    if os.path.exists(user_created_path):
        with open(user_created_path, 'r', encoding='utf-8') as f:
            remaining_chunks = json.load(f)
        remaining_titles = [c.get("title") for c in remaining_chunks]
        for t in titles:
            assert t not in remaining_titles, f"Chunk with title '{t}' was not deleted!"
            
    print("\n[SUCCESS] Verification Successful! Batch delete works perfectly on the backend.")

if __name__ == "__main__":
    main()
