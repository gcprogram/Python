from os.path import exists, join
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
import torch
from pathlib import Path
import numpy as np
from moviepy.video.io.VideoFileClip import VideoFileClip
import whisper
import media_tools

"""
🎚️ 1. Mögliche Whisper-Modelle
Name	Größe (RAM)	Geschwindigkeit	Genauigkeit	Bemerkung
tiny	~75 MB	⚡ Sehr schnell	😐 Gering	Nur für sehr saubere, kurze Audios ohne Akzent
base	~142 MB	🔸 Schnell	🙂 Mittelmäßig	Gute Wahl bei klarer Sprache, ruhiger Umgebung
small	~466 MB	⚖️ Ausgewogen	👍 Gut	Sehr gutes Preis-Leistungs-Verhältnis (Standard)
medium	~1.5 GB	🐢 Langsamer	💪 Sehr gut	Bessere Erkennung bei Akzenten & Hintergrundgeräuschen
large / large-v2 / large-v3	~3–6 GB	🐌 Deutlich langsamer	🧠 Exzellent	Fast professionelle Qualität, sehr robust bei Rauschen, Akzent, Mehrsprachigkeit
"""



class DescriptionGenerator:
    """
    Klasse zur einmaligen Initialisierung des BLIP- (Image) und Whisper-Modells (Audio)
    sowie zur Generierung von Bild- und Video-Untertiteln.
    """

    DEFAULT_IMAGE_MODEL_PATH = "./image_ai" # Path.home() / ".cache/huggingface/hug"
    IMAGE_MODEL_NAME = "Salesforce/blip-image-captioning-base"

    def __init__(self, image_model_path=None, audio_model_size="small"):
        # BLIP
        self.image_processor = None
        self.image_model = None
        # Whisper
        self.audio_model = None
        self.audio_model_size = audio_model_size

        blip_path = image_model_path if image_model_path is not None else self.DEFAULT_IMAGE_MODEL_PATH
        self._load_image_model(blip_path)
        self._load_audio_model(audio_model_size)

    # ------------------ MODELLE LADEN ------------------
    def _load_image_model(self, path):
        """BLIP-Modell laden (lokal oder aus dem Netz)."""
        if exists(join(path, "config.json")):
            try:
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

    def _load_audio_model(self, audio_model_size="small"):
        """Whisper für Transkription laden."""
        print(f"Lade Whisper-Modell ({audio_model_size}) ...")
        self.audio_model = whisper.load_model(audio_model_size)
        print(f"✅ Audioerkennung erfolgreich gespeichert in: HOME/.cache/whisper/{audio_model_size}.pt")

    # ------------------ BILDER ------------------
    def generate_caption(self, image_path):
        """Generiert eine Bildunterschrift für ein einzelnes Bild."""
        if self.image_model is None or self.image_processor is None:
            raise RuntimeError("Das BLIP-Modell ist nicht initialisiert.")

        try:
            image = Image.open(image_path).convert("RGB")
            inputs = self.image_processor(image, return_tensors="pt")
            out = self.image_model.generate(**inputs, max_new_tokens=100)
            caption = self.image_processor.decode(out[0], skip_special_tokens=True)
            return caption.capitalize()
        except FileNotFoundError:
            return f"Fehler: Bilddatei nicht gefunden unter {image_path}"
        except Exception as e:
            return f"Fehler bei der Generierung der Unterschrift: {e}"

    # ------------------ VIDEOS ------------------
    def summarize_video_with_frames(self, video_path, interval=10):
        """
        Erstellt eine Beschreibung eines Videos, indem mehrere Frames mit BLIP analysiert werden
        und das Transkript mit Whisper kombiniert wird.
        """
        captions = []
        spoken_text = ""
        try:
            clip = VideoFileClip(video_path)
            print(f"🎞 Analysiere Video: {video_path}")
            duration = clip.duration
            times = np.arange(0, duration, interval)
            last_caption = ""
            for t in times:
                try:
                    frame = clip.get_frame(t)
                    image = Image.fromarray(frame)
                    caption = self._generate_caption_from_image(image)
                    if caption != last_caption:
                        fmt_mm_ss = _format_time2mmss(t)
                        captions.append(f"{fmt_mm_ss} {caption}")
                except Exception as e:
                    print("⚠️ Frame-Analyse-Fehler:", e)
                    continue
            clip.close()
        except Exception as e:
            print("⚠️ Fehler beim Lesen des Videos:", e)
            return f"[Fehler beim Analysieren des Videos: {e}]"

        # Transkription
        try:
            result = self.audio_model.transcribe(video_path, fp16=False)
            spoken_text = result.get("text", "").strip()
        except Exception as e:
            print("⚠️ Transkriptionsfehler:", e)
            spoken_text = ""

        # Kombinieren
        visual_summary = " | ".join(captions)
        if spoken_text:
            summary = f"{visual_summary}. Gesprochen: {spoken_text}..."
        else:
            summary = visual_summary

        return summary.strip()

    def transcribe_audio(self, path):
        try:
            result = self.audio_model.transcribe(audio=path, fp16=False)  # ignore model warning
            return result["text"].strip()
        except Exception:
            return ""

    def _generate_caption_from_image(self, image):
        """Hilfsfunktion: Caption direkt aus PIL-Image."""
        inputs = self.image_processor(image, return_tensors="pt")
        out = self.image_model.generate(**inputs, max_new_tokens=100)
        return self.image_processor.decode(out[0], skip_special_tokens=True).capitalize()

