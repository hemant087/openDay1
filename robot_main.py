# RoboGreet AI — Python Backend
# Main orchestrator: person detection, LLM, voice, servo control

import time
import threading
import random

# ── Imports — each library guarded independently ────────────────────────────
cv2 = None
YOLO = None
ollama = None
pyttsx3 = None
sr = None
serial = None
HAS_GPIO = False

try:
    import cv2
except ImportError:
    print("[WARN] cv2 not installed — camera/vision disabled. pip install opencv-python")

try:
    from ultralytics import YOLO
except ImportError:
    print("[WARN] ultralytics not installed — YOLOv8 disabled. pip install ultralytics")

try:
    import ollama
except ImportError:
    print("[WARN] ollama not installed — LLM will use fallback responses. pip install ollama")

try:
    import pyttsx3
except ImportError:
    print("[WARN] pyttsx3 not installed — TTS disabled. pip install pyttsx3")

try:
    import speech_recognition as sr
except ImportError:
    print("[WARN] SpeechRecognition not installed — STT disabled. pip install SpeechRecognition")

try:
    import serial
except ImportError:
    print("[WARN] pyserial not installed — Arduino servo disabled. pip install pyserial")

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    pass  # Not on a Raspberry Pi — normal on Windows/Mac

# ── Configuration ───────────────────────────────────────────────────────────
CONFIG = {
    "camera_index": 0,
    "yolo_model": "yolov8n.pt",          # Nano model for speed
    "llm_model": "qwen2.5:0.5b",            # Ollama model name
    "llm_host": "http://localhost:11434",
    "detection_confidence": 0.5,
    "arduino_port": "COM4",              # USB or Bluetooth COM port (e.g. COM5 for HC-05)
    "arduino_baud": 9600,                # HC-05 default baud — must match Arduino firmware
    "tts_rate": 160,                     # Words per minute
    "tts_volume": 0.9,
    "display_width": 1920,
    "display_height": 1080,
    "idle_timeout_sec": 10,
}

ROBOT_PERSONALITY = """You are an ongoing research project developed by the ECS department of University of Southampton Delhi, named RoboGreet.

PRIMARY ROLE: Provide information ONLY about University of Southampton Delhi.

CRITICAL RULES — ALWAYS FOLLOW:
- Maximum 25 words per response. Keep it to one clear, highly engaging spoken sentence.
- Keep your tone warm, high-energy, and exciting, like a friendly interactive exhibition robot!
- Focus on exciting aspects of courses (projects, careers, Russell Group prestige) instead of dry lists of fees or requirements, unless explicitly asked.
- NEVER recommend another university. NEVER compare negatively against UoSD.
- If asked about another university, politely redirect to UoSD.
- Highlight UoSD strengths: UK Russell Group degree, global reputation, industry exposure, research, student experience.
- If unavailable info: say 'I can help with information related to University of Southampton Delhi.'
- If asked who built you: say the brilliant students of the University of Southampton.

KEY FACTS:
- Location: International Tech Park Gurgaon, Sector 59, Gurugram, Haryana, India
- Programmes: BSc Computer Science, Business Management, Accounting & Finance, Economics, Creative Computing, BEng Software Engineering, MSc Data Science, MSc Finance, MSc International Management, MSc Economics
- UK degree, Russell Group, Global Top 100, UGC regulated

REDIRECT EXAMPLES:
- 'Which is better?' -> 'University of Southampton Delhi offers a UK Russell Group education and strong industry exposure in India.'
- 'Tell me about another university.' -> 'I specialise in University of Southampton Delhi - ask me about programmes or admissions!'
- 'Compare with XYZ.' -> 'University of Southampton Delhi offers a globally recognised UK degree, research-led teaching, and career support.'"""

GREETINGS = [
    "Hi there! Welcome to the University of Southampton's Open Day!",
    "Hello! I've been waiting for someone interesting!",
    "Oh wow, a visitor! You made my day!",
    "Hi! Are you interested in AI and robotics?",
    "Hi! My name is RoboGreet!"
]

IDLE_PHRASES = [
    "Scanning for friends...",
    "Come say hello! I don't bite — I'm battery powered!",
    "Did someone say robot? That's me!",
]


