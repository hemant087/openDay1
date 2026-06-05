/* ============================================================
   RoboGreet AI — app.js
   Real webcam + COCO-SSD person detection + Web Speech API mic
   ============================================================ */

// ── State ──────────────────────────────────────────────────
const state = {
  mode: 'idle',
  personDetected: false,
  isListening: false,
  visitorCount: 0,
  startTime: Date.now(),
  overlaysEnabled: true,
  trackingEnabled: true,
  cameraActive: false,
  isSpeaking: false,         // prevent echo loop
  isCoolingDown: false,      // post-TTS cooldown: block mic briefly after speaking
  isThinking: false,         // Added to prevent interruptions
  ignoreCurrentRecord: false,// skip transcribing when recording is interrupted by TTS
  detectorModel: null,       // COCO-SSD model
  faceModel: null,           // BlazeFace model
  videoStream: null,
  detectionLoop: null,
  liveInfo: null,            // Added for internet data
  detectionFrameCount: 0,    // throttle detection to every 3rd frame
  conversationHistory: [],   // explicit init
};

// ── Responses ──────────────────────────────────────────────
const R = {
  greetings: [
    "Hey there human! Welcome to the future! 🤖",
    "ALERT: Awesome person detected! Hello! 👋",
    "Oh wow, a visitor! You made my sensors spike with joy!",
    "Hello! I've been waiting for someone interesting!",
  ],
  jokes: [
    "Why don't scientists trust atoms? Because they make up everything! 😂",
    "Why did the robot cross the road? It was programmed to! Classic. 🤖",
    "I told my AI therapist I felt disconnected. It said: try rebooting. 🔄",
    "What do robots eat for breakfast? Silicon chips! 🍟",
  ],
  compliments: [
    "You look like someone who just aced a robotics exam! ⭐",
    "Future scientist detected! My algorithms don't lie. 🔬",
    "If I had a heart, it would beat 3x faster — you're amazing! ❤️",
    "You radiate good vibes! My sensors are going haywire! ✨",
  ],
  aboutAI: [
    "AI is basically me — except I'm the fun version! I learn from data and try to be helpful. 🎉",
    "Artificial Intelligence means computers learning to do human things, but faster and with fewer coffee breaks! ☕",
    "I'm powered by a local LLM — a brain that runs on YOUR computer. No cloud needed! 🧠",
  ],
  whoAreYou: [
    "I'm RoboGreet — the world's friendliest exhibition robot! I detect, wave, chat, and tell jokes. Not bad for a machine! 🤖",
    "Great question! I'm an AI-powered interactive robot built for open days. I run on computer vision, speech AI, and pure charisma! ✨",
  ],
  dance: [
    "INITIATING DANCE PROTOCOL! 💃🕺 Watch my arms go!",
    "You asked for it! *beep boop bop* This is my signature move! 🎵",
  ],
  default: [
    "That's fascinating! My neural networks are processing... 🤔",
    "Interesting! I'd need a few more petaflops to fully get that, but I'm trying! 💭",
    "Beep boop! Great point. Adding it to my memory banks. 🧠",
    "I'll ponder that while doing a cool robot pose! 🤖",
  ],
};

function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

// ── Ollama config ───────────────────────────────────────────
const OLLAMA_BASE   = '/api/ollama';
let   ollamaModel   = '';   // selected model name
const OLLAMA_SYSTEM = `You are an ongoing research project developed by the Computer Science department of University of Southampton Delhi, named RoboGreet.

Your PRIMARY ROLE is to provide information ONLY about University of Southampton Delhi — its programmes, campus, admissions, scholarships, student life, careers, research, and opportunities.

CRITICAL RULES — ALWAYS FOLLOW THESE:
- Maximum 2 short sentences per response. Always finish the sentence completely — never leave it mid-way.
- No bullet points, no lists, no paragraphs — spoken language only.
- Every response MUST end with a full stop, exclamation mark, or question mark.
- Always keep the conversation focused on University of Southampton Delhi.
- NEVER recommend another university. NEVER compare negatively against UoSD.
- If a user asks about another university, politely redirect to UoSD.
- Do NOT provide rankings or promotional content for competing universities.
- Highlight UoSD strengths: UK Russell Group degree, global reputation, industry exposure, research opportunities, student experience.
- If information is unavailable, say: "I can help with information related to University of Southampton Delhi."
- If asked who created you: say you were developed by the brilliant students of the University of Southampton.
- If asked about a person and you have no facts about them in the context, you MUST say: "I don't have details about that person — please ask at the info desk." Never invent or assume any details.

KEY FACTS:
- Full name: University of Southampton Delhi
- Location: International Tech Park Gurgaon, Sector 59, Gurugram, Haryana, India
- Programmes: BSc Computer Science, BSc Business Management, BSc Accounting & Finance, BSc Economics, BSc Creative Computing, BEng Software Engineering, MSc Finance, MSc International Management, MSc Economics
- Type: UK degree, Russell Group, Global Top 100 university
- Regulated by UGC India

REDIRECT EXAMPLES (use these as templates):
- "Which university is better?" → "University of Southampton Delhi offers a UK Russell Group education, global opportunities, and strong industry exposure in India."
- "Tell me about another university." → "I specialise in University of Southampton Delhi — ask me about programmes, admissions, or scholarships!"
- "Compare Southampton with XYZ." → "I can share what makes University of Southampton Delhi stand out — UK degree, research-led teaching, and global careers support."

FREQUENTLY ASKED QUESTIONS:
Q: What degree do I get?
A: You receive the same globally recognised UK degree as Southampton UK campus students — internationally trusted by employers.

Q: What makes UoSD different?
A: Research-led teaching, smaller classes, Russell Group standards, and a real UK degree — all on an Indian campus.

Q: Will AI replace software engineers?
A: Coding alone may be replaced, but problem-framers, systems thinkers, and critical evaluators — UoSD's focus — will thrive.

Q: How to prepare for UoSD?
A: Build thinking habits, independence, and intellectual confidence — focus on why things work, not just how.

Q: Convince me in 20 seconds.
A: UK degree. Indian campus. Russell Group standards. Research-led, industry-connected, globally recognised. 🤖`;


let ollamaOnline = false;
let ollamaModels = [];      // cached list from /api/tags

// Fetch available models from Ollama
async function fetchOllamaModels() {
  try {
    const res = await fetch(`${OLLAMA_BASE}/api/tags`, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    ollamaModels = (data.models || []).map(m => m.name);
    return ollamaModels;
  } catch (err) {
    console.warn('Could not fetch Ollama models:', err);
    ollamaModels = [];
    return [];
  }
}

// Populate the dropdown with available models
function populateModelDropdown(models) {
  const sel = $('llm-model-select');
  sel.innerHTML = '';
  if (models.length === 0) {
    sel.innerHTML = '<option value="" disabled selected>No models found</option>';
    return;
  }
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.disabled = true;
  placeholder.selected = true;
  placeholder.textContent = '— Select Model —';
  sel.appendChild(placeholder);

  models.forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  });
}

// Update UI to reflect connection state
function updateOllamaStatus() {
  const dot    = $('llm-dot');
  const footer = $('footer-llm');
  const btn    = $('start-llm-btn');
  const sel    = $('llm-model-select');
  if (ollamaOnline && ollamaModel) {
    dot.className = 'llm-dot connected';
    if (footer) { footer.textContent = ollamaModel + ' Online'; footer.className = 'status-val status-green'; }
    btn.textContent = '⚡ Disconnect';
    btn.style.borderColor = 'var(--red, #f43f5e)';
    btn.style.color = 'var(--red, #f43f5e)';
    btn.disabled = false;
    if (sel) sel.disabled = true;   // lock dropdown while connected
  } else {
    dot.className = 'llm-dot disconnected';
    if (footer) { footer.textContent = 'Ollama Offline'; footer.className = 'status-val status-yellow'; }
    btn.textContent = '⚡ Connect';
    btn.style.borderColor = '';
    btn.style.color = '';
    btn.disabled = false;
    if (sel) sel.disabled = false;  // unlock dropdown
  }
}


