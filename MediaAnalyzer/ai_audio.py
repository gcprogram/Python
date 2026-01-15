import gc
import os
import logging
import queue
from pathlib import Path
import whisper
import threading
import torch

"""
🎚️ 1. Mögliche Whisper-Modelle
Name	Größe (RAM)	Geschwindigkeit	Genauigkeit	Bemerkung
tiny	~75 MB	⚡ Sehr schnell	😐 Gering	Nur für sehr saubere, kurze Audios ohne Akzent
base	~142 MB	🔸 Schnell	🙂 Mittelmäßig	Gute Wahl bei klarer Sprache, ruhiger Umgebung
small	~466 MB	⚖️ Ausgewogen	👍 Gut	Sehr gutes Zeit-Leistung-Verhältnis (Standard)
medium	~1.5 GB	🐢 Langsamer	💪 Sehr gut	Bessere Erkennung bei Akzenten & Hintergrundgeräuschen
large / large-v2 / large-v3	~3–6 GB	🐌 Deutlich langsamer	🧠 Exzellent	Fast professionelle Qualität, sehr robust bei Rauschen, Akzent, Mehrsprachigkeit
"""

log = logging.getLogger(__name__)

class AIAudio:
    """
    Klasse zur einmaligen Initialisierung des Whisper-Modells (Audio)
    Macht AUDIO2TEXT
    """

    AUDIO_MODEL_PATH = Path.home() / ".cache/whisper/"

    def __init__(self, audio_model_size:str="large-v3"):
        self.device_str = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(self.device_str)
        self.use_fp16 = (self.device_str == "cuda")

        # Whisper
        self.ai_queue = queue.Queue()
        self.audio_model = None
        self.audio_model_ready = threading.Event()
        self.audio_model_error = None
        self.audio_model_size = audio_model_size
        self.audio_model_size_loaded = None
        self._load_audio_model(audio_model_size)

    #
    # Push jedes Audio und Video in die Queue. _audio_worker_loop()
    #
    def push(self, path, kind:str, item_id, image_text:str, length:float):
        if kind not in ("audio", "video"):
            return
        self.ai_queue.put(
            (path, kind, item_id, image_text, length)
        )
        log.info(f"queue.size={self.ai_queue.qsize()}")

    #
    # Wartet max. 10 Sekunden, wenn die Queue leer ist.
    #
    def _get(self):
        log.info(f"Audio queue.size={self.ai_queue.qsize()}")
        try:
            return self.ai_queue.get(block=True, timeout=10)
        except queue.Empty:
            return None

    def preload_audio_model(self, audio_model_size:str="large-v3"):
        """
        Startet das Laden des Whisper-Modells im Hintergrund.
        """

        def _load():
            try:
                self._load_audio_model(audio_model_size)
                self.audio_model_size_loaded = audio_model_size
            except Exception as exc:
                self.audio_model_error = exc
                self.audio_model = None
            finally:
                self.audio_model_ready.set()

        thread = threading.Thread(
            target=_load,
            name="WhisperModelLoader",
            daemon=True
        )
        thread.start()

    #
    # Lädt das Audio Modell (Whisper) in den Speicher
    #
    def _load_audio_model(self, audio_model_size:str):
        """
        Whisper für Transkription laden.
        Nutzt lokales Modell, falls vorhanden, sonst Download.
        """
        # Standard-Whisper-Cachepfad
        if self.audio_model is not None:
            if self.audio_model_size_loaded == self.audio_model_size:
                log.info("✅ Audio2Text AI Model already loaded into RAM is now ready")
            else:
                log.info("🗑️ Unloading Audio2Text AI Model...")
                del self.audio_model
                gc.collect()
                if torch.cuda.is_available():
                    log.info("🗑️ Deleting GPU cache")
                    torch.cuda.empty_cache()
                self.audio_model = None
                self.audio_model_size_loaded = None

        if self.audio_model is None or self.audio_model_error is not None:
            cache_dir = os.path.join( Path.home(), ".cache", "whisper")
            model_filename = f"{audio_model_size}.pt"
            model_path = os.path.join(cache_dir, model_filename)
            log.info(f"🎧 Audio2Text AI Model runs on {self.device_str.upper()}")
            if os.path.exists(model_path):
                log.info(f"🎧 Audio2Text AI Model locally found ({model_path}). Initializing...")
                self.audio_model = whisper.load_model(model_path,device=self.device)
            else:
                log.info("🎧  Audio2Text AI Model not found – Download started...")
                self.audio_model = whisper.load_model(audio_model_size, device=self.device)
                log.info(f"🎧 Audio2Text AI Model saved locally under: {model_path}")
            if self.use_fp16:
               self.audio_model.half()  # Konvertiert zu float16 (schneller auf GPU)

            log.info("✅ Audio2Text AI Model loaded into RAM is now ready")

    ###################################################################
    # Do Audio2Text
    ###################################################################
    def transcribe_audio(self, path:Path):
        if self.audio_model is None:
            raise RuntimeError("❌ FATAL: Audio AI Model not yet initialized.")

        try:
            log.debug(f"transcribe_audio({os.path.basename(path)}): START")
            result = self.audio_model.transcribe(audio=str(path), fp16=self.use_fp16)  # ignore model warning
            log.info(f"transcribe_audio({os.path.basename(path)})={result}")
            return result["text"].strip()
        except Exception as e:
            log.exception("transcribe_audio()")
            return "⚠️ ERROR in Audio transcription"
