import json

transcript_path = r"C:\Users\hr2u25\.gemini\antigravity-ide\brain\5834d4de-c84a-46a9-b41d-84a0c8074042\.system_generated\logs\transcript.jsonl"
output_path = r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\scratch\vad_chunks.txt"

with open(transcript_path, 'r', encoding='utf-8') as f, open(output_path, 'w', encoding='utf-8') as out:
    for line_num, line in enumerate(f):
        if '"step_index":263' in line or 'step_index":263' in line:
            try:
                step = json.loads(line)
                out.write(f"=== STEP 263 ===\n")
                tool_calls = step.get('tool_calls', [])
                for tc in tool_calls:
                    args = tc.get('args', {})
                    chunks = args.get('ReplacementChunks', [])
                    for idx, chunk in enumerate(chunks):
                        out.write(f"--- Chunk {idx} ---\n")
                        rep = chunk.get('ReplacementContent', '')
                        unescaped = rep.encode('utf-8').decode('unicode_escape')
                        out.write(unescaped)
                        out.write("\n" + "="*80 + "\n")
            except Exception as e:
                out.write(f"Error parsing line {line_num}: {e}\n")

print(f"Extracted Step 263 to {output_path}")
