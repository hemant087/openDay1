import urllib.request
import json

url = "http://localhost:8000/api/university/delete-chunk"
chunk_id = "https://www.delhi.southampton.ac.uk/programmes/data-science-msc/#chunk-0"

data = json.dumps({"id": chunk_id}).encode('utf-8')
req = urllib.request.Request(
    url, 
    data=data, 
    headers={'Content-Type': 'application/json'},
    method='POST'
)

try:
    with urllib.request.urlopen(req) as res:
        print(f"Status: {res.status}")
        print(f"Body: {res.read().decode('utf-8')}")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'):
        print(f"Error Body: {e.read().decode('utf-8')}")
