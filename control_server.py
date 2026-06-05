import http.server
import socketserver
import subprocess
import os
import json
import webbrowser
import threading
import traceback
import time
import tempfile
from datetime import datetime
from collections import defaultdict
import math

import urllib.request
import urllib.parse

# ── faster-whisper (STT) ──────────────────────────────────────────────────────
try:
    from faster_whisper import WhisperModel
    _whisper_model = None
    _whisper_lock  = threading.Lock()
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("[WARN] faster-whisper not installed. Run: pip install faster-whisper")

def get_whisper_model():
    """Lazy-load the Whisper model on first use with multiple fallbacks."""
    global _whisper_model
    if not WHISPER_AVAILABLE:
        return None
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                # Order of preferred models: environment var, then small, then base, then tiny
                preferred_model = os.environ.get("WHISPER_MODEL", "small")
                models_to_try = [preferred_model]
                for m in ["small", "base", "tiny"]:
                    if m not in models_to_try:
                        models_to_try.append(m)
                
                # Try each model in sequence
                for model_name in models_to_try:
                    print(f"[INFO] Attempting to load faster-whisper model '{model_name}'...")
                    
                    # 1. Try on GPU (cuda)
                    try:
                        print(f"[INFO] Trying '{model_name}' on GPU (cuda)...")
                        _whisper_model = WhisperModel(model_name, device="cuda", compute_type="float16")
                        print(f"[INFO] Success! Loaded '{model_name}' on CUDA.")
                        break
                    except Exception as gpu_err:
                        print(f"[INFO] CUDA load failed for '{model_name}' ({gpu_err}). Trying on CPU (int8)...")
                        
                    # 2. Try on CPU
                    try:
                        _whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
                        print(f"[INFO] Success! Loaded '{model_name}' on CPU (int8).")
                        break
                    except Exception as cpu_err:
                        print(f"[WARN] Failed to load '{model_name}' on CPU: {cpu_err}")
                
                if _whisper_model is None:
                    print("[ERROR] Failed to load any faster-whisper model!")
    return _whisper_model

try:

    import serial
except ImportError:
    serial = None

class ArduinoProxy:
    def __init__(self):
        self.ser = None
        
    def connect(self, port):
        self.disconnect()
        if not serial: return False, "pyserial not installed"
        try:
            self.ser = serial.Serial(port, 9600, timeout=1)
            return True, "Connected"
        except Exception as e:
            return False, str(e)
            
    def disconnect(self):
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
            
    def send(self, cmd):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write((cmd + '\n').encode('utf-8'))
                return True
            except:
                return False
        return False

arduino_proxy = ArduinoProxy()

PORT = 8000

# ── Cached Weather (avoids 5s network call per request) ──────────────────────
_weather_cache = {"data": "Unknown", "ts": 0}
_WEATHER_TTL = 60  # refresh every 60 seconds

def _fetch_weather():
    try:
        with urllib.request.urlopen("https://wttr.in/Gurugram?format=%C+%t", timeout=4) as r:
            return r.read().decode('utf-8').strip()
    except Exception:
        return _weather_cache["data"]

def get_live_info():
    """Returns live info with cached weather (< 1ms after first call)."""
    now = time.time()
    if now - _weather_cache["ts"] > _WEATHER_TTL:
        _weather_cache["data"] = _fetch_weather()
        _weather_cache["ts"] = now
    dt = datetime.now()
    return {
        "weather": _weather_cache["data"],
        "location": "Gurugram, India",
        "date": dt.strftime("%d/%m/%Y"),
        "time": dt.strftime("%I:%M %p")
    }

# --- University Knowledge Base (Inverted-Index RAG) ---
UNIVERSITY_DATA = []       # [{text, title}, ...]
INVERTED_INDEX = {}        # word -> [chunk_indices]
RAG_IDF = {}               # word -> idf value
RAG_AVG_DL = 1.0           # average doc length
RAG_DOC_LENGTHS = []       # [length of chunk 0, length of chunk 1, ...]
_STOP = frozenset("the is at in of and to for a an on it by as or be was are with that this from but not have has had can will what how who when where which about your you they their there been would could should does did its also than then very just more do our we all any each few some most other into over such only these those through between during before after above below up down out off no nor so too own same both if while".split())

# ── People Database (people_data/) ───────────────────────────────────────────
PEOPLE_DB = []           # list of all chunk dicts from people_data/ files
PEOPLE_ALIAS_MAP = {}    # lowercase alias string → set of people_data file paths (canonical person key)
PEOPLE_BY_KEY = {}       # canonical person key → list of chunk dicts (sorted by chunk_index)

# ── Courses Database (courses_data/) ─────────────────────────────────────────
COURSES_DB = []          # list of all chunk dicts from courses_data/ files
COURSES_BY_KEY = {}      # course slug → list of chunk dicts (sorted by chunk_index)
COURSES_ALIAS_MAP = {}   # lowercase alias string → set of course slugs

