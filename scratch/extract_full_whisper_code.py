import json

transcript_path = r"C:\Users\hr2u25\.gemini\antigravity-ide\brain\5834d4de-c84a-46a9-b41d-84a0c8074042\.system_generated\logs\transcript.jsonl"
output_path = r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\scratch\whisper_full_code.txt"

with open(transcript_path, 'r', encoding='utf-8') as f, open(output_path, 'w', encoding='utf-8') as out:
    for line_num, line in enumerate(f):
        if "initwhispermic" in line.lower():
            try:
                step = json.loads(line)
                out.write(f"=== STEP {step.get('step_index')} ===\n")
                
                # Check tool_calls
                tool_calls = step.get('tool_calls', [])
                for tc in tool_calls:
                    args = tc.get('args', {})
                    rep = args.get('ReplacementContent', '')
                    if rep:
                        # Unescape raw string newlines and backslashes
                        unescaped = rep.encode('utf-8').decode('unicode_escape')
                        out.write(unescaped)
                        out.write("\n" + "="*80 + "\n")
            except Exception as e:
                out.write(f"Error parsing line {line_num}: {e}\n")

print(f"Extracted to {output_path}")