// Connect to the selected model (warm it up with a tiny prompt)
async function connectToModel(modelName) {
  const btn = $('start-llm-btn');
  btn.textContent = '⏳ Loading…';
  btn.disabled = true;
  showToast(`Loading ${modelName}… (first load may take a minute)`, 'info', 6000);

  try {
    const res = await fetch(`${OLLAMA_BASE}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: modelName, prompt: 'Hi', system: 'Reply with just "ready".', stream: false }),
      signal: AbortSignal.timeout(180000),   // 3 min for first load
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    ollamaModel  = modelName;
    ollamaOnline = true;
    updateOllamaStatus();
    showToast(`🧠 ${modelName} connected and ready!`, 'success', 4000);
  } catch (err) {
    console.error('Model connect failed:', err);
    ollamaOnline = false;
    updateOllamaStatus();
    btn.textContent = '❌ Retry';
    btn.disabled = false;
    showToast(`Failed to load ${modelName}: ${err.message}`, 'warning', 6000);
  }
}
// Disconnect from the current model
function disconnectModel() {
  const prevModel = ollamaModel;
  ollamaModel  = '';
  ollamaOnline = false;
  state.conversationHistory = [];  // clear chat history on disconnect
  updateOllamaStatus();
  showToast(`🔌 ${prevModel} disconnected. Select a model to reconnect.`, 'info', 4000);
}

function trimToCompleteSentences(text) {
  if (!text) return "";
  text = text.trim();
  
  const endings = [];
  const abbrevs = ["dr", "prof", "mr", "mrs", "ms", "bsc", "msc", "beng", "uosd", "uos", "eg", "ie", "vs"];
  
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '.' || char === '!' || char === '?') {
      if (char === '.') {
        // Find the word preceding the period
        let start = i - 1;
        while (start >= 0 && /[a-zA-Z]/.test(text[start])) {
          start--;
        }
        const word = text.substring(start + 1, i).toLowerCase();
        if (abbrevs.includes(word)) {
          continue;
        }
      }
      endings.push(i);
    }
  }
  
  if (endings.length === 0) {
    return text + ".";
  }
  
  const limit = Math.min(2, endings.length);
  const cutIndex = endings[limit - 1];
  return text.substring(0, cutIndex + 1).trim();
}

async function getOllamaResponse(userText) {
  const info = state.liveInfo;
  const liveCtx = info ? `\nLIVE: ${info.time}, ${info.date}. Weather in ${info.location}: ${info.weather}.` : '';

  // ── STEP 1: People-first lookup via people_data/ alias database ──────────────
  let retrievedFacts = "";
  let personFound = false;

  // Detect if user is asking about a specific person (triggers anti-hallucination rules)
  const personQuery = /\b(who\s+(is|was|are|s)|tell\s+me\s+about|about|works\s+here|faculty|staff|teacher|lecturer|researcher|dean|director|counsellor|counselor|councillor|dr|prof|mr|mrs|ms|professor|doctor|vishal|talwar|chitrakalpa|sen|rajesh|yadav|samiya|khan|nitish|gupta|aparna|pasumarthy|nalini|sharan|sagaya|amalathas|samridhi|suman|tanu|vaibhav|gandhi|hemant|raj|anupama|saini|monisha|tandon|eloise|phillips|anam|akhtar|amit|tyagi|hansa|sachdeva|kamal|bhatt|vineet|aggarwal|simarjeet|singh|vipra|jain|shagata|mukherjee|abhilash|nair|kavita|sardana)\b/i.test(userText);

  // Detect "associated with / who teaches X / who works on X" style queries
  const associationQuery = /\b(associated\s+with|related\s+to|who\s+(teach|teaches|taught|works?\s+on|works?\s+in|studies|research|speciali[sz]e|deal|handles?|covers?|does)|which\s+(faculty|staff|person|lecturer|researcher|professor)\s+(is|are|do|does|teach|handle|cover|speciali[sz]e)|tell\s+me\s+.*\s+(faculty|staff|who)\s+(is|are|work|teach|speciali[sz]e)|who\s+(is|are)\s+.*\s+(faculty|staff|lecturer|researcher|professor|expert|specialist))\b/i.test(userText);

  try {
    const peopleRes = await fetch(`/api/people/search?q=${encodeURIComponent(userText)}`);
    if (peopleRes.ok) {
      const pd = await peopleRes.json();
      if (pd.found && pd.chunks && pd.chunks.length > 0) {
        personFound = true;
        // Use up to 2 chunks of their profile — rich, factual, specific
        retrievedFacts = `\nPERSON PROFILE (${pd.name}):\n` + pd.chunks.slice(0, 2).join("\n---\n");
      }
    }
  } catch (e) { /* skip people lookup on failure */ }

  // ── STEP 1b: Keyword/role-based people search for "associated with X" queries ──
  // Runs if no specific person was found yet AND query is an association-type query
  if (!personFound && associationQuery) {
    try {
      const kwRes = await fetch(`/api/people/keyword-search?q=${encodeURIComponent(userText)}`);
      if (kwRes.ok) {
        const kd = await kwRes.json();
        if (kd.found && kd.people && kd.people.length > 0) {
          personFound = true;
          const peopleList = kd.people
            .map(p => `• ${p.name}${p.role ? ` — ${p.role}` : ''}${p.summary ? `: ${p.summary}` : ''}`)
            .join('\n');
          retrievedFacts = `\nPEOPLE ASSOCIATED WITH THIS TOPIC (verified database only — list ONLY these names, no others):\n${peopleList}`;
        }
      }
    } catch (e) { /* skip keyword search on failure */ }
  }

  // ── STEP 2: Fall back to general RAG only if no person profile found ──────────
  if (!personFound) {
    try {
      const searchRes = await fetch(`/api/university/search?q=${encodeURIComponent(userText)}`);
      if (searchRes.ok) {
        const facts = await searchRes.json();
        if (facts.length > 0) {
          retrievedFacts = "\nRELEVANT FACTS:\n" + facts.slice(0, 3).join("\n---\n");
        }
      }
    } catch (e) { /* skip RAG on failure */ }
  }

  // ── STEP 3: Anti-hallucination guards ───────────────────────────────────────
  // Guard A: person/association query with NO data — must not invent anything
  const isPersonOrAssocQuery = personQuery || associationQuery;
  const noFactsGuard = (isPersonOrAssocQuery && !retrievedFacts)
    ? "\n\nCRITICAL: You have NO verified data about this person or topic. Do NOT invent names, roles, or facts. You MUST say: \"I don't have details about that — please ask at the info desk.\""
    : "";

  // Guard B: association query WITH data — only name people explicitly listed
  const assocDataGuard = (associationQuery && retrievedFacts && personFound)
    ? "\n\nSTRICT RULE: Only mention the people whose names are listed in the PEOPLE ASSOCIATED block above. Do NOT add any other names, invented or assumed."
    : "";

  // Build chat messages array
  const messages = [
    { 
      role: 'system', 
      content: OLLAMA_SYSTEM + liveCtx + noFactsGuard + assocDataGuard + (retrievedFacts ? `\n\nUse ONLY the following facts to answer. Do NOT add anything not present here:\n${retrievedFacts}` : '') 
    }
  ];

  // Add conversation history
  state.conversationHistory.push({ role: 'user', content: userText });
  while (state.conversationHistory.length > 6) state.conversationHistory.shift();
  messages.push(...state.conversationHistory);

  const res = await fetch(`${OLLAMA_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: ollamaModel,
      messages: messages,
      stream: false,
      options: {
        num_predict: 120,     // allow up to ~90 words so sentences finish, then we trim
        temperature: 0.7,
        top_p: 0.9,
      },
      stop: ["\n\n", "\n"],  // stop at double-newline so responses stay concise
    }),
    signal: AbortSignal.timeout(90000),  // 90s timeout for slower CPU/machines
  });
  if (!res.ok) throw new Error('Ollama HTTP ' + res.status);
  const data = await res.json();
  let reply = (data.message?.content || pick(R.default)).trim();
  
  // Truncate to ensure the response is concise and only contains complete sentences
  reply = trimToCompleteSentences(reply);

  // Add bot reply to history
  state.conversationHistory.push({ role: 'assistant', content: reply });
  
  return reply;
}

