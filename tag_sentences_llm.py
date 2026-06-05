import json
import os
import re
import requests

DATA_DIR = "cleaned_data"
OUTPUT_FILE = "sentence_keyword_tags.json"
OLLAMA_URL = "http://localhost:11434/api/generate"

def get_ollama_model():
    """Finds an available local LLM from Ollama."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        models = resp.json().get("models", [])
        if models:
            # Prioritize faster, smaller models if available
            for m in models:
                if "qwen" in m["name"].lower() or "tiny" in m["name"].lower():
                    return m["name"]
            return models[0]["name"]
    except:
        print("Warning: Could not connect to Ollama. Make sure it is running.")
        pass
    return "qwen"

def extract_keywords_llm(sentence, model):
    """Uses the LLM to extract keywords for a single sentence."""
    prompt = f"Extract 2 to 4 comma-separated keywords from this sentence. Output ONLY the keywords, no extra text.\nSentence: \"{sentence}\"\nKeywords:"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,  # Low temperature for strict, consistent keyword extraction
            "num_predict": 30
        }
    }
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=10)
        if r.status_code == 200:
            text = r.json().get("response", "").strip()
            # Clean up the LLM response
            text = text.replace('"', '').replace('\n', '')
            keywords = [k.strip() for k in text.split(',') if len(k.strip()) > 2]
            return keywords
    except Exception as e:
        print(f"  [Error] LLM request failed: {e}")
    return []

def main():
    model = get_ollama_model()
    print(f"Starting sentence tagging using LLM: {model}")
    
    if not os.path.exists(DATA_DIR):
        print(f"Error: {DATA_DIR} not found.")
        return

    files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.json')])
    tagged_sentences = []
    
    # LIMIT to first 5 chunks for demonstration purposes!
    # Processing all 292 files sentence-by-sentence with an LLM will take a very long time.
    limit_chunks = 5 
    processed = 0

    for filename in files:
        if processed >= limit_chunks:
            break
            
        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                chunks = json.load(f)
            except Exception:
                continue
            
            for chunk in chunks:
                if processed >= limit_chunks:
                    break
                
                text = chunk.get("text", "")
                if not text: 
                    continue
                
                # Basic sentence splitting by punctuation
                sentences = re.split(r'(?<=[.!?])\s+', text)
                
                for s in sentences:
                    s = s.strip()
                    if len(s) < 15: continue  # Skip extremely short fragments
                    
                    print(f"\nAnalyzing: {s[:60]}...")
                    keywords = extract_keywords_llm(s, model)
                    print(f"Keywords: {keywords}")
                    
                    tagged_sentences.append({
                        "chunk_id": chunk.get("id"),
                        "sentence": s,
                        "keywords": keywords
                    })
                
                processed += 1

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(tagged_sentences, f, ensure_ascii=False, indent=2)
        
    print(f"\n=======================================================")
    print(f"Saved {len(tagged_sentences)} tagged sentences to {OUTPUT_FILE}.")
    print("NOTE: This was a demonstration running on the first 5 chunks.")
    print("To process all files, edit the script and change 'limit_chunks' to infinity.")
    print(f"=======================================================")

if __name__ == "__main__":
    main()