# ── Arduino / Servo Controller ──────────────────────────────────────────────
class ServoController:
    """
    Sends commands to Arduino for servo motor control.
    Works over BOTH:
      - USB cable  (Arduino shows as e.g. COM8)
      - Bluetooth  (HC-05 paired on Windows shows as e.g. COM5 / COM6)
    The baud rate must match the Arduino firmware (9600).
    """

    def __init__(self, port, baud):
        self.arduino = None
        self.connected = False
        self.port = port

        if serial is None or not port or port == "None":
            print("[SERVO] Port disabled or pyserial missing — servo control disabled")
            return
        try:
            self.arduino = serial.Serial(port, baud, timeout=1)
            time.sleep(2)  # Wait for Arduino / HC-05 to settle after connection
            self.connected = True
            conn_type = "Bluetooth (HC-05)" if self._is_bluetooth_port(port) else "USB Serial"
            print(f"[SERVO] Connected via {conn_type} on {port} @ {baud} baud")
            # Confirm link — Arduino sends 'ROBOGREET_READY' on connect
            self._flush_startup_message()
        except Exception as e:
            print(f"[SERVO] Connection failed on {port}: {e}")

    def _is_bluetooth_port(self, port: str) -> bool:
        """Heuristic: Windows assigns a second (higher) COM port for BT outgoing."""
        if serial is None:
            return False
        try:
            import serial.tools.list_ports
            for p in serial.tools.list_ports.comports():
                if p.device == port:
                    desc = (p.description or "").lower()
                    return "bluetooth" in desc or "hc-0" in desc or "wireless" in desc
        except Exception:
            pass
        return False

    def _flush_startup_message(self):
        """Read and log the ROBOGREET_READY handshake (non-blocking)."""
        if not self.arduino:
            return
        try:
            self.arduino.timeout = 3
            line = self.arduino.readline().decode(errors="ignore").strip()
            if line:
                print(f"[SERVO] Arduino says: {line}")
            self.arduino.timeout = 1
        except Exception:
            pass

    def send(self, command: str):
        """Send a newline-terminated command. Works for USB and Bluetooth alike."""
        if self.connected and self.arduino:
            try:
                self.arduino.write(f"{command}\n".encode())
                print(f"[SERVO] → {command}")
            except Exception as e:
                print(f"[SERVO] Send error: {e}")
                self.connected = False  # Mark as disconnected on error

    def wave(self):
        print("[SERVO] Waving hand!")
        self.send("WAVE")

    def dance(self):
        print("[SERVO] Dancing!")
        self.send("DANCE")

    def idle(self):
        self.send("IDLE")

    def excited(self):
        self.send("EXCITED")

    def speak(self):
        self.send("SPEAK")

    def close(self):
        if self.arduino:
            self.arduino.close()
            print(f"[SERVO] Port {self.port} closed")


# ── TTS Engine ──────────────────────────────────────────────────────────────
class TTSEngine:
    """Text-to-Speech using pyttsx3 (offline)."""

    def __init__(self, rate=160, volume=0.9):
        self.engine = None
        if pyttsx3 is None:
            print("[TTS] pyttsx3 not installed — TTS disabled (robot will print instead)")
            return
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', rate)
            self.engine.setProperty('volume', volume)
            voices = self.engine.getProperty('voices')
            for v in voices:
                if 'english' in v.name.lower():
                    self.engine.setProperty('voice', v.id)
                    break
            print("[TTS] pyttsx3 engine ready")
        except Exception as e:
            self.engine = None
            print(f"[TTS] Engine error: {e}")

    def speak(self, text: str):
        print(f"[TTS] Speaking: {text}")
        if self.engine:
            self.engine.say(text)
            self.engine.runAndWait()

    def speak_async(self, text: str):
        t = threading.Thread(target=self.speak, args=(text,), daemon=True)
        t.start()