def load_people_data():
    """Loads all JSON files in people_data/ into PEOPLE_DB and builds an alias lookup map."""
    global PEOPLE_DB, PEOPLE_ALIAS_MAP, PEOPLE_BY_KEY
    import re as _re
    data_dir = "people_data"
    if not os.path.exists(data_dir):
        print("[WARN] people_data/ folder not found — person lookup disabled.")
        return

    PEOPLE_DB.clear()
    PEOPLE_ALIAS_MAP.clear()
    PEOPLE_BY_KEY.clear()

    files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json'))
    _title_re = _re.compile(r'\b(dr|prof|mr|mrs|ms|sir|professor|doctor)\.?\s*', _re.IGNORECASE)

    for filename in files:
        filepath = os.path.join(data_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            if not isinstance(chunks, list):
                continue

            # Use the filename (without .json) as the canonical person key
            person_key = filename[:-5]  # e.g. "dr-chitrakalpa-sen"
            if person_key not in PEOPLE_BY_KEY:
                PEOPLE_BY_KEY[person_key] = []

            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                chunk['_person_key'] = person_key
                PEOPLE_DB.append(chunk)
                PEOPLE_BY_KEY[person_key].append(chunk)

                # Register every alias into the map
                for alias in chunk.get('aliases', []):
                    alias_lower = alias.lower().strip()
                    # Raw alias
                    PEOPLE_ALIAS_MAP.setdefault(alias_lower, set()).add(person_key)
                    # Title-stripped alias
                    stripped = _title_re.sub('', alias_lower).strip()
                    if stripped:
                        PEOPLE_ALIAS_MAP.setdefault(stripped, set()).add(person_key)

        except Exception as e:
            print(f"[WARN] Failed to load people_data/{filename}: {e}")

    # Sort chunks per person by chunk_index
    for key in PEOPLE_BY_KEY:
        PEOPLE_BY_KEY[key].sort(key=lambda c: c.get('chunk_index', 0))

    print(f"[INFO] Loaded people_data: {len(PEOPLE_BY_KEY)} people, {len(PEOPLE_ALIAS_MAP)} aliases, {len(PEOPLE_DB)} chunks")


def search_people_data(query):
    """
    Alias-aware person lookup in people_data/.
    Returns {'found': True, 'person_key': '...', 'name': '...', 'chunks': [...text...]}
    or       {'found': False}
    """
    import re as _re
    if not query or not PEOPLE_ALIAS_MAP:
        return {'found': False}

    _title_re = _re.compile(r'\b(dr|prof|mr|mrs|ms|sir|professor|doctor)\.?\s*', _re.IGNORECASE)
    clean = _title_re.sub('', query).strip().lower()

    def _resolve(candidate):
        """Given a lowercase string, return the matching person_key or None."""
        # 1. Exact match
        keys = PEOPLE_ALIAS_MAP.get(candidate)
        if keys:
            return next(iter(keys))
        # 2. Substring scan — check if candidate is a substring of any alias
        for alias, alias_keys in PEOPLE_ALIAS_MAP.items():
            if len(candidate) >= 3 and candidate in alias:
                return next(iter(alias_keys))
            if len(alias) >= 3 and alias in candidate:
                return next(iter(alias_keys))
        return None

    # Try the full cleaned query
    person_key = _resolve(clean)

    # Try individual tokens (handles "tell me about Chitrakalpa")
    if not person_key:
        tokens = [t.strip('.,;:!?()') for t in clean.split() if len(t) >= 3]
        for token in tokens:
            person_key = _resolve(token)
            if person_key:
                break

    if not person_key or person_key not in PEOPLE_BY_KEY:
        return {'found': False}

    chunks = PEOPLE_BY_KEY[person_key]
    # Pick the display name from the first chunk's title (strip "Name Aliases..." alias chunks)
    name = ''
    for c in chunks:
        title = c.get('title', '')
        if 'alias' not in title.lower():
            # Extract name from title — usually "Dr X Y: ..."
            name = title.split(':')[0].strip()
            break
    if not name:
        name = person_key.replace('-', ' ').title()

    # Return text of all non-alias chunks (alias-chunks are helper text, not profile text)
    text_chunks = [c.get('text', '') for c in chunks if 'alias-chunk' not in c.get('id', '') and c.get('text', '')]

    # Collect all unique aliases for this person
    aliases = []
    for c in chunks:
        for a in c.get('aliases', []):
            if a not in aliases:
                aliases.append(a)

    return {
        'found': True,
        'person_key': person_key,
        'name': name,
        'aliases': aliases,
        'chunks': text_chunks
    }


_KW_STOP = frozenset(
    "the is at in of and to for a an on it by as or be was are with that this from but "
    "not have has had can will what how who when where which about your you they their "
    "there been would could should does did its also than then very just more do our we "
    "all any each few some most other into over such only these those through between "
    "during before after above below up down out off no nor so too own same both if "
    "while tell me about please find list show associated related works here faculty "
    "staff teacher lecturer dean director who is are there anyone anyone".split()
)

# Role/keyword synonyms — maps query keywords to terms found in people data
_ROLE_SYNONYMS = {
    "cs": ["computer science", "computing"],
    "compsci": ["computer science", "computing"],
    "computing": ["computer science", "computing"],
    "business": ["business management", "management", "finance"],
    "finance": ["finance", "accounting", "economics"],
    "economics": ["economics", "finance"],
    "accounting": ["accounting", "finance"],
    "research": ["research", "researcher"],
    "teaching": ["teaching", "learning and teaching", "education"],
    "learning": ["learning", "teaching", "education"],
    "leadership": ["leadership", "director", "dean"],
    "software": ["software", "software engineering"],
    "engineering": ["software engineering", "engineering"],
    "ai": ["artificial intelligence", "machine learning", "ai"],
    "ml": ["machine learning", "artificial intelligence"],
    "data": ["data science", "data", "analytics"],
    "maths": ["mathematics", "maths", "statistics"],
    "math": ["mathematics", "maths", "statistics"],
    "admission": ["admissions", "counsellor", "student"],
    "counsellor": ["counsellor", "admissions", "advisor"],
    "creative": ["creative computing", "creative"],
    "web": ["web", "internet", "networking"],
    "network": ["networking", "network", "communications"],
    "security": ["security", "cybersecurity"],
    "cyber": ["cybersecurity", "security"],
    "law": ["law", "legal", "regulation"],
    "psychology": ["psychology", "behavioural"],
    "marketing": ["marketing", "business"],
    "entrepreneurship": ["entrepreneurship", "startup", "innovation"],
    "innovation": ["innovation", "entrepreneurship"],
    "phd": ["phd", "doctorate", "doctoral"],
    "msc": ["msc", "masters", "postgraduate"],
    "bsc": ["bsc", "undergraduate", "degree"],
    "placement": ["placement", "internship", "career"],
    "career": ["career", "placement", "industry"],
}


def search_people_by_keyword(query, top_n=5):
    """
    Keyword/role-based people search.
    Returns a list of people whose profile chunks match the keyword.
    Each result: {'name': '...', 'role': '...', 'summary': '...'}
    Returns [] if nobody matches.
    """
    import re as _re
    if not query or not PEOPLE_BY_KEY:
        return []

    _title_re = _re.compile(r'\b(dr|prof|mr|mrs|ms|sir|professor|doctor)\.?\s*', _re.IGNORECASE)
    clean_q = _title_re.sub('', query).lower().strip()

    # Expand query using synonyms
    raw_tokens = [t.strip('.,;:!?()') for t in clean_q.split() if len(t) >= 2 and t not in _KW_STOP]
    search_terms = set(raw_tokens)
    for tok in list(raw_tokens):
        for syn in _ROLE_SYNONYMS.get(tok, []):
            search_terms.update(syn.lower().split())

    if not search_terms:
        return []

    # Score each person: sum how many terms match in their text/keywords/titles
    person_scores = defaultdict(float)
    person_names = {}
    person_roles = {}
    person_summaries = {}

    for person_key, chunks in PEOPLE_BY_KEY.items():
        best_name = person_key.replace('-', ' ').title()
        best_role = ''
        best_summary = ''

        for chunk in chunks:
            if 'alias-chunk' in chunk.get('id', ''):
                continue  # skip alias-only chunks

            # Extract display name and role from title
            title = chunk.get('title', '')
            if title and ':' in title:
                parts = title.split(':', 1)
                if not best_name or best_name == person_key.replace('-', ' ').title():
                    best_name = parts[0].strip()
                if not best_role:
                    best_role = parts[1].strip()

            summary = chunk.get('summary', '') or chunk.get('text', '')[:200]
            if summary and not best_summary:
                best_summary = summary

            # Build a combined text field for matching
            text = chunk.get('text', '').lower()
            kw_text = ' '.join(chunk.get('keywords', [])).lower()
            combined = f"{title.lower()} {text} {kw_text}"

            # Score: each matching term adds weight
            for term in search_terms:
                if len(term) >= 3 and term in combined:
                    person_scores[person_key] += 1.0
                # Bonus for exact phrase matches in title (role)
                if len(term) >= 4 and term in title.lower():
                    person_scores[person_key] += 1.5

        person_names[person_key] = best_name
        person_roles[person_key] = best_role
        person_summaries[person_key] = best_summary

    if not person_scores:
        return []

    # Return top matching people with score > 0
    ranked = sorted(
        [(k, v) for k, v in person_scores.items() if v > 0],
        key=lambda x: x[1], reverse=True
    )[:top_n]

    results = []
    for person_key, score in ranked:
        results.append({
            'name': person_names.get(person_key, person_key.replace('-', ' ').title()),
            'role': person_roles.get(person_key, ''),
            'summary': person_summaries.get(person_key, ''),
            'score': round(score, 2)
        })

    return results


def load_university_data():
    """Loads pre-built JSON index or falls back to chunk parsing."""
    global UNIVERSITY_DATA, INVERTED_INDEX, RAG_IDF, RAG_AVG_DL, RAG_DOC_LENGTHS
    
    index_file = "rag_index.json"
    t0 = time.time()
    
    if os.path.exists(index_file):
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                UNIVERSITY_DATA = data["chunks"]
                INVERTED_INDEX = data["index"]
                RAG_IDF = data.get("idf", {})
                RAG_AVG_DL = data.get("meta", {}).get("avg_doc_length", 1.0)
                RAG_DOC_LENGTHS = data.get("meta", {}).get("doc_lengths", [])
            ms = (time.time() - t0) * 1000
            print(f"[INFO] Loaded pre-built RAG index: {len(UNIVERSITY_DATA)} chunks in {ms:.0f}ms")
            return
        except Exception as e:
            print(f"[WARN] Failed to load {index_file}: {e}. Falling back to chunk files.")
    
    # Fallback
    data_dir = "cleaned_data"
    if not os.path.exists(data_dir):
        print("[WARN] cleaned_data folder not found.")
        return
    try:
        inverted_set = defaultdict(set)
        files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json'))
        for filename in files:
            with open(os.path.join(data_dir, filename), 'r', encoding='utf-8') as f:
                chunks = json.load(f)
                for chunk in chunks:
                    idx = len(UNIVERSITY_DATA)
                    text = chunk.get("text", "")
                    title = chunk.get("title", "")
                    kw = " ".join(chunk.get("keywords", []))
                    UNIVERSITY_DATA.append({"text": text, "title": title})
                    combined = f"{text} {title} {kw}".lower().split()
                    RAG_DOC_LENGTHS.append(len(combined))
                    for word in set(combined):
                        clean = word.strip(".,;:!?()[]{}\"'")
                        if len(clean) >= 2 and clean not in _STOP:
                            inverted_set[clean].add(idx)
        INVERTED_INDEX = {k: list(v) for k, v in inverted_set.items()}
        RAG_AVG_DL = sum(RAG_DOC_LENGTHS) / len(RAG_DOC_LENGTHS) if RAG_DOC_LENGTHS else 1.0
        
        # Simple IDF for fallback
        N = len(UNIVERSITY_DATA)
        for term, postings in INVERTED_INDEX.items():
            df = len(postings)
            RAG_IDF[term] = math.log((N - df + 0.5) / (df + 0.5) + 1)
            
        ms = (time.time() - t0) * 1000
        print(f"[INFO] Built RAG index from chunks: {len(UNIVERSITY_DATA)} chunks in {ms:.0f}ms")
    except Exception as e:
        print(f"[ERROR] Failed to index university data: {e}")

def search_university_data(query, top_n=3):
    """BM25 search with name-aware fuzzy matching for partial/titled names."""
    if not query: return []

    # ── 1. Strip common titles so "Dr. Sharma" and "Sharma" both match ──
    import re
    clean_query = re.sub(r'\b(dr|prof|mr|mrs|ms|sir|professor|doctor)\.?\b', ' ', query, flags=re.IGNORECASE)
    clean_query = clean_query.strip()

    # ── 2. Tokenise — allow names as short as 2 chars ──
    raw_words = [w.strip(".,;:!?()\\'\"[]{}") for w in clean_query.lower().split()]
    words = [w for w in raw_words if len(w) >= 2 and w not in _STOP]
    if not words: return []

    scores = defaultdict(float)
    k1 = 1.5
    b  = 0.75

    # ── 3. Exact BM25 on index ──
    for word in words:
        postings = INVERTED_INDEX.get(word, [])
        idf = RAG_IDF.get(word, 1.0)
        for idx in postings:
            doc_len = RAG_DOC_LENGTHS[idx] if idx < len(RAG_DOC_LENGTHS) else RAG_AVG_DL
            tf = 1
            numerator   = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (doc_len / RAG_AVG_DL))
            scores[idx] += idf * (numerator / denominator)

    # ── 4. Fallback: substring scan for partial names (e.g. "sharma" hits "dr. sharma") ──
    # Run substring match for all query tokens of length >= 3 to ensure partial names match
    lower_q = clean_query.lower()
    name_tokens = [w for w in lower_q.split() if len(w) >= 3 and w not in _STOP]
    for name in name_tokens:
        for idx, chunk in enumerate(UNIVERSITY_DATA):
            if name in chunk["text"].lower() or name in chunk.get("title", "").lower():
                scores[idx] += 3.0   # bonus weight for substring hit

    if not scores: return []
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [UNIVERSITY_DATA[i]["text"] for i, _ in top]

