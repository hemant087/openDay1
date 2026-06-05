import json

transcript_path = r"C:\Users\hr2u25\.gemini\antigravity-ide\brain\5834d4de-c84a-46a9-b41d-84a0c8074042\.system_generated\logs\transcript.jsonl"
output_path = r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\scratch\extracted_media_recorder.txt"

with open(transcript_path, 'r', encoding='utf-8') as f, open(output_path, 'w', encoding='utf-8') as out:
    for line_num, line in enumerate(f):
        if "mediarecorder" in line.lower():
            try:
                step = json.loads(line)
                out.write(f"=== Step index: {step.get('step_index')}, Type: {step.get('type')}, Status: {step.get('status')} ===\n")
                content = step.get('content', '')
                if "MediaRecorder" in content:
                    out.write(content)
                    out.write("\n" + "="*80 + "\n")
                
                # Check tool_calls or output
                tool_calls = step.get('tool_calls', [])
                for tc in tool_calls:
                    args = tc.get('arguments', {})
                    args_str = json.dumps(args, indent=2)
                    if "MediaRecorder" in args_str:
                        out.write(args_str)
                        out.write("\n" + "="*80 + "\n")
            except Exception as e:
                out.write(f"Error parsing line {line_num}: {e}\n")

print(f"Extracted to {output_path}")
