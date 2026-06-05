import json

transcript_path = r"C:\Users\hr2u25\.gemini\antigravity-ide\brain\5834d4de-c84a-46a9-b41d-84a0c8074042\.system_generated\logs\transcript.jsonl"

with open(transcript_path, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f):
        if "263" in line:
            try:
                step = json.loads(line)
                if step.get('step_index') == 263:
                    print(f"Match found on line {line_num}!")
                    print(f"Keys: {list(step.keys())}")
                    print(f"Type: {step.get('type')}")
                    # Write the line to a file
                    with open(r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\scratch\step_263.txt", "w", encoding="utf-8") as out:
                        json.dump(step, out, indent=2)
                    break
            except Exception as e:
                pass
