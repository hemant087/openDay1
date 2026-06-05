try:
    from faster_whisper import WhisperModel
    print("SUCCESS: faster-whisper is installed!")
except ImportError:
    print("ERROR: faster-whisper is not installed. Please run: pip install faster-whisper")