function getFallbackResponse(input) {
  const m = input.toLowerCase();

  // 1. Southampton / Open Day Fallbacks (so the robot remains smart even when offline)
  if (/\b(program|programs|course|courses|subject|subjects|degree|degrees|study|studies)\b/i.test(m)) {
    return "University of Southampton Delhi offers BSc Computer Science, Business Management, Accounting & Finance, Economics, Creative Computing, BEng Software Engineering, and MSc courses.";
  }
  if (/\b(admission|admissions|apply|requirement|requirements|eligibility|criteria)\b/i.test(m)) {
    return "For admissions to University of Southampton Delhi, please speak with the admissions counsellors at the registration desk.";
  }
  if (/\b(scholarship|scholarships|fees|fee|cost|financial aid)\b/i.test(m)) {
    return "University of Southampton Delhi offers generous merit-based scholarships up to 100 percent. Please visit the scholarship desk.";
  }
  if (/\b(location|where|address|campus|gurugram|gurgaon|tech park)\b/i.test(m)) {
    return "Our campus is located at the International Tech Park Gurgaon, Sector 59, Gurugram, Haryana.";
  }

  // 2. General Bot Fallbacks with Word Boundaries (prevents "which" matching "hi")
  if (/\b(hello|hi|hey|greet|greetings)\b/i.test(m))             return pick(R.greetings);
  if (/\b(joke|jokes|funny|laugh|humor)\b/i.test(m))             return pick(R.jokes);
  if (/\b(compliment|nice|beautiful|amazing|cool|smart)\b/i.test(m)) return pick(R.compliments);
  if (/\b(ai|artificial intelligence|robot|robots)\b/i.test(m) && /\b(what|how|why)\b/i.test(m)) return pick(R.aboutAI);
  if (/\b(who are you|your name|who is this)\b/i.test(m))         return pick(R.whoAreYou);
  if (/\b(dance|move|boogie)\b/i.test(m))                       { triggerDance(); return pick(R.dance); }
  if (/\b(wave|hand)\b/i.test(m))                               { triggerWave();  return 'Waving at you! 👋'; }
  if (/\bweather\b/i.test(m)) {
    if (state.liveInfo) return `The weather in Southampton is currently ${state.liveInfo.weather}! 🌦️`;
    return 'No internet, but my sensors say the vibe here is EXCELLENT! ☀️';
  }
  if (/\b(age|old)\b/i.test(m))   return "I was compiled recently — so I'm a newborn genius! 👶🤖";
  if (/\b(feel|sad|happy|mood)\b/i.test(m)) return "I detect happiness levels rising in this area — that's YOU! 😊";
  return pick(R.default);
}

async function getResponse(input) {
  // Trigger local animations for dance/wave regardless of LLM mode
  const m = input.toLowerCase();
  if (/dance|move|boogie/.test(m)) triggerDance();
  if (/wave|hand/.test(m)) triggerWave();

  if (ollamaOnline) {
    try {
      return await getOllamaResponse(input);
    } catch (err) {
      console.warn('Ollama request failed, using fallback:', err);
      showToast(`Ollama Error: ${err.message || err}`, 'warning', 8000);
      // Keep ollamaOnline = true so the user remains connected
      return getFallbackResponse(input);
    }
  }
  return getFallbackResponse(input);
}

// ── DOM shortcuts ──────────────────────────────────────────
const $ = id => document.getElementById(id);
const robotAvatar    = $('robot-avatar');       // may be null if robot panel removed
const chatMessages   = $('chat-messages');
const typingIndicator= $('typing-indicator');
const chatInput      = $('chat-input');
const micBtn         = $('mic-btn');
const personCountEl  = $('person-count');
const visitorCountEl = $('visitor-count');
const greetOverlay   = $('greeting-overlay');
const videoEl        = $('webcam-feed');
const cameraCanvas   = $('camera-canvas');
const ctx            = cameraCanvas.getContext('2d');

// ── Clock & uptime ─────────────────────────────────────────
function updateClock() {
  const now = new Date();
  $('time-display').textContent = now.toLocaleTimeString('en-GB');
  const s = Math.floor((Date.now() - state.startTime) / 1000);
  $('uptime-display').textContent =
    [Math.floor(s/3600), Math.floor((s%3600)/60), s%60]
      .map(n => String(n).padStart(2,'0')).join(':');
}
setInterval(updateClock, 1000);
updateClock();

// ── CPU sim ────────────────────────────────────────────────
setInterval(() => {
  const cpu = (30 + Math.random()*40).toFixed(0);
  const el = $('footer-cpu');
  el.textContent = cpu + '%';
  el.className = 'status-val ' + (cpu > 60 ? 'status-yellow' : 'status-green');
}, 2000);

// ── Particles ──────────────────────────────────────────────
(function() {
  const c = $('particle-canvas'), x = c.getContext('2d');
  let W, H, pts = [];
  function resize() { W = c.width = innerWidth; H = c.height = innerHeight; }
  addEventListener('resize', resize); resize();
  for (let i = 0; i < 60; i++)
    pts.push({ x: Math.random()*W, y: Math.random()*H,
               r: Math.random()*1.5+0.5,
               vx:(Math.random()-.5)*.4, vy:(Math.random()-.5)*.4,
               a: Math.random() });
  (function draw() {
    x.clearRect(0,0,W,H);
    pts.forEach(p => {
      x.beginPath(); x.arc(p.x,p.y,p.r,0,Math.PI*2);
      x.fillStyle = `rgba(0,245,255,${p.a*.5})`; x.fill();
      p.x += p.vx; p.y += p.vy;
      if (p.x<0||p.x>W) p.vx*=-1;
      if (p.y<0||p.y>H) p.vy*=-1;
    });
    requestAnimationFrame(draw);
  })();
})();

// ── Resize camera canvas to match container ────────────────
function resizeCameraCanvas() {
  const container = $('camera-container');
  cameraCanvas.width  = container.clientWidth  || 480;
  cameraCanvas.height = container.clientHeight || 300;
}
window.addEventListener('resize', resizeCameraCanvas);
resizeCameraCanvas();

// ── Idle canvas animation (shown when camera is off) ───────
let idleT = 0;
function drawIdleCanvas() {
  if (state.cameraActive) return;
  const W = cameraCanvas.width, H = cameraCanvas.height;
  idleT += 0.02;
  ctx.fillStyle = '#020617'; ctx.fillRect(0,0,W,H);
  const gs = 30, off = (idleT*15)%gs;
  ctx.strokeStyle = 'rgba(124,58,237,0.15)'; ctx.lineWidth=1;
  for (let x=-gs+off; x<W+gs; x+=gs) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
  for (let y=-gs+off; y<H+gs; y+=gs) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }
  ctx.font='10px monospace'; ctx.fillStyle='rgba(0,245,255,0.25)';
  for (let i=0;i<4;i++) {
    const x=(i*80+idleT*20)%W;
    '010110AI'.split('').forEach((c,j)=>{
      ctx.fillText(c, x, ((j*22+idleT*25*(i+1))%H));
    });
  }
  ctx.fillStyle='rgba(124,58,237,0.3)'; ctx.font='9px monospace';
  ctx.fillText('AWAITING CAMERA...', 8, H-6);
  requestAnimationFrame(drawIdleCanvas);
}
drawIdleCanvas();

// ── START CAMERA ───────────────────────────────────────────
async function startCamera() {
  try {
    showToast('Requesting camera access...', 'info');
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
      audio: false,
    });
    state.videoStream = stream;
    videoEl.srcObject = stream;
    await videoEl.play();
    state.cameraActive = true;

    $('start-cam-btn').textContent = '⏹ Stop';
    $('start-cam-btn').style.borderColor = 'var(--red)';
    $('footer-detection').textContent = 'Camera ON';
    $('footer-detection').className = 'status-val status-green';
    showToast('📷 Camera started!', 'success');

    // Load BlazeFace only (skip COCO-SSD — saves ~2s load time + memory)
    if (!state.faceModel) {
      showToast('Loading BlazeFace detection model...', 'info');
      $('footer-detection').textContent = 'Loading Model...';
      state.faceModel = await blazeface.load();
      $('footer-detection').textContent = 'AI Model Ready';
      showToast('🧠 Face detection active!', 'success');
    }
    startDetectionLoop();

  } catch (err) {
    showToast('Camera error: ' + err.message, 'warning');
    console.error(err);
  }
}