def load_courses_data():
    """Loads all JSON files in courses_data/ into COURSES_DB and builds slug/alias lookup maps."""
    global COURSES_DB, COURSES_BY_KEY, COURSES_ALIAS_MAP
    data_dir = "courses_data"
    if not os.path.exists(data_dir):
        print("[WARN] courses_data/ folder not found — course lookup disabled.")
        return

    COURSES_DB.clear()
    COURSES_BY_KEY.clear()
    COURSES_ALIAS_MAP.clear()

    # Skip aggregate/summary files
    _SKIP = {"all_courses_flat.json", "courses_summary.json"}
    files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json') and f not in _SKIP)

    for filename in files:
        filepath = os.path.join(data_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            if not isinstance(chunks, list):
                continue

            # Canonical key is the filename without .json  e.g. "computer-science-bsc-hons"
            course_key = filename[:-5]
            if course_key not in COURSES_BY_KEY:
                COURSES_BY_KEY[course_key] = []

            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                chunk['_course_key'] = course_key
                COURSES_DB.append(chunk)
                COURSES_BY_KEY[course_key].append(chunk)

        except Exception as e:
            print(f"[WARN] Failed to load courses_data/{filename}: {e}")

    # Sort chunks per course by chunk_index
    for key in COURSES_BY_KEY:
        COURSES_BY_KEY[key].sort(key=lambda c: c.get('chunk_index', 0))

    # Build alias map: slug words + programme name words + common short forms
    for course_key in COURSES_BY_KEY:
        # Full slug (e.g. "computer-science-bsc-hons")
        COURSES_ALIAS_MAP.setdefault(course_key, set()).add(course_key)
        # Slug with spaces (e.g. "computer science bsc hons")
        slug_spaced = course_key.replace('-', ' ')
        COURSES_ALIAS_MAP.setdefault(slug_spaced, set()).add(course_key)
        # Individual slug words >= 4 chars
        for word in course_key.split('-'):
            if len(word) >= 4:
                COURSES_ALIAS_MAP.setdefault(word.lower(), set()).add(course_key)
        # Extract programme name from the first chunk title
        first_chunks = COURSES_BY_KEY[course_key]
        if first_chunks:
            title = first_chunks[0].get('title', '')
            # Title format: "Programme Name: Section" — take the part before ':'
            prog_name = title.split(':')[0].strip().lower()
            if prog_name:
                COURSES_ALIAS_MAP.setdefault(prog_name, set()).add(course_key)
                # Also register each word of the programme name
                for word in prog_name.split():
                    if len(word) >= 4:
                        COURSES_ALIAS_MAP.setdefault(word, set()).add(course_key)

    print(f"[INFO] Loaded courses_data: {len(COURSES_BY_KEY)} courses, {len(COURSES_ALIAS_MAP)} aliases, {len(COURSES_DB)} chunks")


def search_courses_data(query):
    """
    Alias-aware course lookup in courses_data/.
    Scores all matching candidates by query-token overlap to resolve ambiguity
    (e.g. 'msc finance' should rank finance-msc above accounting-and-finance-bsc-hons).
    """
    if not query or not COURSES_BY_KEY:
        return {'found': False}

    clean = query.strip().lower()
    q_tokens = [t.strip('.,;:!?()') for t in clean.split() if t.strip('.,;:!?()')]

    if not q_tokens:
        return {'found': False}

    # Detect requested study levels
    query_has_msc = any(t in ("msc", "master", "masters") for t in q_tokens)
    query_has_bsc = any(t in ("bsc", "bachelor", "bachelors") for t in q_tokens)
    query_has_beng = any(t in ("beng",) for t in q_tokens)

    scores = {}

    for course_key, chunks in COURSES_BY_KEY.items():
        score = 0.0
        slug_tokens = course_key.split('-')

        # Determine course study level
        course_level = None
        if "msc" in slug_tokens:
            course_level = "msc"
        elif "bsc" in slug_tokens:
            course_level = "bsc"
        elif "beng" in slug_tokens:
            course_level = "beng"

        # 1. Study level matching (strong differentiator)
        if query_has_msc:
            if course_level == "msc":
                score += 15.0
            elif course_level in ("bsc", "beng"):
                score -= 15.0
        if query_has_bsc:
            if course_level == "bsc":
                score += 15.0
            elif course_level in ("msc", "beng"):
                score -= 15.0
        if query_has_beng:
            if course_level == "beng":
                score += 15.0
            elif course_level in ("msc", "bsc"):
                score -= 15.0

        # 2. Token overlap with course slug
        matched_tokens = 0
        for qt in q_tokens:
            if qt in slug_tokens:
                score += 8.0
                matched_tokens += 1
            else:
                # Substring match within slug tokens
                for st in slug_tokens:
                    if len(qt) >= 4 and qt in st:
                        score += 3.0
                        matched_tokens += 1
                        break
                    elif len(st) >= 4 and st in qt:
                        score += 3.0
                        matched_tokens += 1
                        break

        # 3. Exact slug match
        spaced_slug = course_key.replace('-', ' ')
        if clean == course_key or clean == spaced_slug:
            score += 50.0

        # 4. Word-set match bonus (e.g. "msc data science" vs "data-science-msc")
        slug_token_set = set(slug_tokens)
        q_token_set = set(q_tokens)
        if q_token_set == slug_token_set:
            score += 30.0
        elif q_token_set.issubset(slug_token_set):
            score += 15.0

        # 5. First chunk title matching
        if chunks:
            title = chunks[0].get('title', '')
            prog_name = title.split(':')[0].strip().lower() if ':' in title else ''
            if prog_name:
                if clean == prog_name:
                    score += 40.0
                # Match tokens against programme name
                prog_words = prog_name.split()
                for qt in q_tokens:
                    if qt in prog_words:
                        score += 5.0
                    else:
                        for pw in prog_words:
                            if len(qt) >= 4 and qt in pw:
                                score += 2.0
                                break

        # We need at least one keyword token match to consider this course
        if matched_tokens > 0:
            # Tie-breaker: prefer shorter/more-specific slugs by subtracting a fraction of slug length
            score -= len(slug_tokens) * 0.1
            scores[course_key] = score

    if not scores:
        return {'found': False}

    # Rank and select best candidate
    best_key, best_score = max(scores.items(), key=lambda x: x[1])

    # Threshold score to filter out irrelevant/weak matches
    if best_score < 5.0:
        return {'found': False}

    chunks = COURSES_BY_KEY[best_key]
    name = ''
    for c in chunks:
        title = c.get('title', '')
        if ':' in title:
            name = title.split(':')[0].strip()
            break
    if not name:
        name = best_key.replace('-', ' ').title()

    # Select most relevant chunks (using their summary/short version) based on query intent
    clean_q = clean.lower()
    intent_fees = any(w in clean_q for w in ["fee", "cost", "tuition", "inr", "scholarship", "deposit", "payment", "instalment", "pay"])
    intent_eligibility = any(w in clean_q for w in ["eligibility", "criteria", "admission", "apply", "application", "requirement", "score", "mark", "gpa", "ielts", "grade", "cbse", "cisce", "board"])
    intent_curriculum = any(w in clean_q for w in ["study", "curriculum", "module", "subject", "semester", "syllabus", "learn", "structure", "hons", "honours"])
    intent_careers = any(w in clean_q for w in ["career", "job", "employability", "employer", "prospect"])

    matched_chunks = []
    if intent_fees:
        matched_chunks = [c for c in chunks if c.get("topic") == "fees"]
    elif intent_eligibility:
        matched_chunks = [c for c in chunks if c.get("topic") == "admissions"]
    elif intent_curriculum:
        matched_chunks = [c for c in chunks if c.get("topic") == "programme-curriculum"]
    elif intent_careers:
        matched_chunks = [c for c in chunks if c.get("topic") == "careers"]

    # Fallback to overview if no specific intent matches or no chunks found
    if not matched_chunks:
        overview_chunks = [c for c in chunks if c.get("topic") == "programme-overview"]
        if overview_chunks:
            matched_chunks = overview_chunks[:2]
        else:
            matched_chunks = chunks[:2]

    # Return summaries (concise, pre-written details) to prevent LLM from getting long-winded/boring
    selected_texts = []
    for c in matched_chunks:
        summary = c.get("summary", "").strip()
        if summary:
            selected_texts.append(summary)
        else:
            text = c.get("text", "").strip()
            if len(text) > 250:
                selected_texts.append(text[:250] + "...")
            else:
                selected_texts.append(text)

    return {
        'found': True,
        'course_key': best_key,
        'name': name,
        'chunks': selected_texts
    }


_COURSE_KW_STOP = frozenset(
    "the is at in of and to for a an on it by as or be was are with that this from but "
    "not have has had can will what how who when where which about your you they their "
    "there been would could should does did its also than then very just more do our we "
    "all any each few some most other into over such only these those through between "
    "during before after above below up down out off no nor so too own same both if "
    "while tell me about please find list show associated related course courses programme "
    "programs study studying join pursue offer offered".split()
)


def search_courses_by_keyword(query, top_n=5):
    """
    Keyword-based course search across courses_data/.
    Returns a list of dicts: [{'name': '...', 'overview': '...', 'slug': '...', 'score': N}, ...]
    """
    if not query or not COURSES_BY_KEY:
        return []

    clean_q = query.lower().strip()
    raw_tokens = [t.strip('.,;:!?()') for t in clean_q.split() if len(t) >= 3 and t not in _COURSE_KW_STOP]
    search_terms = set(raw_tokens)

    if not search_terms:
        return []

    course_scores = defaultdict(float)
    course_names = {}
    course_overviews = {}
    course_slugs = {}

    for course_key, chunks in COURSES_BY_KEY.items():
        best_name = course_key.replace('-', ' ').title()
        best_overview = ''

        for chunk in chunks:
            title = chunk.get('title', '')
            if title and ':' in title:
                parts = title.split(':', 1)
                if not best_name or best_name == course_key.replace('-', ' ').title():
                    best_name = parts[0].strip()

            summary = chunk.get('summary', '') or chunk.get('text', '')[:200]
            if summary and not best_overview:
                best_overview = summary

            text = chunk.get('text', '').lower()
            kw_text = ' '.join(chunk.get('keywords', [])).lower()
            combined = f"{title.lower()} {text} {kw_text}"

            for term in search_terms:
                if len(term) >= 3 and term in combined:
                    course_scores[course_key] += 1.0
                if len(term) >= 4 and term in title.lower():
                    course_scores[course_key] += 1.5

        course_names[course_key] = best_name
        course_overviews[course_key] = best_overview
        course_slugs[course_key] = course_key

    if not course_scores:
        return []

    ranked = sorted(
        [(k, v) for k, v in course_scores.items() if v > 0],
        key=lambda x: x[1], reverse=True
    )[:top_n]

    results = []
    for course_key, score in ranked:
        results.append({
            'name': course_names.get(course_key, course_key.replace('-', ' ').title()),
            'overview': course_overviews.get(course_key, ''),
            'slug': course_key,
            'score': round(score, 2)
        })

    return results


# Initialize on startup
load_university_data()
load_people_data()
load_courses_data()

class ControlHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/whisper/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"available": WHISPER_AVAILABLE}).encode())

        elif self.path == '/api/arduino/list-ports':
            # Return all available COM ports so the UI can auto-populate
            try:
                if serial:
                    import serial.tools.list_ports
                    ports = [
                        {"port": p.device, "description": p.description}
                        for p in serial.tools.list_ports.comports()
                    ]
                else:
                    ports = []
            except Exception as e:
                ports = []
                print(f"[WARN] list_ports error: {e}")
            # Always ensure COM4 and COM8 appear as options even if disconnected
            known = {p["port"] for p in ports}
            for fallback in ["COM4", "COM6", "COM7", "COM8"]:
                if fallback not in known:
                    ports.append({"port": fallback, "description": "—"})
            ports.sort(key=lambda x: int(''.join(filter(str.isdigit, x["port"])) or '0'))
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(ports).encode())

        elif self.path.startswith('/api/courses/keyword-search'):
            query = ""
            if '?' in self.path:
                qs = urllib.parse.parse_qs(self.path.split('?', 1)[1])
                query = qs.get('q', [''])[0]
            results = search_courses_by_keyword(query)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'found': len(results) > 0, 'courses': results}).encode())

        elif self.path.startswith('/api/courses/search'):
            query = ""
            if '?' in self.path:
                qs = urllib.parse.parse_qs(self.path.split('?', 1)[1])
                query = qs.get('q', [''])[0]
            result = search_courses_data(query)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        elif self.path.startswith('/api/university/search'):
            query = ""
            if '?' in self.path:
                qs = urllib.parse.parse_qs(self.path.split('?', 1)[1])
                query = qs.get('q', [''])[0]
            
            results = search_university_data(query)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(results).encode())

        elif self.path.startswith('/api/people/keyword-search'):
            # Keyword/role-based people search — returns list of matching people
            query = ""
            if '?' in self.path:
                qs = urllib.parse.parse_qs(self.path.split('?', 1)[1])
                query = qs.get('q', [''])[0]
            results = search_people_by_keyword(query)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'found': len(results) > 0, 'people': results}).encode())

        elif self.path.startswith('/api/people/search'):
            query = ""
            if '?' in self.path:
                qs = urllib.parse.parse_qs(self.path.split('?', 1)[1])
                query = qs.get('q', [''])[0]
            result = search_people_data(query)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        elif self.path == '/api/live-info':
            info = get_live_info()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(info).encode())
        elif self.path == '/api/system/status':
            try:
                # Check if Ollama is running
                ollama_check = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ollama.exe"], capture_output=True, text=True)
                is_ollama_running = "ollama.exe" in ollama_check.stdout
                
                # Check if Robot Backend is running (searching for RoboGreet in window titles)
                robot_check = subprocess.run(["tasklist", "/FI", "WINDOWTITLE eq RoboGreet AI*"], capture_output=True, text=True)
                is_robot_running = "python.exe" in robot_check.stdout or "cmd.exe" in robot_check.stdout
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "online" if (is_ollama_running or is_robot_running) else "offline",
                    "ollama": is_ollama_running,
                    "robot": is_robot_running
                }).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif self.path.startswith('/api/ollama/'):
            # Forward GET to Ollama
            target_path = self.path[len('/api/ollama'):]
            url = f"http://localhost:11434{target_path}"
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as r:
                    self.send_response(r.status)
                    for k, v in r.headers.items():
                        if k.lower() not in ['content-length', 'connection', 'transfer-encoding']:
                            self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(r.read())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            return super().do_GET()

    def do_POST(self):
        if self.path == '/api/system/start':
            try:
                print("[CONTROL] Starting System Components...")
                os.environ["OLLAMA_ORIGINS"] = "*"
                # Start Ollama only (Web-only mode)
                subprocess.Popen("ollama serve", shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "System starting..."}).encode())
            except Exception as e:
                error_msg = traceback.format_exc()
                print(f"[ERROR] {error_msg}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(error_msg.encode())

        elif self.path == '/api/system/stop':
            try:
                print("[CONTROL] Stopping System Components...")
                subprocess.run(["taskkill", "/F", "/IM", "ollama.exe", "/T"], capture_output=True)
                subprocess.run(["taskkill", "/F", "/FI", "WINDOWTITLE eq RoboGreet AI*", "/T"], capture_output=True)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "System stopping..."}).encode())
            except Exception as e:
                error_msg = traceback.format_exc()
                print(f"[ERROR] {error_msg}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(error_msg.encode())

        elif self.path == '/api/system/shutdown':
            try:
                print("[CONTROL] TOTAL SYSTEM SHUTDOWN...")
                subprocess.run(["taskkill", "/F", "/IM", "ollama.exe", "/T"], capture_output=True)
                subprocess.run(["taskkill", "/F", "/FI", "WINDOWTITLE eq RoboGreet AI*", "/T"], capture_output=True)
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Shutting down orchestrator...")
                
                threading.Timer(1.0, lambda: os._exit(0)).start()
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif self.path == '/api/university/delete-topic':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length) if length > 0 else b'{}'
                data = json.loads(body)
                topic = data.get("topic", "")
                
                if not topic:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Topic name required"}).encode())
                    return
                    
                # 1. Clean the files in cleaned_data
                data_dir = "cleaned_data"
                files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json'))
                for filename in files:
                    filepath = os.path.join(data_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        chunks = json.load(f)
                    
                    if isinstance(chunks, list):
                        updated_chunks = [c for c in chunks if c.get("topic") != topic]
                    elif isinstance(chunks, dict):
                        updated_chunks = [] if chunks.get("topic") == topic else chunks
                    else:
                        updated_chunks = chunks
                        
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(updated_chunks, f, indent=2, ensure_ascii=False)
                
                # 2. Rebuild the RAG index file
                import build_rag_index
                build_rag_index.build_index()
                
                # 3. Reload in memory
                load_university_data()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": f"Deleted topic '{topic}'"}).encode())
                
            except Exception as e:
                print("[ERROR] Exception in delete-topic:")
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        elif self.path == '/api/university/save-chunk':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length) if length > 0 else b'{}'
                data = json.loads(body)
                chunk_id = data.get("id", "")
                title = data.get("title", "")
                topic = data.get("topic", "")
                text = data.get("text", "")
                keywords = data.get("keywords", [])
                
                if not chunk_id:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Chunk ID required"}).encode())
                    return
                    
                # Search all files in cleaned_data/
                data_dir = "cleaned_data"
                files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json'))
                found = False
                
                for filename in files:
                    filepath = os.path.join(data_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        chunks = json.load(f)
                    
                    if not isinstance(chunks, list):
                        continue
                        
                    for chunk in chunks:
                        if chunk.get("id") == chunk_id:
                            # Update fields
                            chunk["title"] = title
                            chunk["topic"] = topic
                            chunk["text"] = text
                            chunk["keywords"] = keywords
                            chunk["tokens"] = len(text.split())
                            found = True
                            break
                            
                    if found:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            json.dump(chunks, f, indent=2, ensure_ascii=False)
                        break
                        
                if not found:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Chunk not found"}).encode())
                    return
                    
                # Rebuild RAG index and reload
                import build_rag_index
                build_rag_index.build_index()
                load_university_data()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Chunk saved successfully"}).encode())
                
            except Exception as e:
                print("[ERROR] Exception in save-chunk:")
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        elif self.path == '/api/university/delete-chunk':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length) if length > 0 else b'{}'
                data = json.loads(body)
                chunk_id = data.get("id", "")
                
                if not chunk_id:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Chunk ID required"}).encode())
                    return
                    
                # Search all files in cleaned_data/
                data_dir = "cleaned_data"
                files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json'))
                found = False
                
                for filename in files:
                    filepath = os.path.join(data_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        chunks = json.load(f)
                    
                    if not isinstance(chunks, list):
                        continue
                    
                    initial_len = len(chunks)
                    chunks = [c for c in chunks if c.get("id") != chunk_id]
                    
                    if len(chunks) < initial_len:
                        found = True
                        with open(filepath, 'w', encoding='utf-8') as f:
                            json.dump(chunks, f, indent=2, ensure_ascii=False)
                        break
                        
                if not found:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Chunk not found"}).encode())
                    return
                    
                # Rebuild RAG index and reload
                import build_rag_index
                build_rag_index.build_index()
                load_university_data()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Chunk deleted successfully"}).encode())
                
            except Exception as e:
                print("[ERROR] Exception in delete-chunk:")
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        elif self.path == '/api/university/delete-chunks':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length) if length > 0 else b'{}'
                data = json.loads(body)
                chunk_ids = data.get("ids", [])
                
                if not chunk_ids or not isinstance(chunk_ids, list):
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Chunk IDs list required"}).encode())
                    return
                
                chunk_ids_set = set(chunk_ids)
                data_dir = "cleaned_data"
                files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json'))
                deleted_count = 0
                
                for filename in files:
                    filepath = os.path.join(data_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        chunks = json.load(f)
                    
                    if not isinstance(chunks, list):
                        continue
                    
                    initial_len = len(chunks)
                    chunks = [c for c in chunks if c.get("id") not in chunk_ids_set]
                    diff = initial_len - len(chunks)
                    if diff > 0:
                        deleted_count += diff
                        with open(filepath, 'w', encoding='utf-8') as f:
                            json.dump(chunks, f, indent=2, ensure_ascii=False)
                
                if deleted_count == 0:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "No matching chunks found"}).encode())
                    return
                    
                # Rebuild RAG index and reload
                import build_rag_index
                build_rag_index.build_index()
                load_university_data()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": f"Successfully deleted {deleted_count} chunks"}).encode())
                
            except Exception as e:
                print("[ERROR] Exception in delete-chunks:")
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        elif self.path == '/api/university/create-chunk':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length) if length > 0 else b'{}'
                data = json.loads(body)
                title = data.get("title", "")
                topic = data.get("topic", "")
                text = data.get("text", "")
                keywords = data.get("keywords", [])
                
                if not title or not text or not topic:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Title, topic, and text are required"}).encode())
                    return
                    
                import uuid
                # Generate unique ID
                unique_suffix = str(uuid.uuid4())[:8]
                chunk_id = f"https://www.delhi.southampton.ac.uk/user-created/{topic}/#chunk-{unique_suffix}"
                
                new_chunk = {
                    "id": chunk_id,
                    "source_url": f"https://www.delhi.southampton.ac.uk/user-created/{topic}/",
                    "source_file": "chunk_user_created.json",
                    "title": title,
                    "path": f"/user-created/{topic}/",
                    "chunk_index": len(UNIVERSITY_DATA),
                    "text": text,
                    "tokens": len(text.split()),
                    "language": "en",
                    "summary": text[:150] + "..." if len(text) > 150 else text,
                    "keywords": keywords,
                    "keywords_method": "user-created",
                    "keyword_scores": {},
                    "entities": [],
                    "topic": topic,
                    "embedding_id": None,
                    "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
                }
                
                # Append to cleaned_data/chunk_user_created.json
                data_dir = "cleaned_data"
                filepath = os.path.join(data_dir, "chunk_user_created.json")
                
                chunks = []
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        try:
                            chunks = json.load(f)
                            if not isinstance(chunks, list):
                                chunks = []
                        except:
                            chunks = []
                            
                chunks.append(new_chunk)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(chunks, f, indent=2, ensure_ascii=False)
                    
                # Rebuild RAG index and reload
                import build_rag_index
                build_rag_index.build_index()
                load_university_data()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Chunk created successfully"}).encode())
                
            except Exception as e:
                print("[ERROR] Exception in create-chunk:")
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        elif self.path == '/api/whisper/transcribe':
            if not WHISPER_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "faster-whisper not installed. Run: pip install faster-whisper"}).encode())
                return

            length = int(self.headers.get('Content-Length', 0))
            audio_data = self.rfile.read(length)
            content_type = self.headers.get('Content-Type', 'audio/wav')
            suffix = '.wav' if 'wav' in content_type else '.webm'
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(audio_data)
                    tmp_path = tmp.name

                model = get_whisper_model()
                # Provide contextual vocabulary/names and Indian English accent guide to Whisper
                prompt_vocab = (
                    "A conversation about the University of Southampton Delhi campus at International Tech Park Gurgaon, "
                    "Sector 59. Academic programs, admissions, fees, and courses. "
                    "Names of staff and faculty: Dr. Vishal Talwar, Dr. Chitrakalpa Sen, Dr. Rajesh Yadav, "
                    "Dr. Samiya Khan, Dr. Nitish Gupta, Dr. Aparna Pasumarthy, Dr. Nalini Sharan, Dr. Sagaya Amalathas, "
                    "Dr. Samridhi Suman, Dr. Tanu Gupta, Dr. Vaibhav Gandhi, Mr. Hemant Raj, Ms. Anupama Saini, "
                    "Ms. Monisha Tandon, Professor Eloise Phillips, Dr. Mohammed Anam Akhtar."
                )
                segments, _ = model.transcribe(
                    tmp_path,
                    language="en",
                    beam_size=5,
                    vad_filter=False,
                    initial_prompt=prompt_vocab
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()
                print(f"[WHISPER] '{text}'")

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"text": text}).encode())

            except Exception as e:
                print(f"[WHISPER ERROR] {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try: os.unlink(tmp_path)
                    except: pass

        elif self.path == '/api/arduino/connect':
            length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(length))
            port = data.get("port", "COM4")
            success, msg = arduino_proxy.connect(port)
            self.send_response(200 if success else 500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success" if success else "error", "message": msg}).encode())
            
        elif self.path == '/api/arduino/disconnect':
            arduino_proxy.disconnect()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode())
            
        elif self.path == '/api/arduino/command':
            length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(length))
            cmd = data.get("command", "")
            success = arduino_proxy.send(cmd)
            self.send_response(200 if success else 500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success" if success else "error"}).encode())
        elif self.path.startswith('/api/ollama/'):
            # Forward POST to Ollama
            target_path = self.path[len('/api/ollama'):]
            url = f"http://localhost:11434{target_path}"
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length > 0 else b''
            try:
                req = urllib.request.Request(url, data=body, method='POST')
                if 'Content-Type' in self.headers:
                    req.add_header('Content-Type', self.headers['Content-Type'])
                with urllib.request.urlopen(req, timeout=180) as r:
                    self.send_response(r.status)
                    for k, v in r.headers.items():
                        if k.lower() not in ['content-length', 'connection', 'transfer-encoding']:
                            self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(r.read())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self.end_headers()

def start_all_components():
    """Launches all background services automatically."""
    try:
        print("[CONTROL] AUTO-START: Launching Web-Only components...")
        os.environ["OLLAMA_ORIGINS"] = "*"
        subprocess.Popen("ollama serve", shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        return True
    except Exception as e:
        print(f"[ERROR] Auto-start failed: {e}")
        return False

# Run the server
if __name__ == "__main__":
    import sys
    
    # Check for auto-start flag
    if "--auto" in sys.argv:
        start_all_components()

    handler = ControlHandler
    # Threaded server: requests don't block each other
    class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True
    with ThreadedServer(("", PORT), handler) as httpd:
        url = f"http://localhost:{PORT}"
        print(f"RoboGreet Control Server running at {url}")
        
        # Try to open in Chrome specifically
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
        ]
        
        opened = False
        for path in chrome_paths:
            if os.path.exists(path):
                subprocess.Popen([path, "--start-maximized", "--app=" + url])
                opened = True
                break
        
        if not opened:
            try:
                # Fallback to starting Chrome via system Command Prompt
                subprocess.Popen(["cmd", "/c", "start", "chrome", "--app=" + url])
                opened = True
            except:
                pass
                
        if not opened:
            print(f"[WARNING] Google Chrome not found. RoboGreet is optimized to run ONLY in Google Chrome. Please open {url} manually in Google Chrome.")
            
        httpd.serve_forever()
