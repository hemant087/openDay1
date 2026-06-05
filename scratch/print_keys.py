import json

transcript_path = r"C:\Users\hr2u25\.gemini\antigravity-ide\brain\5834d4de-c84a-46a9-b41d-84a0c8074042\.system_generated\logs\transcript.jsonl"

with open(transcript_path, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f):
        if "initwhispermic" in line.lower():
            try:
                step = json.loads(line)
                print(f"Step {step.get('step_index')}: keys = {list(step.keys())}")
                if 'tool_calls' in step:
                    for tc in step['tool_calls']:
                        print(f"  Tool Call keys: {list(tc.keys())}")
                        if 'arguments' in tc:
                            print(f"    Arguments keys: {list(tc['arguments'].keys())}")
                            for k, v in tc['arguments'].items():
                                print(f"      Arg {k}: type={type(v)}, len={len(str(v))}")
                break
            except Exception as e:
                print(e)