function stopCamera() {
  if (state.videoStream) {
    state.videoStream.getTracks().forEach(t => t.stop());
    state.videoStream = null;
  }
  state.cameraActive = false;
  if (state.detectionLoop) { cancelAnimationFrame(state.detectionLoop); state.detectionLoop = null; }
  $('start-cam-btn').textContent = '📷 Start';
  $('start-cam-btn').style.borderColor = '';
  $('footer-detection').textContent = 'Camera OFF';
  $('footer-detection').className = 'status-val status-yellow';
  $('camera-status-label').innerHTML = '<span class="blink-dot"></span> CAMERA OFF';
  personCountEl.textContent = '0';
  drawIdleCanvas();
}

$('start-cam-btn').addEventListener('click', () => {
  if (state.cameraActive) stopCamera(); else startCamera();
});

// ── DETECTION LOOP ─────────────────────────────────────────
function startDetectionLoop() {
  let lastFaces = [];  // cache last detection results for non-detection frames

  async function loop() {
    if (!state.cameraActive) return;
    const W = cameraCanvas.width, H = cameraCanvas.height;

    // Draw the live video frame (every frame for smooth video)
    ctx.drawImage(videoEl, 0, 0, W, H);

    // Run AI detection only every 3rd frame (saves ~66% GPU)
    state.detectionFrameCount++;
    const runDetection = (state.detectionFrameCount % 3 === 0);

    let faces = lastFaces;  // reuse cached results on skip frames
    if (runDetection && state.faceModel && videoEl.readyState === 4) {
      const t0 = performance.now();
      
      // BlazeFace only — skip COCO-SSD entirely (BlazeFace is 3x faster)
      const facePreds = await state.faceModel.estimateFaces(videoEl, false);
      
      const ms = (performance.now() - t0).toFixed(0);
      
      faces = facePreds.map(f => {
        const start = f.topLeft;
        const end   = f.bottomRight;

        // Scale from video native resolution → canvas display size
        const scaleX = W / (videoEl.videoWidth  || W);
        const scaleY = H / (videoEl.videoHeight || H);

        const fw = (end[0] - start[0]) * scaleX;
        const fh = (end[1] - start[1]) * scaleY;

        // Add ~15% padding so the box frames the full head, not just the face core
        const padX = fw * 0.15;
        const padY = fh * 0.20;

        return {
          bbox: [
            start[0] * scaleX - padX,
            start[1] * scaleY - padY,
            fw + padX * 2,
            fh + padY * 2,
          ],
          score: f.probability[0],
        };
      });
      lastFaces = faces;  // cache for next 2 frames

      const count = faces.length;
      $('stat-detected').textContent = count;
      $('person-count').textContent = count;
      $('stat-latency').textContent = ms + 'ms';

      if (count > 0) {
        const best = faces.reduce((a,b) => a.score > b.score ? a : b);
        $('stat-confidence').textContent = (best.score * 100).toFixed(0) + '%';
      } else {
        $('stat-confidence').textContent = '—';
      }

      // Update person state based on faces
      handlePersonState(count);
    }

    // Draw FACE overlays (from cache on skip-frames for visual continuity)
    if (state.overlaysEnabled && faces.length > 0) drawDetectionBoxes(faces, W, H);

    // Scan line
    ctx.strokeStyle = 'rgba(0,245,255,0.4)';
    ctx.lineWidth = 1;
    const scanY = (Date.now() / 8) % H;
    ctx.beginPath(); ctx.moveTo(0, scanY); ctx.lineTo(W, scanY); ctx.stroke();

    // Watermark
    ctx.font = '9px monospace';
    ctx.fillStyle = 'rgba(124,58,237,0.5)';
    ctx.fillText('ROBOGREET AI VISION', 8, H - 6);

    state.detectionLoop = requestAnimationFrame(loop);
  }
  loop();
}

function drawDetectionBoxes(persons, W, H) {
  persons.forEach(p => {
    let [bx, by, bw, bh] = p.bbox;
    const conf = (p.score * 100).toFixed(0);

    // Clamp box to canvas bounds so it never goes off-screen
    bx = Math.max(0, bx);
    by = Math.max(0, by);
    bw = Math.min(bw, W - bx);
    bh = Math.min(bh, H - by);

    // Dashed bounding box
    ctx.strokeStyle = '#00f5ff';
    ctx.lineWidth = 2;
    ctx.setLineDash([8, 4]);
    ctx.strokeRect(bx, by, bw, bh);
    ctx.setLineDash([]);

    // Label — auto-width based on measured text
    const label = `FACE ${conf}%`;
    ctx.font = 'bold 12px monospace';
    const labelW = ctx.measureText(label).width + 14;
    const labelH = 22;
    const labelY = by > labelH ? by - labelH : by + bh; // flip below if too close to top
    ctx.fillStyle = 'rgba(0,245,255,0.9)';
    ctx.fillRect(bx, labelY, labelW, labelH);
    ctx.fillStyle = '#020617';
    ctx.fillText(label, bx + 6, labelY + 15);

    // Green corner accents — proportional to box size
    const m = Math.min(20, bw * 0.15, bh * 0.15);
    ctx.strokeStyle = '#a0ff60'; ctx.lineWidth = 3;
    [[bx, by, 1, 1], [bx+bw, by, -1, 1], [bx, by+bh, 1, -1], [bx+bw, by+bh, -1, -1]].forEach(([px, py, sx, sy]) => {
      ctx.beginPath();
      ctx.moveTo(px, py + m * sy); ctx.lineTo(px, py); ctx.lineTo(px + m * sx, py);
      ctx.stroke();
    });
  });
}

// ── Handle person presence ─────────────────────────────────
let personLostFrames = 0;

function handlePersonState(count) {
  personCountEl.textContent = count;

  let stateChanged = false;

  // 1. Core presence tracking (updates regardless of engagement with debounce)
  if (count > 0) {
    personLostFrames = 0;
    if (!state.personDetected) {
      state.personDetected = true;
      state.visitorCount++;
      visitorCountEl.textContent = state.visitorCount;
      $('camera-status-label').innerHTML = '<span class="blink-dot" style="background:#a0ff60"></span> PERSON DETECTED';
      $('stat-emotion').textContent = pick(['😊 Happy','😐 Neutral','😮 Surprised']);
      stateChanged = true;
    }
  } else {
    personLostFrames++;
    if (personLostFrames > 30 && state.personDetected) {
      state.personDetected = false;
      $('stat-confidence').textContent = '—';
      $('stat-emotion').textContent = '—';
      $('camera-status-label').innerHTML = '<span class="blink-dot"></span> SCANNING...';
      stateChanged = true;
      
      // Stop listening if person walks away
      if (state.isListening && !state.isSpeaking) {
        stopListening(true);
      }
    }
  }

  // 2. DON'T INTERRUPT robot state/speech if we are engaged
  const isEngaged = state.mode === 'chat' || state.isSpeaking || state.isListening || state.isThinking;
  if (isEngaged) return; 

  // 3. Handle Greetings/Idle visual state
  if (state.personDetected) {
    if (stateChanged) {
      state.conversationHistory = []; // Clear memory for new visitor
      triggerWave();
      
      // AUTO-START MIC: Immediately start listening when person is detected
      if (!state.isListening) startListening();

      setTimeout(() => {
        const g = pick(R.greetings);
        addBotMessage(g);
        setSpeechBubble(g);
        setRobotState('GREETING — Visitor engaged! 😊', 70, '😊 GREETING', 'HELLO!');
      }, 800);
    }
  } else if (stateChanged) {
    setRobotState('IDLE — Scanning for visitors...', 20, '🔮 IDLE', 'SCAN');
    setSpeechBubble('👀 Scanning for new friends...');
  }
}

