import os
from deepface import DeepFace
import pandas as pd


class FaceIdentifier:
    def __init__(self, db_path):
        self.db_path = db_path
        # Initialer Check/Laden der DB (erstellt die .pkl Datei)
        # Wir nutzen FaceNet512 für eine hohe Genauigkeit bei kleineren Gruppen
        self.model_name = "Facenet512"

    def identify_persons(self, image_path):
        """Erkennt alle Personen auf einem Bild und gibt eine Liste der Namen zurück."""
        try:
            # enforce_detection=False verhindert Abstürze, wenn kein Gesicht gefunden wird
            results = DeepFace.find(img_path=image_path,
                                    db_path=self.db_path,
                                    model_name=self.model_name,
                                    enforce_detection=False,
                                    silent=True)

            found_persons = set()
            for df in results:
                if not df.empty:
                    # Der Ordnername in deiner DB ist der Name der Person
                    path = df.iloc[0]['identity']
                    person_name = os.path.basename(os.path.dirname(path))
                    found_persons.add(person_name)

            return list(found_persons)
        except Exception as e:
            print(f"Fehler bei {image_path}: {e}")
            return []


# --- Integration in dein Projekt ---
FACE_IDENT_DB="C:/TEMP/Fotos-DCIM-2023-/_FACE_IDENT/personen_db"
identifier = FaceIdentifier(db_path=FACE_IDENT_DB)

# Beispiel für ein Foto (Punkt 4)
personen = identifier.identify_persons(FACE_IDENT_DB+"/../foto1.jpg")
print(f"Auf dem Bild foto1 sind: {personen}")
personen = identifier.identify_persons(FACE_IDENT_DB+"/../foto2.jpg")
print(f"Auf dem Bild foto2 sind: {personen}")

# Beispiel für dein Video-Loop (Punkt 5)
# Du extrahierst alle 30s ein Frame 'frame_30s.jpg'
# personen_im_video_segment = identifier.identify_persons("frame_30s.jpg")