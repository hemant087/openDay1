import json
import re

transcript_path = r"C:\Users\hr2u25\.gemini\antigravity-ide\brain\5834d4de-c84a-46a9-b41d-84a0c8074042\.system_generated\logs\transcript.jsonl"
output_path = r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\scratch\extracted_whisper_functions.txt"

functions_to_find = ["initWhisperMic", "startWhisperListening", "blobToWav", "transcribeWithWhisper"]

with open(transcript_path, 'r', encoding='utf-8') as f, open(output_path, 'w', encoding='utf-8') as out:
    for line_num, line in enumerate(f):
        if "initwhispermic" in line.lower():
            out.write(f"=== MATCH Line {line_num} ===\n")
            out.write(line[:25000])  # write first 25000 chars of matching line
            out.write("\n" + "="*80 + "\n")

print(f"Extracted function definitions to {output_path}")
