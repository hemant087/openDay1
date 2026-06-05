import os
import json
import re
from collections import defaultdict

data_dir = r"c:\Users\hr2u25\OneDrive - University of Southampton\Desktop\openDay1\cleaned_data"

slugs = [
    "dr-akhtar", "dr-aparna-pasumarthy", "dr-chitrakalpa-sen", "dr-nalini-sharan",
    "dr-nitish-gupta", "dr-rajesh-yadav", "dr-sagaya-amalathas", "dr-samiya-khan",
    "dr-samridhi-suman", "dr-tanu-gupta", "dr-vaibhav-gandhi", "dr-vishal-talwar",
    "mr-hemant-raj", "ms-anupama-saini", "ms-monisha-tandon", "professor-eloise-phillips"
]

faculty_data = []

# First, read all chunks and group them by slug
all_chunks = []
for filename in sorted(os.listdir(data_dir)):
    if filename.endswith(".json"):
        path = os.path.join(data_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            try:
                all_chunks.extend(json.load(f))
            except Exception as e:
                print(f"Error loading {filename}: {e}")

for slug in slugs:
    # Gather chunks belonging to this slug
    chunks = []
    for chunk in all_chunks:
        if chunk.get("topic") != "faculty-bio":
            continue
        p = chunk.get("path", "")
        title = chunk.get("title", "")
        
        # Match if slug is in path (e.g. /team/dr-aparna-pasumarthy/)
        if slug in p:
            chunks.append(chunk)
            continue
            
        # Match if it's from /study/our-team/ and name parts are in title
        name_parts = slug.split("-")[1:]
        if "/study/our-team" in p and name_parts and all(part in title.lower() for part in name_parts):
            chunks.append(chunk)
            continue
            
    if not chunks:
        print(f"Warning: no chunks found for {slug}")
        continue
        
    # Sort chunks by chunk_index to keep sequence correct
    chunks = sorted(chunks, key=lambda x: x.get("chunk_index", 0))
    
    # 1. Combine texts and titles
    combined_text = " ".join(c.get("text", "") for c in chunks)
    
    # 2. Extract Name and Role
    name = None
    role = None
    
    # Check chunks for clear title definitions
    for c in chunks:
        t = c.get("title", "")
        if ":" in t:
            parts = t.split(":")
            cand_name = parts[0].strip()
            if re.match(r'^(Dr|Prof|Mr|Ms|Professor)\b', cand_name, re.I):
                name = cand_name
                role = parts[1].strip()
                break
        elif "," in t:
            parts = t.split(",")
            cand_name = parts[0].strip()
            if re.match(r'^(Dr|Prof|Mr|Ms|Professor)\b', cand_name, re.I):
                name = cand_name
                role = parts[1].strip()
                break

    # Fallbacks for Name
    if not name:
        for c in chunks:
            t = c.get("title", "")
            match = re.match(r'^(Dr\.|Dr|Prof\.|Prof|Professor|Mr\.|Mr|Ms\.|Ms)\s+([A-Za-z\s]+)', t)
            if match:
                name = match.group(0).strip()
                break
    if not name:
        parts = slug.split("-")
        title_prefix = parts[0].capitalize()
        name_parts = [p.capitalize() for p in parts[1:]]
        name = f"{title_prefix}. " + " ".join(name_parts)
        
    name = re.sub(r"'s\b.*", "", name).strip()
    
    # Clean up name: some might have punctuation
    name = re.sub(r'\s+', ' ', name)
    
    # Fallback for Role
    if not role:
        # Check text
        patterns = [
            r'(?:is|working as|appointed as|serves as)\s+(?:a\s+|the\s+)?([^.,;]{5,80})',
        ]
        for pat in patterns:
            m = re.search(pat, combined_text, re.I)
            if m:
                role = m.group(1).strip()
                break
    if not role:
        role = "Academic Faculty / Staff"
        
    role = re.sub(r'\s+at\s+University.*', '', role, flags=re.I)
    role = re.sub(r'\s+at\s+the\s+University.*', '', role, flags=re.I)
    role = re.sub(r'\s+and\s+brings\s+over.*', '', role, flags=re.I)
    role = role.strip(" .,;'")
    
    # 3. Extract Department
    department = "General"
    dept_keywords = {
        "Computing": ["computing", "cybersecurity", "software", "computer science"],
        "Economics": ["economics", "economist"],
        "Business": ["business", "management", "marketing", "careers", "career advancement"],
        "Accounting & Finance": ["accounting", "finance", "bba"],
        "Library & Information Services": ["library", "librarian"],
        "Student Experience": ["student experience", "student affairs"],
        "Senior Leadership": ["provost", "chief operating officer", "leadership team"]
    }
    
    # Look in role and text
    found_dept = False
    for dept_name, keywords in dept_keywords.items():
        if any(kw in role.lower() for kw in keywords) or any(kw in combined_text.lower()[:500] for kw in keywords):
            department = dept_name
            found_dept = True
            break
            
    # 4. Extract Email / Contact Info
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', combined_text)
    email = emails[0] if emails else "Not Available"
    
    # 5. Extract Research Interests
    interests = []
    # Check for Research Interest keyword list or split
    interest_match = re.search(r'Research Interest[s]?\s*:\s*([^.\n]+)', combined_text, re.I)
    if interest_match:
        items = re.split(r',|;', interest_match.group(1))
        interests = [item.strip() for item in items if item.strip()]
    else:
        # Look for keywords or text patterns
        # e.g., "specializing in X, Y, and Z"
        spec_match = re.search(r'specializ(?:ing|es)\s+in\s+([^.\n]{5,150})', combined_text, re.I)
        if spec_match:
            items = re.split(r',|and', spec_match.group(1))
            interests = [item.strip() for item in items if len(item.strip()) > 3]
            
    # Remove bad characters/formatting from interests
    clean_interests = []
    for inter in interests:
        inter = re.sub(r'\s+', ' ', inter).strip(" .,;")
        if len(inter) > 3 and len(inter) < 60:
            clean_interests.append(inter)
    interests = list(dict.fromkeys(clean_interests)) # Deduplicate
    
    # 6. Extract Biography Summary (2-3 clean sentences)
    # Get the text of the first profile chunk (chunk_index 0 or 1 usually contains the intro)
    intro_chunk = chunks[0]
    for c in chunks:
        if c.get("chunk_index") == 0:
            intro_chunk = c
            break
    intro_text = intro_chunk.get("text", "")
    
    # Clean sentences
    sentences = re.split(r'(?<=[.!?])\s+', intro_text)
    # Skip sentences that are just navigation or menu items
    valid_sentences = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) < 30:
            continue
        if "read more" in sent.lower() or "view profile" in sent.lower() or "choose to search" in sent.lower():
            continue
        valid_sentences.append(sent)
        
    bio_summary = " ".join(valid_sentences[:3])
    # If bio_summary is empty, fall back to a snippet of combined text
    if not bio_summary:
        bio_summary = combined_text[:300] + "..."
        
    # 7. Extract Publications (if any)
    publications = []
    # Search for publications chunk
    pub_text = ""
    for c in chunks:
        if "publication" in c.get("title", "").lower() or "article" in c.get("title", "").lower() or "proceeding" in c.get("title", "").lower():
            pub_text += " " + c.get("text", "")
            
    if pub_text:
        # Simple extraction of publications: look for capitalized names and years in parentheses or double quotes
        # or items separated by semi-colons/periods
        pub_list = re.split(r'\n|(?<=\d{4}\))|(?<=\.)(?=\s+[A-Z])', pub_text)
        for pub in pub_list:
            pub = pub.strip(" .,;-\t")
            if len(pub) > 20 and any(char.isdigit() for char in pub):
                # Clean up multiple spaces
                pub = re.sub(r'\s+', ' ', pub)
                # Keep it if it looks like a publication title
                publications.append(pub)
                
    # 8. Source URL
    source_url = chunks[0].get("source_url", f"https://www.delhi.southampton.ac.uk/team/{slug}/")
    
    faculty_data.append({
        "slug": slug,
        "name": name,
        "role": role,
        "department": department,
        "email": email,
        "research_interests": interests[:8],
        "bio": bio_summary,
        "publications": publications[:5],
        "source_url": source_url
    })

print(json.dumps(faculty_data[0], indent=2))
print("=" * 60)
print(json.dumps(faculty_data[1], indent=2))
