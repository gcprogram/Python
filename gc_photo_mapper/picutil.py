import os
from PIL import Image, ImageOps
import base64
from io import BytesIO
import dbutil

########################################################
# Calculates a thumbnail and stores it in the photos 
# table.
########################################################

def create_thumbnail(db_path, size, progress_callback, log_callback):
    log_callback("Beginne mit Thumbnail Generierung...")
    rows = dbutil.read_photo_without_thumbnail(db_path)
    if not rows:
        return None

    total = len(rows)
    idx = 0
    done = 0
    for filepath, thumbimg in rows:
        if not os.path.exists(filepath):
            continue
        try:
            with Image.open(filepath) as img:
                if thumbimg is None: # should always be None because of SELECT statement
                    img = ImageOps.exif_transpose(img)    # transpose portrait/landscape according to rotate factor
                    img.thumbnail(size)
                    w = img.width
                    h = img.height
                    buffer = BytesIO()
                    img.save(buffer, format="JPEG", exif=b'')        
                    dbutil.write_photo_thumbnail(db_path, filepath, w, h, buffer.getvalue())
                    done += 1
        except Exception as e:
            print(f"Error create_thumbnail_db: filepath={filepath}")
            log_callback(f"⚠️ {filepath}: Fehler beim Erzeugen von Thumbnail in DB: {e}")

        idx += 1;
        if progress_callback:
            progress_callback(idx / total * 100)

    if log_callback:
        log_callback(f"✔️ {done} Thumbnails erzeugt.")

#######################################################
# Read geocache icons to database and create dataurls
########################################################
def read_icons_files(db_path, source_dir, progress_callback=None, log_callback=None):
    type_map = {
        "type_advlab.png": "Lab Cache",
        "type_earth.png": "Earthcache",
        "type_location.png": "Locationless (Reverse) Cache",
        "type_tradi.png": "Traditional Cache",
        "type_ape.png": "Project Ape Cache",
        "type_event.png": "Event Cache",
        "type_maze.png": "GPS Adventures Exhibit",
        "type_virtual.png": "Virtual Cache",
        "type_block.png": "Geocaching HQ Block Party",
        "type_giga.png": "Giga-Event Cache",
        "type_mega.png": "Mega-Event Cache",
        "type_webcam.png": "Webcam Cache",
        "type_cce.png": "Community Celebration Event",
        "type_hq.png": "Geocaching HQ",
        "type_multi.png": "Multi-cache",
        "type_wherigo.png": "Wherigo Cache",
        "type_cito.png": "Cache In Trash Out Event",
        "type_letter.png": "Letterbox hybrid",
        "type_mystery.png": "Unknown Cache",
    }
    
    if len(type_map) == dbutil.get_number_icons(db_path):
        return
        
    if source_dir is None:
        source_dir = os.getcwd()

    files = [f for f in os.listdir(source_dir) if f.endswith(".png") and f in type_map]
    total = len(files)

    # Convert PNG files to base64 encoded dataurl
    for i, filename in enumerate(files):
        full_path = os.path.join(source_dir, filename)
        with open(full_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
            data_url = f"data:image/png;base64,{encoded}"
            type_label = type_map[filename]
            dbutil.write_icons(db_path,filename, type_label, data_url)
        print(f"✔️ {filename} als '{type_label}' gespeichert.")

    if log_callback:
        print(f"✅ {total} Icons erfolgreich importiert.")
  