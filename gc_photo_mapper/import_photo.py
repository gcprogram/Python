import os
import sqlite3
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

def get_exif_data(img_path):
    try:
        image = Image.open(img_path)
        exif_data = image._getexif()
        if not exif_data:
            return None

        gps_info = {}
        for tag, value in exif_data.items():
            decoded = TAGS.get(tag)
            if decoded == 'GPSInfo':
                for t in value:
                    sub_decoded = GPSTAGS.get(t)
                    gps_info[sub_decoded] = value[t]
                return gps_info
        return None
    except Exception as e:
        print(f"Fehler beim Lesen von EXIF für {img_path}: {e}")
        return None

def dms_to_decimal(value, ref):
    print(f"   dms {value}")
    try:
        d = value[0][0] / value[0][1]
        m = value[1][0] / value[1][1]
        s = value[2][0] / value[2][1]
        decimal = d + (m / 60.0) + (s / 3600.0)
        print(f"decimal={decimal}")
        if ref in ['S', 'W']:
            decimal = -decimal
        print(f"   decimal {decimal}")
        return decimal
    except Exception as e:
        print(f"Expection {e}")
        return None

def extract_gps_from_exif(gps_info):
    try:
        lat = dms_to_decimal(gps_info['GPSLatitude'], gps_info['GPSLatitudeRef'])
        lon = dms_to_decimal(gps_info['GPSLongitude'], gps_info['GPSLongitudeRef'])
        return lat, lon
    except Exception:
        return None

def import_photos(photo_dir, db_path='geocaching.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for root, dirs, files in os.walk(photo_dir):
        for file in files:
            print(f" working on {file}")
            if file.lower().endswith(('.jpg', '.jpeg')):
                full_path = os.path.abspath(os.path.join(root, file))
                gps_info = get_exif_data(full_path)
                print(f"  gps_info {gps_info}")
                if gps_info:
                    coords = extract_gps_from_exif(gps_info)
                    print(f"  coords {coords}")
                    if coords:
                        lat, lon = coords
                        try:
                            cursor.execute('''
                                INSERT OR REPLACE INTO photos (filename, lat, lon)
                                VALUES (?, ?, ?)
                            ''', (full_path, lat, lon))
                            print(f"Eingelesen: {file} ({lat:.6f}, {lon:.6f})")
                        except sqlite3.Error as e:
                            print(f"DB-Fehler bei {file}: {e}")
    conn.commit()
    conn.close()
    print("Foto-Import abgeschlossen.")

# Beispiel
if __name__ == '__main__':
    import_photos('C:/TEMP/Fotos-DCIM-2023-/2025-05-03 16 Icons Tag Prag Hannover')