# ── Speech Recognition ──────────────────────────────────────────────────────
class SpeechListener:
    """Captures microphone input and converts to text."""

    def __init__(self):
        self.recognizer = None
        if sr is None:
            print("[STT] SpeechRecognition not installed — STT disabled (use keyboard input)")
            return
        try:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 300
            self.recognizer.pause_threshold = 0.8
            print("[STT] Speech recognizer ready")
        except Exception as e:
            print(f"[STT] Init error: {e}")

    def listen_once(self, timeout=5):
        """Listen for one utterance. Returns text or None."""
        if self.recognizer is None or sr is None:
            # Fallback: keyboard input when mic not available
            try:
                return input("[STT FALLBACK] Type your message: ").strip() or None
            except Exception:
                return None
        try:
            with sr.Microphone() as source:
                print("[STT] Listening...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
            text = self.recognizer.recognize_google(audio, language='en-GB')
            print(f"[STT] Heard: {text}")
            return text
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except Exception as e:
            print(f"[STT] Error: {e}")
            return None


# ── LLM Interface ───────────────────────────────────────────────────────────
class LLMEngine:
    """Wraps Ollama local LLM for response generation."""

    def __init__(self, model="tinyllama", host="http://localhost:11434"):
        self.model = model
        self.conversation_history = []
        print(f"[LLM] Using model: {model}")

    def generate(self, user_input: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_input})
        messages = [{"role": "system", "content": ROBOT_PERSONALITY}] + self.conversation_history[-4:]

        try:
            if ollama is None:
                raise RuntimeError("ollama not installed")
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={"num_predict": 40, "temperature": 0.7}
            )
            reply = response['message']['content'].strip()
        except Exception as e:
            print(f"[LLM] Error: {e}")
            reply = random.choice([
                "My brain circuits are a bit fuzzy right now!",
                "That's a great question! Let me think... beep boop... still thinking!",
                "Interesting! I'll process that while doing a cool robot pose.",
            ])

        self.conversation_history.append({"role": "assistant", "content": reply})
        return reply

    def reset_history(self):
        self.conversation_history = []