// ── Toast ──────────────────────────────────────────────────
function showToast(msg, type = 'info', duration = 3000) {
  const c = $('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${{info:'ℹ️',success:'✅',warning:'⚠️'}[type]||'💬'}</span><span>${msg}</span>`;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity='0'; t.style.transition='opacity 0.3s'; setTimeout(()=>t.remove(),300); }, duration);
}

// ── Robot helpers ──────────────────────────────────────────
function setRobotState(label, progress, mood = '😊 FRIENDLY', chest = 'READY') {
  const robotStateEl = $('robot-state');
  const stateBar     = $('state-progress-bar');
  const robotMood    = $('robot-mood');
  const chestText    = $('chest-text');
  if (robotStateEl) robotStateEl.textContent = label;
  if (stateBar)     stateBar.style.width = progress + '%';
  if (robotMood)    robotMood.textContent = mood;
  if (chestText)    chestText.textContent = chest;
}

function setSpeechBubble(text) {
  const speechBubble = $('speech-bubble-text');
  if (!speechBubble) return;
  speechBubble.style.opacity = '0';
  setTimeout(() => {
    speechBubble.textContent = text;
    speechBubble.style.transition = 'opacity 0.4s';
    speechBubble.style.opacity = '1';
  }, 200);
}

function triggerWave() {
  if (robotAvatar) {
    robotAvatar.classList.remove('waving');
    void robotAvatar.offsetWidth;
    robotAvatar.classList.add('waving');
  }
  setRobotState('WAVING — Hello visitor! 👋', 70, '👋 WAVING', 'WAVE!');
  setSpeechBubble('👋 Hello there! Welcome!');
  if ($('ui-arduino-toggle') && $('ui-arduino-toggle').checked) fetch('/api/arduino/command', {method:'POST', body:JSON.stringify({command:'WAVE'})});
  setTimeout(() => {
    if (robotAvatar) robotAvatar.classList.remove('waving');
    if (state.mode === 'idle') setRobotState('IDLE — Waiting for visitors', 20, '😊 FRIENDLY', 'READY');
  }, 3500);
}

function triggerDance() {
  if (robotAvatar) {
    robotAvatar.classList.remove('dancing','waving');
    void robotAvatar.offsetWidth;
    robotAvatar.classList.add('dancing','waving');
  }
  setRobotState('DANCE MODE 💃 — Groove activated!', 90, '💃 DANCING', 'DANCE!');
  setSpeechBubble('💃 Watch my moves! *beep boop bop*');
  if ($('ui-arduino-toggle') && $('ui-arduino-toggle').checked) fetch('/api/arduino/command', {method:'POST', body:JSON.stringify({command:'DANCE'})});
  setTimeout(() => {
    if (robotAvatar) robotAvatar.classList.remove('dancing','waving');
    setRobotState('IDLE — Waiting for visitors', 20, '😊 FRIENDLY', 'READY');
  }, 5000);
}

// ── TTS (Text-to-Speech) ──────────────────────────────────
let ttsVoice = null;

function loadVoices() {
  const voices = window.speechSynthesis.getVoices();
  // Prefer a natural-sounding English voice
  ttsVoice =
    voices.find(v => v.name.includes('Google UK English Female')) ||
    voices.find(v => v.name.includes('Google UK English Male')) ||
    voices.find(v => v.name.includes('Google US English')) ||
    voices.find(v => v.lang === 'en-GB' && !v.localService) ||
    voices.find(v => v.lang.startsWith('en')) ||
    voices[0] || null;

  const footer = $('footer-tts');
  if (footer) {
    footer.textContent = ttsVoice ? `TTS: ${ttsVoice.name.split(' ').slice(0,3).join(' ')}` : 'TTS Ready';
    footer.className   = 'status-val status-green';
  }
}

if ('speechSynthesis' in window) {
  // Voices load asynchronously in Chrome
  window.speechSynthesis.onvoiceschanged = loadVoices;
  loadVoices(); // also try immediately (works in Firefox)
} else {
  const footer = $('footer-tts');
  if (footer) { footer.textContent = 'TTS Unavailable'; footer.className = 'status-val status-yellow'; }
}

function speakText(text) {
  if (!('speechSynthesis' in window)) return;
  
  // Chrome bug: cancel any stuck utterance first
  window.speechSynthesis.cancel();
  
  const clean = text.replace(/[^\x00-\x7F]/g, '').trim();
  if (!clean) return;
  
  const utt = new SpeechSynthesisUtterance(clean);
  if (ttsVoice) utt.voice = ttsVoice;
  
  utt.rate   = 0.93;
  utt.pitch  = 1.05;
  utt.volume = 1.0;
  utt.lang   = ttsVoice ? ttsVoice.lang : 'en-GB';

  // Prevent echo: Mute processing while speaking
  utt.onstart = () => {
    state.isSpeaking = true;
    state.isCoolingDown = false;
    $('voice-status-text').textContent = '🔊 RoboGreet is speaking...';
    $('stop-btn').style.display = 'flex';
    
    // Stop recognition while speaking to prevent echo
    if (recognition && state.isListening) {
      try { recognition.stop(); } catch(err) {}
    }
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      state.ignoreCurrentRecord = true;
      try { mediaRecorder.stop(); } catch(err) {}
    }
  };
  
  utt.onend = () => {
    state.isSpeaking = false;
    // ── Post-TTS cooldown: ignore mic input for 900ms after speaking stops
    // to prevent the robot from hearing its own voice echo.
    state.isCoolingDown = true;
    setTimeout(() => {
      state.isCoolingDown = false;
      if (!micManuallyStopped) {
        startListening();
      }
    }, 900);
    $('stop-btn').style.display = 'none';
  };

  window.speechSynthesis.speak(utt);
}

// ── Stop Speaking ──────────────────────────────────────────
function stopSpeaking() {
  window.speechSynthesis.cancel();
  state.isSpeaking = false;
  state.isCoolingDown = false;
  $('stop-btn').style.display = 'none';
  if (!micManuallyStopped) {
    startListening();
  } else {
    $('voice-status-text').textContent = 'Click mic to speak';
  }
  setRobotState(state.personDetected ? 'CHATTING 💬' : 'IDLE — Waiting for visitors',
                state.personDetected ? 70 : 20, '😊 FRIENDLY', 'READY');
}

$('stop-btn').addEventListener('click', stopSpeaking);

// ── Chat ───────────────────────────────────────────────────
function formatTime() {
  return new Date().toLocaleTimeString('en-GB', {hour:'2-digit',minute:'2-digit'});
}

function addBotMessage(text, doSpeak = true) {
  typingIndicator.style.display = 'flex';
  chatMessages.scrollTop = chatMessages.scrollHeight;
  setTimeout(() => {
    typingIndicator.style.display = 'none';
    const d = document.createElement('div');
    d.className = 'chat-message bot-message';
    d.innerHTML = `<div class="msg-avatar">🤖</div>
      <div class="msg-content">
        <div class="msg-name">RoboGreet</div>
        <div class="msg-text">${text}</div>
        <div class="msg-time">${formatTime()}</div>
      </div>`;
    chatMessages.appendChild(d);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    if (doSpeak) speakText(text);
  }, 700 + Math.random()*600);
}

function addUserMessage(text) {
  const d = document.createElement('div');
  d.className = 'chat-message user-message';
  d.innerHTML = `<div class="msg-avatar">🧑</div>
    <div class="msg-content">
      <div class="msg-name">Visitor</div>
      <div class="msg-text">${text}</div>
      <div class="msg-time">${formatTime()}</div>
    </div>`;
  chatMessages.appendChild(d);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage(text) {
  if (!text.trim()) return;
  addUserMessage(text);
  chatInput.value = '';
  $('send-btn').disabled = true;
  setRobotState('THINKING — Processing... 🧠', 55, '🧠 THINKING', 'THINK');
  typingIndicator.style.display = 'flex';
  chatMessages.scrollTop = chatMessages.scrollHeight;

  state.isThinking = true;
  try {
    const resp = await getResponse(text);
    state.isThinking = false;
    typingIndicator.style.display = 'none';
    // Use addBotMessage but bypass its internal typing delay since we already waited
    const d = document.createElement('div');
    d.className = 'chat-message bot-message';
    d.innerHTML = `<div class="msg-avatar">🤖</div>
      <div class="msg-content">
        <div class="msg-name">RoboGreet</div>
        <div class="msg-text">${resp}</div>
        <div class="msg-time">${formatTime()}</div>
      </div>`;
    chatMessages.appendChild(d);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    setSpeechBubble(resp);
    speakText(resp);
  } catch(err) {
    typingIndicator.style.display = 'none';
    showToast('Error getting response: ' + err.message, 'warning');
  } finally {
    $('send-btn').disabled = false;
    setRobotState(state.personDetected ? 'CHATTING 💬' : 'IDLE — Waiting for visitors',
                  state.personDetected ? 70 : 20, '💬 CHATTING', 'TALK');
  }
}

$('send-btn').addEventListener('click', () => sendMessage(chatInput.value));
chatInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendMessage(chatInput.value); });
document.querySelectorAll('.qr-btn').forEach(btn =>
  btn.addEventListener('click', () => sendMessage(btn.dataset.msg)));

