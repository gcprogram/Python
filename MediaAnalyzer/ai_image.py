import os
import logging
from os.path import exists
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from moviepy.video.io.VideoFileClip import VideoFileClip
from transformers import BlipProcessor, BlipForConditionalGeneration
import queue
from media_tools import format_time2mmss

log = logging.getLogger(__name__)

class AIImage:
    """
    Klasse zur einmaligen Initialisierung des BLIP- (Image) Modells
    sowie zur Generierung von Bild- und Video-Untertiteln.
    """

    DEFAULT_IMAGE_MODEL_PATH = Path.home() / ".cache/huggingface/hub"
    IMAGE_MODEL_NAME = "Salesforce/blip-image-captioning-base"

    def __init__(self):
        self.ai_queue = queue.Queue()
        self.device_str = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(self.device_str)
        self.use_fp16 = (self.device_str == "cuda")

        # BLIP
        self.image_processor = None
        self.image_model = None
        self._load_image_model(self.DEFAULT_IMAGE_MODEL_PATH)

    # Pushes the job into the Queue.
    def push(self, path:Path, kind:str, item_id):
        if kind not in ("image", "audio", "video"):
            return
        self.ai_queue.put( (path, kind, item_id), block = False, timeout = None)
        log.debug(f"Image queue.size={self.ai_queue.qsize()}")

    # Retrieves the job from the Queue (FIFO) -> oldest job first.
    def _get(self):
        log.info(f"Image queue.size={self.ai_queue.qsize()}")
        try:
            return self.ai_queue.get(block=True, timeout=10)
        except queue.Empty:
            return None

    # ------------------ MODELLE LADEN ------------------
    def _load_image_model(self, path):
        """BLIP-Modell laden (lokal oder aus dem Netz)."""
        if exists( path / "models--Salesforce--blip-image-captioning-base/snapshots/82a37760796d32b1411fe092ab5d4e227313294b/config.json"):
            try:
                path = path / ('models--Salesforce--blip-image-captioning-base/snapshots'
                               '/82a37760796d32b1411fe092ab5d4e227313294b')
                log.info("🖼️ Image2Text AI Model found locally. Initializing...")
                self.image_processor = BlipProcessor.from_pretrained(path)
                if self.use_fp16:
                    self.image_model = BlipForConditionalGeneration.from_pretrained(path,torch_dtype=torch.float16).to(self.device)
                else:
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
            if self.use_fp16:
                self.image_model = BlipForConditionalGeneration.from_pretrained(self.IMAGE_MODEL_NAME, cache_dir=path, torch_dtype=torch.float16).to(self.device)
            else:
                self.image_model = BlipForConditionalGeneration.from_pretrained(self.IMAGE_MODEL_NAME, cache_dir=path).to(self.device)

            #  float16 (schneller auf GPU)
            log.info("🖼️ Image2Text model saved under:", path)
        except Exception:
            log.exception(f"❌ ERROR: Downloading Image2Text model:")
            self.image_processor = None
            self.image_model = None

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
                except Exception:
                    log.exception("⚠️ ERROR: Frame extraction or Image description problem:")
                    continue
            clip.close()
        except Exception:
            log.exception("⚠️ ERROR: VideoClip problem: ")
            return f"⚠️ ERROR: VideoClip problem"

        # Kombinieren
        summary = " | ".join(captions)
        return summary.strip()