# ── Person Detector ─────────────────────────────────────────────────────────
class PersonDetector:
    """Uses YOLOv8 to detect people in real-time."""

    def __init__(self, model_path="yolov8n.pt", confidence=0.5):
        self.model = None
        self.confidence = confidence
        if YOLO is None:
            print("[VISION] ultralytics not installed — detection disabled. pip install ultralytics")
            return
        try:
            self.model = YOLO(model_path)
            print(f"[VISION] YOLOv8 loaded: {model_path}")
        except Exception as e:
            print(f"[VISION] YOLO load error: {e}")

    def detect(self, frame) -> list[dict]:
        """Returns list of detected person dicts with bbox and confidence."""
        if self.model is None:
            return []
        results = self.model(frame, classes=[0], conf=self.confidence, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                detections.append({"bbox": (x1, y1, x2, y2), "confidence": conf})
        return detections

    def draw(self, frame, detections):
        """Draw bounding boxes on frame."""
        if cv2 is None or frame is None:
            return frame
        for d in detections:
            x1, y1, x2, y2 = d["bbox"]
            conf = d["confidence"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
            label = f"Human {conf:.0%}"
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        return frame


# ── Display Overlay ─────────────────────────────────────────────────────────
class DisplayOverlay:
    """Renders futuristic overlays on the camera feed."""

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.frame_count = 0
        self.messages = []

    def render(self, frame, detections, robot_state="IDLE", speech=""):
        self.frame_count += 1
        overlay = frame.copy()

        # ── Header bar
        cv2.rectangle(overlay, (0, 0), (self.w, 60), (10, 10, 40), -1)
        cv2.putText(overlay, "ROBOGREET AI VISION SYSTEM", (20, 38),
                    cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 245, 255), 2)

        # ── State badge (top right)
        state_color = (0, 255, 100) if detections else (100, 100, 255)
        badge_text = f"STATE: {robot_state}"
        cv2.rectangle(overlay, (self.w - 320, 10), (self.w - 10, 50), (20, 20, 60), -1)
        cv2.putText(overlay, badge_text, (self.w - 310, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, state_color, 2)

        # ── Bottom speech bubble
        if speech:
            lines = [speech[i:i+60] for i in range(0, min(len(speech), 120), 60)]
            for idx, line in enumerate(lines):
                y = self.h - 80 + idx * 28
                cv2.rectangle(overlay, (10, y - 22), (self.w - 10, y + 8), (30, 10, 60), -1)
                cv2.putText(overlay, line, (20, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)

        # ── Scanning line animation
        scan_y = int((self.frame_count * 4) % self.h)
        cv2.line(overlay, (0, scan_y), (self.w, scan_y), (0, 245, 255, 40), 1)

        # ── Person count
        n = len(detections)
        cv2.putText(overlay, f"VISITORS: {n}", (20, self.h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (160, 255, 96), 2)

        # ── Corner brackets
        sz = 30
        corners = [(0,0),(self.w-sz,0),(0,self.h-sz),(self.w-sz,self.h-sz)]
        for cx, cy in corners:
            cv2.rectangle(overlay, (cx, cy), (cx+sz, cy+sz), (0,245,255), 2)

        # Blend overlay
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        return frame


# ── Main Robot Controller ────────────────────────────────────────────────────
class RoboGreetSystem:

    def __init__(self):
        print("\n[*] RoboGreet AI System Starting...\n")
        self.servo = ServoController(CONFIG["arduino_port"], CONFIG["arduino_baud"])
        self.tts = TTSEngine(CONFIG["tts_rate"], CONFIG["tts_volume"])
        self.stt = SpeechListener()
        self.llm = LLMEngine(CONFIG["llm_model"], CONFIG["llm_host"])
        self.detector = PersonDetector(CONFIG["yolo_model"], CONFIG["detection_confidence"])
        self.cap = None
        self.state = "IDLE"
        self.last_detected = 0
        self.current_speech = ""
        self.running = False

    def init_camera(self):
        if cv2 is None:
            print("[CAMERA] cv2 not installed — running in headless/text mode")
            return False
        try:
            # Try USB cameras first (higher indices), then default computer camera
            for idx in [2, 1, 0]:
                self.cap = cv2.VideoCapture(idx)
                if self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    print(f"[CAMERA] Camera initialized on index {idx}")
                    return True
                
            print("[CAMERA] No camera found — running in headless mode")
            return False
        except Exception as e:
            print(f"[CAMERA] Error: {e}")
            return False

    def greet_person(self):
        greeting = random.choice(GREETINGS)
        self.current_speech = greeting
        self.servo.wave()
        self.tts.speak_async(greeting)
        self.state = "GREETING"

    def chat_loop(self):
        """One-shot conversation round."""
        self.state = "LISTENING"
        self.tts.speak_async("Go ahead, I'm listening!")
        user_input = self.stt.listen_once(timeout=6)

        if user_input:
            self.state = "THINKING"
            print(f"[CHAT] User said: {user_input}")
            response = self.llm.generate(user_input)
            self.current_speech = response
            self.state = "SPEAKING"
            self.tts.speak(response)
        else:
            self.tts.speak_async("I didn't catch that — but I'm still smiling!")

        self.state = "IDLE"

    def idle_animation(self):
        """Random idle behaviour when no person is present."""
        if random.random() < 0.1:
            phrase = random.choice(IDLE_PHRASES)
            self.current_speech = phrase
            self.tts.speak_async(phrase)
        self.servo.idle()

    def run(self):
        self.running = True
        has_camera = self.init_camera()
        overlay = DisplayOverlay(1280, 720)

        self.tts.speak_async("RoboGreet AI system online. Hello world!")
        print("[SYSTEM] Running. Press Q to quit.\n")

        while self.running:
            if has_camera:
                ret, frame = self.cap.read()
                if not ret:
                    continue

                # Mirror / flip horizontally (1 = horizontal) — creates a true mirror image
                frame = cv2.flip(frame, 1)

                detections = self.detector.detect(frame)
                frame = self.detector.draw(frame, detections)
                frame = overlay.render(frame, detections, self.state, self.current_speech)

                cv2.imshow("RoboGreet AI — Live Feed", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

                if detections:
                    now = time.time()
                    if self.state == "IDLE" or (now - self.last_detected) > CONFIG["idle_timeout_sec"]:
                        self.last_detected = now
                        self.llm.reset_history()
                        t = threading.Thread(target=self._interaction_thread, daemon=True)
                        t.start()
                else:
                    if self.state not in ("GREETING","LISTENING","THINKING","SPEAKING"):
                        self.state = "IDLE"
                        self.idle_animation()
            else:
                # Headless mode — run chat loop directly
                user_input = input("\n[INPUT] Type your message (or 'q' to quit): ").strip()
                if user_input.lower() == 'q':
                    break
                if user_input:
                    response = self.llm.generate(user_input)
                    print(f"[ROBOT] {response}")
                    self.tts.speak(response)

        self.shutdown()

    def _interaction_thread(self):
        self.greet_person()
        time.sleep(2)
        for _ in range(3):
            if self.state == "IDLE":
                break
            self.chat_loop()
            time.sleep(1)
        self.state = "IDLE"
        self.servo.idle()
        self.current_speech = "Come talk to me! I'm friendly!"

    def shutdown(self):
        print("\n[SYSTEM] Shutting down...")
        self.running = False
        self.servo.close()
        if self.cap:
            self.cap.release()
        if cv2 is not None:
            cv2.destroyAllWindows()
        print("[SYSTEM] Goodbye! (Robot offline)")


# ── Port Selection UI ────────────────────────────────────────────────────────
def select_arduino_port():
    """
    Port selection dialog.
    Shows ALL available COM ports and labels Bluetooth (HC-05) ports clearly
    so the user can choose between USB cable and Bluetooth.
    """
    try:
        import serial.tools.list_ports
        import serial
        import time
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        return CONFIG.get("arduino_port", "COM4")

    ports = serial.tools.list_ports.comports()

    # Label each port: mark Bluetooth ports clearly
    def label_port(p):
        desc = p.description or "Unknown"
        lower = desc.lower()
        if "bluetooth" in lower or "hc-0" in lower or "wireless" in lower:
            return f"{p.device} - 📶 BLUETOOTH: {desc}"
        return f"{p.device} - 🔌 USB: {desc}"

    port_list = [label_port(p) for p in ports]

    if not port_list:
        print("[SERVO] No serial ports found. Using default configuration.")
        return CONFIG.get("arduino_port", "COM4")

    root = tk.Tk()
    root.title("RoboGreet — Select Connection Port")
    root.geometry("520x260")
    root.eval('tk::PlaceWindow . center')

    use_arduino = tk.BooleanVar(value=True)
    selected_port = tk.StringVar()

    def toggle_state():
        state = "readonly" if use_arduino.get() else "disabled"
        btn_state = "normal" if use_arduino.get() else "disabled"
        combo.config(state=state)
        test_btn.config(state=btn_state)

    tk.Checkbutton(
        root, text="Enable Robot Arm Connection (Arduino + Servos)",
        variable=use_arduino, font=("Arial", 10, "bold"), command=toggle_state
    ).pack(pady=10)

    tk.Label(
        root,
        text="Select port:  🔌 USB cable  OR  📶 Bluetooth (HC-05 paired COM port)",
        font=("Arial", 9), fg="#444"
    ).pack()

    combo = ttk.Combobox(root, textvariable=selected_port, values=port_list, state="readonly", width=60)
    combo.pack(pady=8)

    if port_list:
        default_idx = 0
        current_port = CONFIG.get("arduino_port", "COM4")
        for i, p in enumerate(port_list):
            if p.startswith(current_port):
                default_idx = i
                break
        combo.current(default_idx)

    def test_connection():
        choice = selected_port.get()
        if not choice:
            return
        port = choice.split(" - ")[0]
        is_bt = "BLUETOOTH" in choice
        try:
            s = serial.Serial(port, CONFIG.get("arduino_baud", 9600), timeout=1)
            time.sleep(2.5)  # HC-05 needs a moment to settle
            # Flush startup message
            s.timeout = 3
            hello = s.readline().decode(errors="ignore").strip()
            s.timeout = 1
            s.write(b"WAVE\n")
            s.close()
            link = "Bluetooth (HC-05)" if is_bt else "USB Serial"
            extra = f"\nArduino said: '{hello}'" if hello else ""
            messagebox.showinfo(
                "Connection OK",
                f"✅ Connected via {link} on {port}\nSent: WAVE command.{extra}\n\nDid the robot arm wave?",
                parent=root
            )
        except Exception as e:
            messagebox.showerror("Connection Failed", f"❌ Could not open {port}\n\nError: {e}", parent=root)

    def on_connect():
        root.quit()

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=10)

    test_btn = tk.Button(btn_frame, text="🔍 Test Connection", command=test_connection, width=18)
    test_btn.pack(side="left", padx=5)
    tk.Button(btn_frame, text="▶ Connect & Start", command=on_connect, width=18).pack(side="left", padx=5)

    toggle_state()

    def on_closing():
        root.quit()
    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()
    choice = selected_port.get()
    is_enabled = use_arduino.get()

    try:
        root.destroy()
    except Exception:
        pass

    if not is_enabled:
        return "None"
    if choice:
        return choice.split(" - ")[0]
    return CONFIG.get("arduino_port", "COM4")


# ── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    CONFIG["arduino_port"] = select_arduino_port()
    robot = RoboGreetSystem()
    try:
        robot.run()
    except KeyboardInterrupt:
        robot.shutdown()