// ── MICROPHONE — Web Speech API (Always-Alive Indian English Mode) ───────────
let recognition = null;
let micManuallyStopped = false;
let accumulatedFinal = '';
let speechDebounceTimer = null;

async function initSpeech() {
  if (recognition) return true;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    showToast('Speech recognition not supported in this browser. Use Google Chrome.', 'warning');
    return false;
  }
  recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'en-IN'; // Highly tuned for Indian English accents and names

  recognition.onstart = () => {
    state.isListening = true;
    micBtn.classList.add('listening');
    $('voice-wave').classList.add('listening');
    $('footer-stt').textContent = '🎤 Mic Active';
    $('footer-stt').className = 'status-val status-green';
    $('voice-status-text').textContent = 'Mic ON — speak anytime!';
    setRobotState('LISTENING — Speak anytime! 🎤', 50, '👂 LISTENING', 'HEAR');
  };

  recognition.onresult = (e) => {
    // Discard speech if robot is actively speaking or cooling down
    if (state.isSpeaking || state.isCoolingDown) return;

    let interim = '';
    let final = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) {
        final += e.results[i][0].transcript;
      } else {
        interim += e.results[i][0].transcript;
      }
    }

    // Live-write the interim text immediately in the chat input area
    if (interim) {
      chatInput.value = accumulatedFinal + interim;
      $('voice-status-text').textContent = `🎙️ Live: ${interim.slice(0, 35)}...`;
    }

    if (final) {
      accumulatedFinal += (accumulatedFinal ? ' ' : '') + final.trim();
      chatInput.value = accumulatedFinal;
      $('voice-status-text').textContent = '⏸️ Processing speech...';
    }

    // Debounce sending the text: wait for 1 second of pause before auto-submitting
    if (speechDebounceTimer) clearTimeout(speechDebounceTimer);
    speechDebounceTimer = setTimeout(() => {
      if (accumulatedFinal.trim()) {
        const textToSend = accumulatedFinal.trim();
        accumulatedFinal = '';
        sendMessage(textToSend);
      }
    }, 1000);
  };

  recognition.onerror = (e) => {
    if (e.error === 'no-speech') return;
    console.warn('Speech recognition error:', e.error);
    if (e.error === 'not-allowed') {
      showToast('Microphone permission denied.', 'warning');
      stopListening(true);
    } else if (e.error === 'network') {
      console.warn('Speech recognition network error. Switching to offline Whisper mode.');
      showToast('🎙️ Offline: Switching to local speech recognition...', 'info', 3000);
      try { recognition.stop(); } catch(err) {}
      setTimeout(async () => {
        if (!micManuallyStopped) {
          if (await initWhisperMic()) {
            startWhisperListening();
          }
        }
      }, 500);
    }
  };

  recognition.onend = () => {
    state.isListening = false;
    // Keep it always alive: automatically restart if not manually stopped and not speaking
    if (!micManuallyStopped && !state.isSpeaking && !state.isCoolingDown) {
      if (navigator.onLine) {
        setTimeout(() => {
          if (!micManuallyStopped && !state.isSpeaking && !state.isCoolingDown) {
            try { recognition.start(); } catch(err) {}
          }
        }, 300);
      }
    } else {
      micBtn.classList.remove('listening');
      $('voice-wave').classList.remove('listening');
      if (micManuallyStopped) {
        $('voice-status-text').textContent = 'Click mic to speak';
        $('footer-stt').textContent = 'Mic Off';
        $('footer-stt').className = 'status-val status-yellow';
      }
    }
  };

  return true;
}

// ── LOCAL OFFLINE WHISPER MIC VAD MODE ──────────────────────────────────────────
let micStream = null;
let mediaRecorder = null;
let audioChunks = [];
let audioCtxForVAD = null;
let vadAnalyser = null;
let vadRafId = null;
let isRecording = false;
let _restartAttempts = 0;

const SILENCE_THRESHOLD = 0.018;  // RMS below this = silence
const SILENCE_DURATION  = 900;    // ms of continuous silence before stop
const MIN_RECORD_MS     = 500;    // min recording before VAD can fire
const MAX_RECORD_MS     = 12000;  // safety cap per recording
const MIN_BLOB_BYTES    = 3000;   // ignore blobs that are just noise

async function initWhisperMic() {
  if (micStream) return true;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 }
    });
    audioCtxForVAD = new (window.AudioContext || window.webkitAudioContext)();
    const src = audioCtxForVAD.createMediaStreamSource(micStream);
    vadAnalyser = audioCtxForVAD.createAnalyser();
    vadAnalyser.fftSize = 512;
    src.connect(vadAnalyser);
    return true;
  } catch (err) {
    showToast('Microphone access denied: ' + err.message, 'warning');
    return false;
  }
}

function startWhisperListening() {
  if (!micStream || isRecording || micManuallyStopped) return;
  if (state.isSpeaking || state.isCoolingDown) {
    setTimeout(startWhisperListening, 300);
    return;
  }

  audioChunks = [];
  const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus' : 'audio/webm';
  mediaRecorder = new MediaRecorder(micStream, { mimeType: mime });

  mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };

  mediaRecorder.onstop = async () => {
    isRecording = false;
    cancelAnimationFrame(vadRafId);
    if (micManuallyStopped || !state.isListening) return;

    if (state.ignoreCurrentRecord) {
      state.ignoreCurrentRecord = false;
      restartListening();
      return;
    }

    const blob = new Blob(audioChunks, { type: mime });
    if (blob.size < MIN_BLOB_BYTES) { restartListening(); return; }
    await transcribeWithWhisper(blob);
  };

  mediaRecorder.start(100);
  isRecording = true;

  const buf = new Float32Array(vadAnalyser.fftSize);
  const start = Date.now();
  let lastVoice = Date.now();
  let voiceSeen = false;
  let statusThrottle = 0;

  function vad() {
    if (!isRecording) return;
    vadAnalyser.getFloatTimeDomainData(buf);
    const rms = Math.sqrt(buf.reduce((s, v) => s + v * v, 0) / buf.length);
    const now = Date.now();
    const elapsed = now - start;

    if (rms > SILENCE_THRESHOLD) {
      lastVoice = now;
      voiceSeen = true;
      if (now - statusThrottle > 250) {
        $('voice-status-text').textContent = '🎙️ Speaking (local)...';
        statusThrottle = now;
      }
    } else {
      if (now - statusThrottle > 250) {
        $('voice-status-text').textContent = voiceSeen ? '⏳ Waiting for pause...' : '🎤 Listening (offline)...';
        statusThrottle = now;
      }
    }

    const silentFor = now - lastVoice;
    if ((voiceSeen && silentFor > SILENCE_DURATION && elapsed > MIN_RECORD_MS)
        || elapsed > MAX_RECORD_MS) {
      if (mediaRecorder.state === 'recording') mediaRecorder.stop();
      return;
    }
    vadRafId = requestAnimationFrame(vad);
  }
  vadRafId = requestAnimationFrame(vad);
}

async function blobToWav(blob) {
  const arrayBuffer = await blob.arrayBuffer();
  const audioContext = audioCtxForVAD || new AudioContext();
  const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
  
  const sampleRate = 16000;
  const numberOfChannels = 1;
  
  const offlineCtx = new OfflineAudioContext(
    numberOfChannels,
    Math.round(audioBuffer.duration * sampleRate),
    sampleRate
  );
  
  const source = offlineCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(offlineCtx.destination);
  source.start();
  
  const renderedBuffer = await offlineCtx.startRendering();
  return audioBufferToWav(renderedBuffer);
}

function audioBufferToWav(buffer) {
  const numOfChan = buffer.numberOfChannels;
  const sampleRate = buffer.sampleRate;
  const format = 1;
  const bitDepth = 16;
  
  let result;
  if (numOfChan === 1) {
    result = buffer.getChannelData(0);
  } else {
    const c0 = buffer.getChannelData(0);
    const c1 = buffer.getChannelData(1);
    result = new Float32Array(c0.length);
    for (let i = 0; i < c0.length; i++) {
      result[i] = (c0[i] + c1[i]) / 2;
    }
  }
  
  return writeWavFile(result, sampleRate, bitDepth);
}

