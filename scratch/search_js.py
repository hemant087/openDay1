import sys

# Ensure UTF-8 output encoding for Windows consoles
sys.stdout.reconfigure(encoding='utf-8')

with open(r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\app.js", "r", encoding="utf-8") as f:
    lines = f.readlines()

search_terms = ["utt.onstart"]

for term in search_terms:
    print(f"=== Matches for '{term}' ===")
    matches = 0
    for idx, line in enumerate(lines):
        if term.lower() in line.lower():
            # Clean up the output string to avoid console printing issues
            clean_line = line.strip().encode('ascii', errors='replace').decode('ascii')
            print(f"Line {idx+1}: {clean_line[:120]}")
            matches += 1
            if matches >= 15:
                print("... truncated ...")
                break
    if matches == 0:
        print("No matches")
    print()
