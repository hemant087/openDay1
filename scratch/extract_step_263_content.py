import json

transcript_path = r"C:\Users\hr2u25\.gemini\antigravity-ide\brain\5834d4de-c84a-46a9-b41d-84a0c8074042\.system_generated\logs\transcript.jsonl"
output_path = r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\scratch\whisper_reconstructed.txt"

with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        if "initwhispermic" in line.lower() and '"step_index":263' in line:
            step = json.loads(line)
            content = step.get('content', '')
            with open(output_path, 'w', encoding='utf-8') as out:
                out.write(content)
            print(f"Wrote Step 263 content to {output_path}")
            break