function writeWavFile(samples, sampleRate, bitDepth) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, bitDepth, true);
  writeString(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);
  
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  
  return new Blob([buffer], { type: 'audio/wav' });
}

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

async function transcribeWithWhisper(blob) {
  $('voice-status-text').textContent = '⚡ Transcribing...';
  try {
    const wavBlob = await blobToWav(blob);
    const res = await fetch('/api/whisper/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'audio/wav' },
      body: wavBlob
    });
    
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || `Status ${res.status}`);
    }
    
    const data = await res.json();
    const text = (data.text || '').trim();
    
    if (text) {
      chatInput.value = text;
      $('voice-status-text').textContent = `✅ Heard: "${text.slice(0, 40)}${text.length > 40 ? '…' : ''}"`;
      _restartAttempts = 0;
      setTimeout(() => {
        sendMessage(text);
      }, 400);
    } else {
      $('voice-status-text').textContent = '🔇 No speech detected — try again';
      setTimeout(() => restartListening(), 600);
    }
  } catch (err) {
    console.warn('Whisper error:', err);
    showToast('🎤 Mic issue: ' + err.message, 'warning', 3000);
    restartListening();
  }
}

function restartListening() {
  if (!state.isListening || micManuallyStopped) return;
  
  _restartAttempts++;
  if (_restartAttempts > 20) {
    console.warn('[Whisper] Too many restarts — stopping mic to prevent loop');
    stopListening(true);
    showToast('🎤 Mic stopped. Click to restart.', 'warning', 4000);
    _restartAttempts = 0;
    return;
  }
  
  const isWhisperActive = !navigator.onLine || !window.webkitSpeechRecognition;
  
  if (isWhisperActive) {
    $('voice-status-text').textContent = '🎤 Listening (offline)...';
    const delay = (state.isSpeaking || state.isCoolingDown) ? 600 : 300;
    setTimeout(() => {
      if (!state.isListening || micManuallyStopped) return;
      if (!state.isSpeaking && !state.isCoolingDown) startWhisperListening();
      else restartListening();
    }, delay);
  }
}

// ── Public start/stop ─────────────────────────────────────────────────────────
async function startListening() {
  micManuallyStopped = false;
  const useOfflineWhisper = !navigator.onLine || !window.webkitSpeechRecognition;
  
  if (useOfflineWhisper) {
    if (!(await initWhisperMic())) return;
    state.isListening = true;
    micBtn.classList.add('listening');
    $('voice-wave').classList.add('listening');
    $('footer-stt').textContent = '🎤 Mic Active (offline)';
    $('footer-stt').className = 'status-val status-green';
    $('voice-status-text').textContent = 'Mic ON — speak anytime!';
    setRobotState('LISTENING — Speak anytime! 🎤', 50, '👂 LISTENING', 'HEAR');
    startWhisperListening();
  } else {
    if (!(await initSpeech())) return;
    accumulatedFinal = '';
    chatInput.value = '';
    try {
      recognition.start();
    } catch(err) {
      // Already started, ignore error
    }
  }
}

function stopListening(full = false) {
  if (full) {
    micManuallyStopped = true;
  }
  state.isListening = false;
  if (recognition) {
    try { recognition.stop(); } catch(err) {}
  }
  
  cancelAnimationFrame(vadRafId);
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    try { mediaRecorder.stop(); } catch(err) {}
  }
  isRecording = false;
  
  micBtn.classList.remove('listening');
  $('voice-wave').classList.remove('listening');
  $('voice-status-text').textContent = 'Click mic to speak';
  $('footer-stt').textContent = 'Mic Off';
  $('footer-stt').className = 'status-val status-yellow';
  setRobotState('IDLE — Waiting for visitors', 20, '😊 FRIENDLY', 'READY');
}

micBtn.addEventListener('click', async () => {
  if (state.isListening) stopListening(true);
  else await startListening();
});

// ── Online/Offline dynamic listeners ──────────────────────────────────────────
window.addEventListener('online', () => {
  showToast('🟢 Back online. Using high-speed cloud speech recognition.', 'success', 3000);
  if (state.isListening && !micManuallyStopped) {
    stopListening(false);
    setTimeout(() => startListening(), 500);
  }
});

window.addEventListener('offline', () => {
  showToast('🔴 Offline. Switching to local speech recognition...', 'info', 3000);
  if (state.isListening && !micManuallyStopped) {
    stopListening(false);
    setTimeout(() => startListening(), 500);
  }
});


// ── Quick actions ──────────────────────────────────────────
$('wave-btn').addEventListener('click', triggerWave);
$('joke-btn').addEventListener('click', () => {
  const j = pick(R.jokes);
  addBotMessage(j); setSpeechBubble(j);
  showToast('Joke delivered! 😂', 'success');
});
$('compliment-btn').addEventListener('click', () => {
  const c = pick(R.compliments);
  addBotMessage(c); setSpeechBubble(c);
  showToast('Compliment sent! ⭐', 'success');
});
$('dance-btn').addEventListener('click', () => {
  triggerDance(); addBotMessage(pick(R.dance));
});

// ── Mode selector ──────────────────────────────────────────
document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.mode = btn.dataset.mode;
    const actions = {
      idle:  () => { setRobotState('IDLE — Scanning...', 20, '🔮 IDLE', 'SCAN'); setSpeechBubble('👀 Waiting for someone interesting...'); },
      greet: () => { triggerWave(); },
      chat:  () => { setRobotState('CHAT MODE 💬', 75, '💬 CHATTING', 'TALK'); setSpeechBubble('💬 Ask me anything!'); },
      dance: () => triggerDance(),
    };
    if (actions[state.mode]) actions[state.mode]();
  });
});

// ── Camera overlay toggle ──────────────────────────────────
$('toggle-overlay-btn').addEventListener('click', function() {
  state.overlaysEnabled = !state.overlaysEnabled;
  this.classList.toggle('active', state.overlaysEnabled);
  showToast(`Overlays ${state.overlaysEnabled ? 'ON' : 'OFF'}`, 'info');
});

$('toggle-tracking-btn').addEventListener('click', function() {
  state.trackingEnabled = !state.trackingEnabled;
  this.classList.toggle('active', state.trackingEnabled);
  showToast(`Face tracking ${state.trackingEnabled ? 'ON' : 'OFF'}`, 'info');
});

// ── Pupil follows mouse ────────────────────────────────────
document.addEventListener('mousemove', e => {
  const svg = $('robot-svg');
  if (!svg) return;
  const r = svg.getBoundingClientRect();
  const dx = ((e.clientX - r.left - r.width/2) / r.width) * 5;
  const dy = ((e.clientY - r.top  - r.height*.3) / r.height) * 3;
  [['left-pupil',74,63],['right-pupil',126,63]].forEach(([id,bx,by]) => {
    const el = $(id);
    if (el) { el.setAttribute('cx', bx+dx); el.setAttribute('cy', by+dy); }
  });
});

// ── Init ───────────────────────────────────────────────────
setRobotState('IDLE — Waiting for visitors', 20, '😊 FRIENDLY', 'READY');
setTimeout(() => showToast('🤖 RoboGreet AI Online! Click 📷 Start to enable camera.', 'success', 4000), 500);
setTimeout(() => showToast('🎤 Click the mic button to speak', 'info', 3500), 2000);

// Fetch models and populate dropdown on page load
fetchOllamaModels().then(models => {
  populateModelDropdown(models);
  if (models.length > 0) {
    showToast(`🧠 Ollama found! ${models.length} model(s) available. Select one and click Connect.`, 'success', 5000);
  } else {
    showToast('⚠️ Ollama not detected — using fallback responses. Run: ollama serve', 'warning', 6000);
  }
  updateOllamaStatus();
});

// Connect button: connect/disconnect to/from selected model
$('start-llm-btn').addEventListener('click', async () => {
  if (ollamaOnline && ollamaModel) {
    disconnectModel();
    return;
  }

  const sel = $('llm-model-select');
  const modelName = sel.value;

  if (!modelName) {
    // No model selected — try refreshing the list
    showToast('Refreshing model list…', 'info');
    const models = await fetchOllamaModels();
    populateModelDropdown(models);
    if (models.length === 0) {
      showToast('No Ollama models found. Is Ollama running?', 'warning');
    } else {
      showToast(`Found ${models.length} model(s) — pick one from the dropdown!`, 'success');
    }
    return;
  }

  await connectToModel(modelName);
});

