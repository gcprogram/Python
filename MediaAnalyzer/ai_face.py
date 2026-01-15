import logging
import os
from deepface import DeepFace
from pathlib import Path
import queue
import threading
# own:
import media_tools

log = logging.getLogger(__name__)

class AIFace:
    def __init__(self, db_path:Path = None, model_name:str = "Facenet512", enforce_detection:bool = False):
        self.db_path:Path = db_path
        # Initialer Check/Laden der DB (erstellt die .pkl Datei)
        # Wir nutzen FaceNet512 für eine hohe Genauigkeit bei kleineren Gruppen
        self.model_name:str = model_name
        self.enforce_detection:bool = enforce_detection
        self.runs:bool = False
        self.ai_queue = queue.Queue()

    def set_db_path(self, db_path:Path):
        self.db_path:Path = db_path

    def _normalize_path(self, path: str) -> str:
        return path.encode('ascii', 'ignore').decode('ascii')

    def _identify_persons_image(self, image_path:Path) -> set:
        """Erkennt alle Personen auf einem Bild und gibt eine Liste der Namen zurück."""
        try:
            normalized_path = self._normalize_path( str(image_path) )
            # enforce_detection=False verhindert Abstürze, wenn kein Gesicht gefunden wird
            results = DeepFace.find(img_path=normalized_path,
                                    db_path=str(self.db_path),
                                    model_name=self.model_name,
                                    enforce_detection=self.enforce_detection,
                                    silent=True)

            found_persons = set()
            for df in results:
                if not df.empty:
                    # Der Ordnername in deiner DB ist der Name der Person
                    path = df.iloc[0]['identity']
                    person_name = os.path.basename(os.path.dirname(path))
                    found_persons.add(person_name)

            return set(found_persons)
        except Exception as e:
                logging.exception(f"identify_persons({image_path}): ")
        return []

    def identify_persons(self, file_path:Path) -> set:
        """Erkennt alle Personen in Videos Frames mit <interval> Abstand."""
        kind:str = media_tools.get_kind_of_media(file_path)
        persons:set = set()
        if kind == "image":
            persons = self._identify_persons_image(file_path)
        elif kind == "video":
            # Erzeuge eine Liste von Frame-Namen für das aktuelle Video
            folder = file_path.parent
            frame_prefix = os.path.splitext(os.path.basename(file_path))[0] + '+'
            frame_files = [os.path.join(folder, f) for f in os.listdir(folder)
                           if f.startswith(frame_prefix) and f.endswith('.png')]
            log.debug(f"Found {len(frame_files)} frames in {file_path}")
            # Schleife über alle Frames des Videofiles
            for frame in frame_files:
                persons = persons | self._identify_persons_image(frame)
        elif kind == "audio":
            infile = os.path.splitext(file_path)[0] + '+cover.png'
            if os.path.exists(infile) and os.path.isfile(infile):
                log.debug(f"Found Cover image in {infile}.")
                persons = self._identify_persons_image(infile)
        else:
            log.debug(f"Unkown kind {kind}")

        return persons

    def push(self, file_path:Path, kind:str, item_id):
        if kind not in ("image", "audio", "video"):
            return
        self.ai_queue.put( (file_path, kind, item_id), block=False, timeout=None)

    def get(self):
        log.info(f"Face queue.size={self.ai_queue.qsize()}")
        try:
            return self.ai_queue.get(block=True, timeout=10)
        except queue.Empty:
            return None

    def load(self) -> bool:
        if not self.db_path or not self.db_path.exists():
            log.error(f"⚠️ load() FaceDB not found at {self.db_path}. Set directory to FaceDB.")
            self.runs = False
        else:
            log.info("🗑✅ Loading Face AI Model.")
            self.runs = True
        return self.runs

    def unload(self):
        log.info("🗑️ Unloading Face AI Model.")

    def is_running(self) -> bool:
        return self.runs;

    def from_gpu_to_cpu(self):
        log.info("🔄 Moving Face AI Model from GPU to CPU.")

    def _wait_for_jobs(self):
        self.ai_queue.join()  # ⬅ BLOCKIERT, bis alle task_done() aufgerufen wurden
        self.root.after(0, self._on_all_jobs_done)

    def _on_all_jobs_done(self):
        log.debug("✅ Face AI finished analysing.")

        threading.Thread(
            target=self._wait_for_jobs,
            daemon=True,
            name="WaitForFaceJobs"
        ).start()

    def _faces_worker_loop(self):
        while True:
            job = self.ai_face.get()
            if job is None:
                log.info("Face AI has nothing to do.")
                break  # sauberer Shutdown

            path, kind, item_id = job
            persons:set = []
            try:
                persons = self.ai_face.identify_persons(Path(path))

            except Exception as e:
                log.exception("_faces_worker_loop(): ")
                persons = "⚠️"
            finally:
                self.root.after(
                    0,
                    self._update_tree_persons_columns,
                    item_id,
                    persons
                )
                self.ai_face.ai_queue.task_done()

# --- Integration in dein Projekt ---
#FACE_IDENT_DB="C:/TEMP/Fotos-DCIM-2023-/_FACE_IDENT/personen_db"
#identifier = AIFace(db_path=FACE_IDENT_DB)

# Beispiel für ein Foto (Punkt 4)
#personen = identifier.identify_persons(FACE_IDENT_DB+"/../foto1.jpg")
#print(f"Auf dem Bild foto1 sind: {personen}")
#personen = identifier.identify_persons(FACE_IDENT_DB+"/../foto2.jpg")
#print(f"Auf dem Bild foto2 sind: {personen}")

