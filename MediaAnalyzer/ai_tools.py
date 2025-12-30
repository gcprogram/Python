import gc
import os
import logging
from os.path import exists
from pathlib import Path
import numpy as np
import whisper
import threading
import torch
from PIL import Image
from moviepy.video.io.VideoFileClip import VideoFileClip
from transformers import BlipProcessor, BlipForConditionalGeneration
from media_tools import format_time2mmss

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

class AITools:
    """
    Klasse zur einmaligen Initialisierung des BLIP- (Image) und Whisper-Modells (Audio)
    sowie zur Generierung von Bild- und Video-Untertiteln.
    """

    DEFAULT_IMAGE_MODEL_PATH = Path.home() / ".cache/huggingface/hug"
    IMAGE_MODEL_NAME = "Salesforce/blip-image-captioning-base"
    AUDIO_MODEL_PATH = Path.home() / ".cache/whisper/"

    def __init__(self, audio_model_size:str="large-v3"):
        self.device_str = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(self.device_str)

        # BLIP
        self.image_processor = None
        self.image_model = None
        # Whisper
        self.audio_model = None
        self.audio_model_ready = threading.Event()
        self.audio_model_error = None
        self.audio_model_size = audio_model_size
        self.audio_model_size_loaded = None
        self._load_image_model(self.DEFAULT_IMAGE_MODEL_PATH)
        self._load_audio_model(audio_model_size)
        self.use_fp16 = (self.device_str == "cuda")

    # ------------------ MODELLE LADEN ------------------
    def _load_image_model(self, path):
        """BLIP-Modell laden (lokal oder aus dem Netz)."""
        if exists( path / "models--Salesforce--blip-image-captioning-base/snapshots/82a37760796d32b1411fe092ab5d4e227313294b/config.json"):
            try:
                path = path / ('models--Salesforce--blip-image-captioning-base/snapshots'
                               '/82a37760796d32b1411fe092ab5d4e227313294b')
                log.info("🖼️ Image2Text AI Model found locally. Initializing...")
                self.image_processor = BlipProcessor.from_pretrained(path)
                self.image_model = BlipForConditionalGeneration.from_pretrained(path).to(self.device)
                log.info("✅ Image2Text AI Model loaded into RAM is now ready.")
                return
            except Exception:
                # 🚨 GEÄNDERT: Behandelt unvollständiges Modell ohne Netz
                log.exception(f"⚠️ FATAL: Local Image2Text AI model incomplete or damaged (or new version): {path}")
                log.warning("   No network found therefore BLIP cannot be downloaded.")
                log.warning("   Delete the cache folder and restart.")
                # Setzt die Modelle auf None, was später in generate_caption einen RuntimeError auslösen würde
                self.image_processor = None
                self.image_model = None
                return  # Verlassen der Methode, ohne Online-Versuch

        # 🚨 Hinzugefügt: Online-Versuch nur mit Netz
        try:
            log.info(f"🖼️ Image2Text AI model downloading ({self.IMAGE_MODEL_NAME})...")
            self.image_processor = BlipProcessor.from_pretrained(self.IMAGE_MODEL_NAME, cache_dir=path)
            self.image_model = BlipForConditionalGeneration.from_pretrained(self.IMAGE_MODEL_NAME, cache_dir=path).to(self.device)
            log.info("🖼️ Image2Text model saved under:", path)
        except Exception as e:
            log.exception(f"❌ ERROR: Downloading Image2Text model:")
            self.image_processor = None
            self.image_model = None

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

            log.info("✅ Audio2Text AI Model loaded into RAM is now ready")

    ###################################################################
    # Describe the image with BLIP AI model
    # image_or_path is either an image of a filepath to an image.
    ###################################################################
    def describe_image(self, image_or_path):
        """Generiert eine Bildunterschrift für ein einzelnes Bild."""
        if self.image_model is None or self.image_processor is None:
            raise RuntimeError("❌ FATAL: Image AI Model not yet initialized.")

        try:
            if isinstance(image_or_path, Image.Image):
                image = image_or_path
                source = "<PIL.Image>"
            else:
                image = Image.open(image_or_path).convert("RGB")
                source = os.path.basename(str(image_or_path))

            log.debug(f"describe_image({source}): START")

            #command = "Describe objects, people, and location. "
            inputs = self.image_processor(image, return_tensors="pt").to(self.device)
            out = self.image_model.generate(**inputs,
                                            max_new_tokens=100,
                                            # BLIP-2: do_sample=True,
                                            # BLIP-2: temperature=0.7,
                                            # BLIP-2: top_p=0.9,
                                            # BLIP-2: repetition_penalty=1.1
                                            )
            caption = self.image_processor.decode(out[0], skip_special_tokens=True)
            log.info(f"describe_image()={caption}")
            return caption.capitalize()
        except FileNotFoundError:
            return f"⚠️ ERROR: Image not found: {image_or_path}"
        except Exception as e:
            return f"⚠️ ERROR: Image AI problem: {e}"

    ###################################################################
    # ------------------ VIDEOS ------------------
    # Describe Video by extracting frame images every interval seconds
    # and use describe_image on each interval frame.
    ###################################################################
    def describe_video_by_frames(self, video_path, interval:int=30):
        captions = []
        try:
            clip = VideoFileClip(video_path)
            folder = os.path.dirname(video_path)
            relpath = os.path.relpath(video_path, folder)

            duration = clip.duration
            fmt_dur_mm_ss = format_time2mmss(duration)
            log.info(f"🎞 Analyse Video: {relpath}, with {duration/interval:.0f} frames")
            times = np.arange(0, duration, interval)
            last_caption = ""
            for t in times:
                try:
                    fmt_mm_ss = format_time2mmss(t)
                    log.info(f"  Frame {fmt_mm_ss}/{fmt_dur_mm_ss}")
                    frame = clip.get_frame(t)
                    image = Image.fromarray(frame)
                    caption = self.describe_image(image)
                    if caption != last_caption:
                        captions.append(f"{fmt_mm_ss} {caption}")
                    last_caption = caption
                except Exception as e:
                    log.exception("⚠️ ERROR: Frame extraction or Image description problem:")
                    continue
            clip.close()
        except Exception as e:
            log.exception("⚠️ ERROR: VideoClip problem: ")
            return f"⚠️ ERROR: VideoClip problem"

        # Kombinieren
        summary = " | ".join(captions)
        return summary.strip()

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
