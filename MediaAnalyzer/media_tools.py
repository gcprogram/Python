# media_tools.py
import exifread
import subprocess
import json
import re
import os
from datetime import datetime
from geopy import Nominatim
from moviepy.video.io.VideoFileClip import VideoFileClip  # <- korrigierter Import
from typing import Tuple, Dict, Any
# Metadaten-Bibliotheken
from PIL import Image  # Für JPEGs/PNGs (Exif)
from mutagen.id3 import ID3  # Für WAVs (ID3-Tags)
from mutagen.mp4 import MP4  # Für MP4s
import exiftool  # Bester Allrounder, erfordert separate ExifTool-Installation!

from mutagen import File
from mutagen.wave import WAVE
from mutagen.mp3 import MP3

MEDIA_EXT = {
    ".jpg": "image", ".jpeg": "image", ".png": "image",
    ".mp4": "video", ".mov": "video", ".avi": "video",
    ".wav": "audio", ".mp3": "audio", ".m4a": "audio", ".flac": "audio"
}

# Unterstützte Dateitypen (Mapping zu Metadaten-Tags)
FILE_TAGS = {
    # Foto/Video
    '.jpg': ['DateTimeOriginal', 'CreateDate'],
    '.jpeg': ['DateTimeOriginal', 'CreateDate'],
    '.png': ['CreateDate'],
    '.mp4': ['CreationTime', 'DateTimeOriginal'],
    '.mov': ['CreationTime', 'DateTimeOriginal'],
    # Audio
    '.wav': ['TrackCreateDate', 'CreationTime'],
}
DATE_FORMAT_STR = "%Y-%m-%d %H:%M:%S"
DATE_EXIF_STR = "%Y:%m:%d %H:%M:%S"

########################################
# Find audio duration in the file
########################################
def _get_audio_duration(file_path):
    """Gibt die Dauer einer Audio-Datei (MP3 oder WAV) in Sekunden zurück."""
    try:
        # File() funktioniert für viele Formate und erkennt den Typ automatisch
        audio = File(file_path)

        if audio is not None:
            # Die Dauer ist im .info-Objekt gespeichert
            duration_seconds = audio.info.length
            return duration_seconds
        else:
            return f"Fehler: Unbekanntes oder beschädigtes Format: {file_path}"

    except Exception as e:
        return f"Fehler beim Lesen der Datei {file_path}: {e}"

