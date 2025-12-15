import os
from os.path import exists, join
from pathlib import Path
import numpy as np
import whisper
from PIL import Image
from moviepy.video.io.VideoFileClip import VideoFileClip
from transformers import BlipProcessor, BlipForConditionalGeneration

from media_tools import format_time2mmss

"""
🎚️ 1. Mögliche Whisper-Modelle
Name	Größe (RAM)	Geschwindigkeit	Genauigkeit	Bemerkung
tiny	~75 MB	⚡ Sehr schnell	😐 Gering	Nur für sehr saubere, kurze Audios ohne Akzent
base	~142 MB	🔸 Schnell	🙂 Mittelmäßig	Gute Wahl bei klarer Sprache, ruhiger Umgebung
small	~466 MB	⚖️ Ausgewogen	👍 Gut	Sehr gutes Preis-Leistungs-Verhältnis (Standard)
medium	~1.5 GB	🐢 Langsamer	💪 Sehr gut	Bessere Erkennung bei Akzenten & Hintergrundgeräuschen
large / large-v2 / large-v3	~3–6 GB	🐌 Deutlich langsamer	🧠 Exzellent	Fast professionelle Qualität, sehr robust bei Rauschen, Akzent, Mehrsprachigkeit
"""



class AITools:
    """
    Klasse zur einmaligen Initialisierung des BLIP- (Image) und Whisper-Modells (Audio)
    sowie zur Generierung von Bild- und Video-Untertiteln.
    """

    DEFAULT_IMAGE_MODEL_PATH = Path.home() / ".cache/huggingface/hug"
    IMAGE_MODEL_NAME = "Salesforce/blip-image-captioning-base"
    AUDIO_MODEL_PATH = Path.home() / ".cache/whisper/"

    def __init__(self, image_model_path=None, audio_model_size="small"):
        # BLIP
        self.image_processor = None
        self.image_model = None
        # Whisper
        self.audio_model = None
        self.audio_model_size = audio_model_size

        blip_path = image_model_path if image_model_path is not None else self.DEFAULT_IMAGE_MODEL_PATH
        self._load_image_model(blip_path)
        self._load_audio_model(self.AUDIO_MODEL_PATH, audio_model_size)

    # ------------------ MODELLE LADEN ------------------
    def _load_image_model(self, path):
        """BLIP-Modell laden (lokal oder aus dem Netz)."""
        print(f"Image model at: {path}")
        if exists( path / "models--Salesforce--blip-image-captioning-base/snapshots/82a37760796d32b1411fe092ab5d4e227313294b/config.json"):
            try:
                path = path / ('models--Salesforce--blip-image-captioning-base/snapshots'
                               '/82a37760796d32b1411fe092ab5d4e227313294b')
                print("Lade Bild-Erkennungsmodell von lokal:", path)
                self.image_processor = BlipProcessor.from_pretrained(path)
                self.image_model = BlipForConditionalGeneration.from_pretrained(path)
                print("✅ Bilderkennung erfolgreich lokal geladen.")
                return
            except Exception:
                # 🚨 GEÄNDERT: Behandelt unvollständiges Modell ohne Netz
                print("⚠️ SCHWERWIEGENDER FEHLER: Lokales Modell unvollständig oder beschädigt unter:", path)
                print("   Da keine Netzwerkverbindung verfügbar ist oder eine Offline-Nutzung gewünscht wird,")
                print(
                    "   kann das BLIP-Modell nicht geladen werden. Bitte löschen Sie den Ordner und versuchen Sie es online erneut.")
                # Setzt die Modelle auf None, was später in generate_caption einen RuntimeError auslösen würde
                self.image_processor = None
                self.image_model = None
                return  # Verlassen der Methode, ohne Online-Versuch

        # 🚨 Hinzugefügt: Online-Versuch nur mit Netz
        try:
            print(f"Lade Bilderkennungsmodell ({self.IMAGE_MODEL_NAME}) herunter – das kann dauern...")
            self.image_processor = BlipProcessor.from_pretrained(self.IMAGE_MODEL_NAME, cache_dir=path)
            self.image_model = BlipForConditionalGeneration.from_pretrained(self.IMAGE_MODEL_NAME, cache_dir=path)
            print("✅ Bilderkennung erfolgreich gespeichert in:", path)
        except Exception as e:
            print(
                f"❌ FEHLER: Konnte BLIP-Modell nicht herunterladen. Ist eine Netzwerkverbindung vorhanden? Fehler: {e}")
            self.image_processor = None
            self.image_model = None

    def _load_audio_model(self, path, audio_model_size="small"):
        """Whisper für Transkription laden."""
        print(f"Lade Whisper-Modell ({audio_model_size}) ...")

        self.audio_model = whisper.load_model(audio_model_size)
        print(f"✅ Audioerkennung erfolgreich gespeichert in: $HOME/.cache/whisper/{audio_model_size}.pt")

    ###################################################################
    # ------------------ BILDER ------------------
    # Describe the image with BLIP AI model
    # image_or_path is either an image of a filepath to an image.
    ###################################################################
    def describe_image(self, image_or_path):
        """Generiert eine Bildunterschrift für ein einzelnes Bild."""
        if self.image_model is None or self.image_processor is None:
            raise RuntimeError("Das BLIP-Modell ist nicht initialisiert.")

        # Prüfen, ob die Eingabe ein PIL.Image-Objekt ist
        if not isinstance(image_or_path, Image.Image):
            image = Image.open(image_or_path).convert("RGB")
        else:
            image = image_or_path
        try:
            inputs = self.image_processor(image, return_tensors="pt")
            out = self.image_model.generate(**inputs, max_new_tokens=100)
            caption = self.image_processor.decode(out[0], skip_special_tokens=True)
            return caption.capitalize()
        except FileNotFoundError:
            return f"Fehler: Bilddatei nicht gefunden unter {image_or_path}"
        except Exception as e:
            return f"Fehler bei der Generierung der Unterschrift: {e}"

    ###################################################################
    # ------------------ VIDEOS ------------------
    # Describe Video by extracting frame images every interval seconds
    # and use describe_image on each interval frame.
    ###################################################################
    def describe_video_by_frames(self, video_path, interval=10):
        captions = []
        try:
            clip = VideoFileClip(video_path)
            folder = os.path.dirname(video_path)
            relpath = os.path.relpath(video_path, folder)
            print(f"🎞 Analysiere Video: {relpath}")

            duration = clip.duration
            times = np.arange(0, duration, interval)
            last_caption = ""
            for t in times:
                try:
                    frame = clip.get_frame(t)
                    image = Image.fromarray(frame)
                    caption = self.describe_image(image)
                    if caption != last_caption:
                        fmt_mm_ss = format_time2mmss(t)
                        captions.append(f"{fmt_mm_ss} {caption}")
                    last_caption = caption
                except Exception as e:
                    print("⚠️ Frame-Analyse-Fehler:", e)
                    continue
            clip.close()
        except Exception as e:
            print("⚠️ Fehler beim Lesen des Videos:", e)
            return f"[Fehler beim Analysieren des Videos: {e}]"

        # Kombinieren
        summary = " | ".join(captions)
        return summary.strip()

    ###################################################################
    # Do Audio2Text
    ###################################################################
    def transcribe_audio(self, path):
        try:
            result = self.audio_model.transcribe(audio=path, fp16=False)  # ignore model warning
            return result["text"].strip()
        except Exception:
            return ""