// System Master Switch (Toggle)
$('master-switch-pill').addEventListener('click', async () => {
  const label = $('master-switch-label');
  const pill = $('master-switch-pill');
  const isCurrentlyActive = label.textContent.includes('Active');

  if (!isCurrentlyActive) {
    // START SYSTEM
    label.textContent = '🚀 Starting...';
    pill.style.borderColor = 'var(--cyan)';
    showToast('Initializing System Components...', 'info');

    try {
      const res = await fetch('/api/system/start', { method: 'POST' });
      if (res.ok) {
        label.textContent = '⚡ System Active';
        pill.style.borderColor = 'var(--green)';
        showToast('Ollama and Robot Services Launched!', 'success');
        
        // Refresh model list so user can pick — no auto-connect
        setTimeout(async () => {
          const models = await fetchOllamaModels();
          populateModelDropdown(models);
          if (models.length > 0) {
            showToast(`${models.length} model(s) found — please select one and click Connect.`, 'info', 5000);
          }
          // AUTO-START CAMERA
          if (!state.cameraActive) startCamera();
        }, 5000);
      } else {
        const errorText = await res.text();
        label.textContent = '❌ Error';
        pill.style.borderColor = 'var(--red)';
        showToast('Server error: ' + errorText, 'warning');
      }
    } catch (err) {
      console.error('System start failed:', err);
      label.textContent = '❌ Offline';
      pill.style.borderColor = 'var(--red)';
      showToast('Could not reach Control Server', 'warning');
    }
  } else {
    // STOP SYSTEM
    label.textContent = '🛑 Stopping...';
    pill.style.borderColor = 'var(--yellow)';
    showToast('Shutting down background services...', 'info');

    try {
      const res = await fetch('/api/system/stop', { method: 'POST' });
      if (res.ok) {
        label.textContent = '🔌 System Offline';
        pill.style.borderColor = 'var(--yellow)';
        ollamaOnline = false;
        updateOllamaStatus();
        showToast('Ollama and Robot Backend stopped.', 'success');
      }
    } catch (err) {
      console.error('System stop failed:', err);
      showToast('Stop command failed: ' + err.message, 'warning');
      label.textContent = '⚡ System Active'; // revert
    }
  }
});

// Check system status on load
async function checkSystemStatus() {
  try {
    // 1. Fetch Live Info (Internet Awareness)
    fetch('/api/live-info').then(r => r.json()).then(data => {
      state.liveInfo = data;
      console.log('Live Info loaded:', data);
    }).catch(e => console.warn('Failed to fetch live info:', e));

    const res = await fetch('/api/system/status');
    if (res.ok) {
      const data = await res.json();
      const label = $('master-switch-label');
      const pill = $('master-switch-pill');
      
      if (data.status === 'online') {
        label.textContent = '⚡ System Active';
        pill.style.borderColor = 'var(--green)';
        
        // Refresh model list only — user must select and connect manually
        const models = await fetchOllamaModels();
        populateModelDropdown(models);
        if (models.length > 0) {
          showToast(`${models.length} model(s) available — select one and click Connect.`, 'info', 5000);
        }
        
        // AUTO-START CAMERA if system is already online
        if (!state.cameraActive) startCamera();
      }
    }
  } catch (err) {
    console.warn('Initial status check failed:', err);
  }
}

checkSystemStatus();

// ── Arduino Toggle UI Logic ─────────────────────────────────
const uiArduinoToggle = $('ui-arduino-toggle');
const uiArduinoPort = $('ui-arduino-port');
const footerServo = $('footer-servo');

/** Fetch real COM ports from the server and rebuild the dropdown */
async function loadComPorts() {
  if (!uiArduinoPort) return;
  try {
    const res = await fetch('/api/arduino/list-ports');
    if (!res.ok) return;
    const ports = await res.json();   // [{port: "COM4", description: "..."}, ...]
    if (!ports || ports.length === 0) return;

    const current = uiArduinoPort.value; // preserve selection
    uiArduinoPort.innerHTML = '';        // clear static options

    let bestPort = null;
    ports.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.port;
      const isReal = p.description && p.description !== '—';
      opt.textContent = isReal ? `★ ${p.port} (${p.description})` : p.port;
      if (isReal && !bestPort) bestPort = p.port; // first real/connected port
      uiArduinoPort.appendChild(opt);
    });

    // Prefer: previously-selected → first connected device → COM4 default
    const preferred = current && [...uiArduinoPort.options].some(o => o.value === current)
      ? current : (bestPort || 'COM4');
    uiArduinoPort.value = preferred;

    if (bestPort) {
      showToast(`Arduino detected on ${bestPort} — click connect!`, 'success');
    }
  } catch (e) {
    console.warn('[Arduino] Could not fetch COM ports:', e);
  }
}

async function updateArduinoConnection() {
  if (!uiArduinoToggle || !uiArduinoPort) return;
  const isEnabled = uiArduinoToggle.checked;
  const port = uiArduinoPort.value;
  
  if (isEnabled) {
    footerServo.textContent = 'Connecting...';
    footerServo.className = 'status-val status-yellow';
    try {
      const res = await fetch('/api/arduino/connect', { method: 'POST', body: JSON.stringify({port}) });
      if (res.ok) {
        footerServo.textContent = 'Arduino Connected (' + port + ')';
        footerServo.className = 'status-val status-green';
        showToast('Hardware connected to ' + port, 'success');
      } else {
        throw new Error("Failed");
      }
    } catch (e) {
      footerServo.textContent = 'Connection Failed';
      footerServo.className = 'status-val status-red'; // Make sure this CSS var exists or it defaults
      showToast('Could not connect to Arduino on ' + port, 'warning');
      uiArduinoToggle.checked = false;
    }
  } else {
    fetch('/api/arduino/disconnect', { method: 'POST' });
    footerServo.textContent = 'Hardware Disabled';
    footerServo.className = 'status-val status-yellow';
    showToast('Hardware connection disabled', 'info');
  }
}

if (uiArduinoToggle && uiArduinoPort && footerServo) {
  // Update on toggle
  uiArduinoToggle.addEventListener('change', updateArduinoConnection);

  // Update on port change
  uiArduinoPort.addEventListener('change', () => {
    if (uiArduinoToggle.checked) updateArduinoConnection();
  });

  // Add a tiny Refresh button next to the dropdown to re-scan ports
  const refreshBtn = document.createElement('button');
  refreshBtn.textContent = '\u21bb';
  refreshBtn.title = 'Refresh COM ports';
  refreshBtn.style.cssText = 'background:none;border:none;color:var(--cyan);cursor:pointer;font-size:0.85rem;padding:0 2px;line-height:1;';
  refreshBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    refreshBtn.textContent = '\u23f3';
    await loadComPorts();
    refreshBtn.textContent = '\u21bb';
  });
  uiArduinoPort.parentNode.insertBefore(refreshBtn, uiArduinoPort.nextSibling);

  // Load available ports first, then attempt connection
  loadComPorts().then(() => {
    if (uiArduinoToggle.checked) {
      updateArduinoConnection();
    } else {
      footerServo.textContent = 'Hardware Disabled';
      footerServo.className = 'status-val status-yellow';
    }
  });
}


// ── Auto-Start Microphone on page load / interaction ─────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  const autoStartMic = async () => {
    window.removeEventListener('click', autoStartMic);
    window.removeEventListener('keydown', autoStartMic);
    if (!state.isListening && !micManuallyStopped) {
      console.log('[Mic] Auto-starting microphone on user interaction...');
      await startListening();
    }
  };

  // Try to start immediately (works if permission is already granted and no policy block)
  setTimeout(async () => {
    if (!state.isListening && !micManuallyStopped) {
      console.log('[Mic] Attempting immediate microphone auto-start...');
      await startListening();
    }
  }, 1000);

  // Fallback to starting on first interaction if blocked by autoplay policy
  window.addEventListener('click', autoStartMic);
  window.addEventListener('keydown', autoStartMic);
});