############################################
# Converts 3 values DD, MM, SS to DD.DDDDDD
############################################
def _convert_to_degrees(value):
    """Hilfsfunktion: wandelt GPS EXIF-Werte in Dezimalgrad um."""
    try:
        d = float(value[0].num) / float(value[0].den)
        m = float(value[1].num) / float(value[1].den)
        s = float(value[2].num) / float(value[2].den)
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        return None
###############################################
# Format date of different formats to
# YYYY-mm-dd HH-MM-SS
###############################################
def format_date(self, date_str):
    if not date_str:
        return ""
    try:
        # mögliche Formate aus EXIF / FFProbe
        for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(date_str[:19], fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
    except Exception:
        pass
    return date_str  # falls nicht parsbar, original zurückgeben


#############################################
# Find date of a video file
#############################################

def _get_date_from_metadata(self, filepath):
    """
    Versucht, das Erstellungsdatum aus den Metadaten der Datei zu extrahieren.
    Verwendet PyExifTool für beste Abdeckung.
    Gibt ein datetime-Objekt oder None zurück.
    """
    extension = os.path.splitext(filepath)[1].lower()
    # 1. Fallback-Prüfung: Prüfe auf Dateierstellungsdatum (Windows ctime)
    # Wenn wir keine Metadaten finden, nutzen wir das Datum des Dateisystems
    try:
        timestamp = os.path.getctime(filepath)
        # KORRIGIERT: Erzeugt direkt ein datetime-Objekt
        fallback_date = datetime.fromtimestamp(timestamp)
    except:
        fallback_date = None

    if extension in self.FILE_TAGS:
        try:
            # Verwende PyExifTool (erfordert ExifTool-Installation)
            with exiftool.ExifTool() as et:
                metadata = et.get_metadata(filepath)

            # Gehe die priorisierten Tags für diesen Dateityp durch
            for tag in self.FILE_TAGS[extension]:
                if f'EXIF:{tag}' in metadata or f'QuickTime:{tag}' in metadata or tag in metadata:
                    # Extrahiere den Wert (oft im Format YYYY:MM:DD HH:MM:SS)
                    date_value = metadata.get(f'EXIF:{tag}') or metadata.get(f'QuickTime:{tag}') or metadata.get(
                        tag)
                    if isinstance(date_value, str):
                        # Korrigiere EXIF-Format YYYY:MM:DD zu YYYY-MM-DD und ersetze ':' in Zeit durch '.'
                        date_value = date_value.replace(':', '-', 2).replace(':', '.')
                        # Versuche, das Datum/die Uhrzeit zu parsen
                        try:
                            val = datetime.strptime(date_value, self.DATE_FORMAT_STR)
                            return val
                        except ValueError:
                            # Versuche, nur das Datum zu parsen
                            try:
                                val = datetime.strptime(date_value[:10], "%Y-%m-%d")
                                return val
                            except:
                                pass

        except Exception as e:
            # print(f"Fehler bei PyExifTool für {os.path.basename(filepath)}: {e}")
            pass

    # 2. Fallback: Für Audio-Dateien (WAV) versuchen wir Mutagen
    if extension == '.wav':
        try:
            audio = ID3(filepath)
            if 'TDRC' in audio:  # Standard-ID3-Tag für Datum/Zeit
                date_str = str(audio['TDRC']).replace('T', ' ').replace(':', '.')
                return datetime.strptime(date_str, DATE_FORMAT_STR)
        except:
            pass

    # 3. Fallback: Rückgabe des Dateisystem-Datums
    return fallback_date

############################################################
# Returns type of media file
#  audio
#  video
#  image
#  unknown
############################################################
def get_kind_of_media(path) -> str:
    ext = os.path.splitext(path)[1].lower()
    kind:str = "unknown"
    if ext in MEDIA_EXT:
        kind = MEDIA_EXT[ext]
    return kind

############################################################
# Extract the meta data from all type of media files
############################################################
def get_meta_data(path: str) -> Dict[str, Any]:
    res = { "Date": "", "Address": "", "Lat": "", "Lon": "", "Length": ""}
    kind = get_kind_of_media(path)
    if kind == "image":
        res = _get_exif_data(path)
    elif kind == "video":
        res = _get_video_metadata(path)
    elif kind == "audio":
        # ... (der Fallback-Block ist hier nicht relevant, da er in _get_date_from_metadata liegt)
        dt_obj = _get_date_from_metadata(path)
        # Sicherstellen, dass das Datum immer im Zielformat (String) gespeichert wird
        if isinstance(dt_obj, datetime):
            res["Date"] = dt_obj.strftime(DATE_FORMAT_STR)
        else:
            res["Date"] = ""  # Oder behalten Sie den Standardwert
        res["Address"] = ""
        res["Lat"] = ""
        res["Lon"] = ""
        res["Length"] = _get_audio_duration(path)

    return res

def _get_exif_data(path: str) -> Dict[str, Any]:
    """
    Liest EXIF aus Bildern (Datum, GPS) und gibt Dict mit Schlüsseln:
    {'Date': str, 'Lat': float|'', 'Lon': float|''}
    """
    data = {"Date": "", "Address": "", "Lat": "", "Lon": "", "Length": ""}
    try:
        with open(path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
        # Datum
        date_str = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime") or tags.get("EXIF DateTimeDigitized")
        if date_str:
            date_str = str(date_str).replace(" ", " ")  # Stellt sicher, dass es ein String ist
            try:
                # 1. Parsen des EXIF-Strings (z.B. '2025:11:06 19:33:26') in datetime-Objekt
                dt_obj = datetime.strptime(date_str, DATE_EXIF_STR)
                # 2. Formatieren des datetime-Objekts in den Ziel-String ('%Y-%m-%d %H:%M:%S')
                data["Date"] = dt_obj.strftime(DATE_FORMAT_STR)
            except ValueError:
                # Bei Parsing-Fehler, z.B. wenn nur das Datum vorhanden ist, ignorieren oder loggen
                pass

        # GPS
        gps_lat = tags.get("GPS GPSLatitude")
        gps_lon = tags.get("GPS GPSLongitude")
        gps_lat_ref = tags.get("GPS GPSLatitudeRef")
        gps_lon_ref = tags.get("GPS GPSLongitudeRef")
        if gps_lat and gps_lon:
            lat = _convert_to_degrees(gps_lat.values)
            lon = _convert_to_degrees(gps_lon.values)
            if lat is not None and lon is not None:
                # Vorzeichen nach Reference
                if gps_lat_ref and getattr(gps_lat_ref, "values", None):
                    if str(gps_lat_ref.values) != "N":
                        lat = -lat
                if gps_lon_ref and getattr(gps_lon_ref, "values", None):
                    if str(gps_lon_ref.values) != "E":
                        lon = -lon
                data["Address"] = reverse_geocode(lat, lon)
                data["Lat"] = f"{lat:.6f}"
                data["Lon"] = f"{lon:.6f}"
    except Exception as e:
        # still return defaults, but print optional warning
        # print("Warnung EXIF:", e)
        pass
    return data

###################################################
# Helper for _extract_coords_from_video_tags()
# to extract GPS coords in iso6709 format
###################################################
def _try_parse_iso6709(s: str) -> Tuple[Any, Any]:
    """
    Versucht ISO6709 oder +lat+lon / +lat-lon / lat,lon etc. zu parsen.
    Gibt (lat, lon) oder (None, None)
    """
    if not s or not isinstance(s, str):
        return None, None
    s = s.strip()
    # ISO6709 like +37.421998-122.084000/
    m = re.search(r'([+-]?\d+\.\d+)([+-]\d+\.\d+)', s)
    if m:
        try:
            lat = float(m.group(1))
            lon = float(m.group(2))
            return lat, lon
        except:
            pass
    # lat, lon or lat;lon or lat lon
    m2 = re.search(r'([+-]?\d+\.\d+)[,\s;]+([+-]?\d+\.\d+)', s)
    if m2:
        try:
            lat = float(m2.group(1))
            lon = float(m2.group(2))
            return lat, lon
        except:
            pass
    return None, None

######################################################################
# Durchsucht Tag Dictionary und gibt Position lat, lon zurück
######################################################################
def _extract_coords_from_video_tags(tags: Dict[str, Any]) -> Tuple[Any, Any]:
    if not tags:
        return None, None
    # Normalisiere keys zu strings
    for k, v in tags.items():
        key = str(k).lower()
        val = v
        if isinstance(val, bytes):
            try:
                val = val.decode('utf-8', errors='ignore')
            except:
                val = str(val)
        # Gemeinsame Kandidaten
        if "location" in key or "com.apple.quicktime.location" in key or "geolocation" in key or "gps" in key:
            lat, lon = _try_parse_iso6709(str(val))
            if lat is not None and lon is not None:
                return lat, lon
        # manche Kameras speichern "com.apple.quicktime.location.ISO6709"
        if "iso6709" in key:
            lat, lon = _try_parse_iso6709(str(val))
            if lat is not None and lon is not None:
                return lat, lon
    return None, None

####################################################################
# Extrahiere Informationen aus Videos:
#  - Date (creation_time falls vorhanden)
#  - Lat, Lon falls in Tags vorhanden (ISO6709 etc.)
#  - duration in mm:ss (versucht moviepy, ansonsten ffprobe)
#  - summary: einfacher bereinigter Dateiname
####################################################################
def _get_video_metadata(path: str) -> Dict[str, Any]:
    result = {"Date": "", "Address": "", "Lat": "", "Lon": "", "Length": ""}
    # 1) Versuche moviepy für Dauer (falls moviepy funktioniert)
    try:
        clip = VideoFileClip(path)
        dur = float(clip.duration)
        clip.close()
        minutes = int(dur // 60)
        seconds = int(dur % 60)
        result["Length"] = f"{minutes}:{seconds:02d}"
    except Exception:
        # fallback wird später per ffprobe versucht
        pass

    # 2) ffprobe JSON auslesen (Format + Streams) - zuverlässiger für tags & creation_time
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", path
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        info = json.loads(out)
        # duration fallback from format
        fmt = info.get("format", {})
        if not result["Length"]:
            dur_s = fmt.get("duration")
            try:
                if dur_s:
                    durf = float(dur_s)
                    minutes = int(durf // 60)
                    seconds = int(durf % 60)
                    result["Length"] = f"{minutes}:{seconds:02d}"
            except Exception:
                pass

        # creation_time: check format.tags and streams[*].tags
        tags = fmt.get("tags") or {}
        creation = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time")
        if creation:
            result["Date"] = creation

        # check stream tags as well
        streams = info.get("streams", [])
        for s in streams:
            stags = s.get("tags") or {}
            # creation
            if not result["Date"]:
                if "creation_time" in stags:
                    result["Date"] = stags.get("creation_time")
            # try to extract location from stream tags
            latlon = _extract_coords_from_video_tags(stags)
            if latlon and latlon[0] is not None:
                result["Address"] = reverse_geocode(latlon[0], latlon[1])
                result["Lat"] = f"{latlon[0]:.6f}"
                result["Lon"] = f"{latlon[1]:.6f}"
                break

        # also try top-level format tags for coords
        if (not result["Lat"] or not result["Lon"]) and tags:
            latlon = _extract_coords_from_video_tags(tags)
            if latlon and latlon[0] is not None:
                result["Address"] = reverse_geocode(latlon[0], latlon[1])
                result["Lat"] = f"{latlon[0]:.6f}"
                result["Lon"] = f"{latlon[1]:.6f}"

    except Exception:
        # falls ffprobe nicht verfügbar oder fehlerhaft -> ignore
        pass

    return result

###########################################################
# Format seconds into String mm:ss
###########################################################
def format_time2mmss(sekunden: float) -> str:
    # Berechnet die Minuten (ganzzahlig) und die verbleibenden Sekunden (float)
    ganz_minuten, rest_sekunden_float = divmod(sekunden, 60)
    ganz_sekunden = int(round(rest_sekunden_float))

    # Optional: Korrektur, falls die Rundung auf 60 Sekunden führt
    if ganz_sekunden == 60:
        ganz_minuten += 1
        ganz_sekunden = 0

    formatted_time = f"{int(ganz_minuten):02d}:{ganz_sekunden:02d}"

    return formatted_time

###########################################################
# Wandelt latitude, longitude in einen Ortsnamen um
# Parts Elements:
# {'aeroway': 'B', 'road': 'Circuit 2', 'town': 'Tremblay-en-France', 'municipality': 'Le Raincy', 'county': 'Seine-Saint-Denis', 'ISO3166-2-lvl6': 'FR-93', 'state': 'Île-de-France', 'ISO3166-2-lvl4': 'FR-IDF', 'region': 'Metropolitanes Frankreich', 'postcode': '93290', 'country': 'Frankreich', 'country_code': 'fr'}
# {'road': 'Circuit 2', 'town': 'Tremblay-en-France', 'municipality': 'Le Raincy', 'county': 'Seine-Saint-Denis', 'ISO3166-2-lvl6': 'FR-93', 'state': 'Île-de-France', 'ISO3166-2-lvl4': 'FR-IDF', 'region': 'Metropolitanes Frankreich', 'postcode': '93290', 'country': 'Frankreich', 'country_code': 'fr'}
# {'road': 'Rue de la Grande Borne', 'village': 'Le Mesnil-Amelot', 'municipality': 'Meaux', 'county': 'Seine-et-Marne', 'ISO3166-2-lvl6': 'FR-77', 'region': 'Metropolitanes Frankreich', 'postcode': '77990', 'country': 'Frankreich', 'country_code': 'fr'}
###########################################################

def reverse_geocode(lat, lon):
    """Wandelt Koordinaten in einen Ortsnamen um (Nominatim - uses OpenStreetMap)."""
    if not lat or not lon:
        return ""
    loc: str = ""
    try:
        geolocator = Nominatim(user_agent="media_analyzer")
        location = geolocator.reverse((lat, lon), language="de", timeout=10)
        if location and location.address:
            # z. B. nur Stadt oder Land extrahieren
            parts = location.raw.get("address", {})
            # parts contains a lot of address data
            # pts = [parts.get("postcode"), parts.get("city"), parts.get("town"), parts.get("village"), parts.get("state"), parts.get("country")]
            # In order to make address not too long, collect only a few parts:
            # Part 1: Road
            loc += parts.get("road")
            if len(loc) > 0:
                loc += ", "
            # Part2: City, town, village, state, municipality, or region
            loc += parts.get("city") or parts.get("town") or parts.get("village") or \
                   parts.get("state") or parts.get("municipality") or parts.get("region")
            # Part 3: country
            if len(loc) > 0:
                loc += ", "
            loc += parts.get("country")
            return loc
    except Exception:
        return ""
    return ""