# media_tools.py
import exifread
import subprocess
import json
import re
import os
import io
from pathlib import Path
from datetime import datetime
from dateutil import parser
from geopy import Nominatim
from moviepy.video.io.VideoFileClip import VideoFileClip  # <- korrigierter Import
from typing import Tuple, Dict, Any
# Metadaten-Bibliotheken
from PIL import Image  # Für JPEGs/PNGs (Exif)
import exiftool  # Damit 'exiftool.exceptions' erkannt wird
from exiftool import ExifToolHelper  # Bester Allrounder, erfordert separate ExifTool-Installation!
from mutagen import File
from mutagen.wave import WAVE
from mutagen.id3 import ID3, APIC
import logging
import requests

log = logging.getLogger(__name__)
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
            return int(duration_seconds)
        else:
            return f"Fehler: Unbekanntes oder beschädigtes Format: {file_path}"

    except Exception as e:
        log.exception("_get_audio_duration({file_path}):")
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
# unused da es nicht ganz funktioniert.
###############################################
def _format_date(self, date_str):
    if not date_str:
        return ""
    try:
        # mögliche Formate aus EXIF / FFProbe
        for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(date_str[:19], fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                log.exception(f"Exception in _format_date(): ")
                pass
    except Exception:
        pass
    return date_str  # falls nicht parsbar, original zurückgeben


#############################################
# Find date of a video file
#############################################

def _get_date_from_metadata(filepath:Path, et_instance=None):
    """
    Versucht, das Erstellungsdatum aus den Metadaten der Datei zu extrahieren.
    Verwendet PyExifTool für beste Abdeckung.
    Gibt ein datetime-Objekt oder None zurück.
    """
    extension:str = filepath.suffix.lower()
    # 1. Fallback-Prüfung: Prüfe auf Dateierstellungsdatum (Windows ctime)
    # Wenn wir keine Metadaten finden, nutzen wir das Datum des Dateisystems
    try:
        timestamp = os.path.getctime(filepath)
        # KORRIGIERT: Erzeugt direkt ein datetime-Objekt
        fallback_date = datetime.fromtimestamp(timestamp)
    except:
        fallback_date = None

    if extension in FILE_TAGS and et_instance:
        try:
            # Verwende PyExifTool (erfordert ExifTool-Installation)
            metadata_list = et_instance.get_metadata(filepath)
            metadata = metadata_list[0] if metadata_list else {}

            # Gehe die priorisierten Tags für diesen Dateityp durch
            for tag in FILE_TAGS[extension]:
                if f'EXIF:{tag}' in metadata or f'QuickTime:{tag}' in metadata or tag in metadata:
                    # Extrahiere den Wert (oft im Format YYYY:MM:DD HH:MM:SS)
                    date_value = metadata.get(f'EXIF:{tag}') or metadata.get(f'QuickTime:{tag}') or metadata.get(
                        tag)
                    if isinstance(date_value, str):
                        # Korrigiere EXIF-Format YYYY:MM:DD zu YYYY-MM-DD und ersetze ':' in Zeit durch '.'
                        date_value = date_value.replace(':', '-', 2).replace(':', '.')
                        # Versuche, das Datum/die Uhrzeit zu parsen
                        try:
                            val = datetime.strptime(date_value, DATE_FORMAT_STR)
                            return val
                        except ValueError:
                            # Versuche, nur das Datum zu parsen
                            try:
                                val = datetime.strptime(date_value[:10], "%Y-%m-%d")
                                return val
                            except:
                                pass

        except Exception as e:
            # log.exception(f"Fehler bei PyExifTool für {os.path.basename(filepath)}:")
            pass

        # 2. Fallback: Für Audio-Dateien (WAV) versuchen wir Mutagen
        if extension == '.wav':
            try:
                # 💡 KORREKT: Verwende WAVE von Mutagen
                audio = WAVE(filepath)

                # WAV-Metadaten speichern das Datum oft im 'bext' oder 'info' Chunk als
                # 'IDAT' (creation date) oder 'date'/'creationdate' im LIST-Chunk.
                # Da WAV-Tags nicht standardisiert sind wie ID3, ist das schwierig.
                # Versuche, das 'IDAT' Tag aus dem RIFF-Info-Block zu extrahieren.
                date_str = None
                if audio.info and hasattr(audio.info, 'date'):
                    date_str = audio.info.date

                if date_str:
                    # Nutze dateutil.parser um flexible Datumsformate zu handhaben
                    dt_obj = parser.parse(date_str)
                    return dt_obj

            except Exception as e:
                # Wenn WAV-Metadaten fehlschlagen, gehen wir zum letzten Fallback
                # log.exception(f"WAV-Fehler bei {os.path.basename(filepath)}:")
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
def get_kind_of_media(path:Path) -> str:
    if not isinstance(path, Path):
        path = Path(path)
    ext = path.suffix.lower()
    kind:str = "unknown"
    if ext in MEDIA_EXT:
        kind = MEDIA_EXT[ext]
    return kind

############################################################
# Extract the meta data from all type of media files
############################################################
def get_meta_data_bundle(path: Path, meta_ai:dict, et_instance: object = None) -> Dict[str, Any]:
    res = { "Date": "", "Lat": "", "Lon": "", "Length": "", "Address": "", "Landmark":"" }
    kind = get_kind_of_media(path)
    if kind == "image":
        res = _get_exif_data(path)
    elif kind == "video":
        res = _get_video_metadata(path)
    elif kind == "audio":
        # ... (der Fallback-Block ist hier nicht relevant, da er in _get_date_from_metadata liegt)
        log.info(f"get_meta_data: {path}")
        dt_obj = _get_date_from_metadata(path, et_instance=et_instance)
        # Sicherstellen, dass das Datum immer im Zielformat (String) gespeichert wird
        if isinstance(dt_obj, datetime):
            res["Date"] = dt_obj.strftime(DATE_FORMAT_STR)
        else:
            res["Date"] = ""  # Oder behalten Sie den Standardwert
        res["Lat"] = ""
        res["Lon"] = ""
        res["Length"] = _get_audio_duration(path)
    res["Address"] = meta_ai.get("Address")
    res["Landmark"] = meta_ai.get("Landmark")
    return res

def _get_exif_data(path: Path) -> Dict[str, Any]:
    """
    Liest EXIF aus Bildern (Datum, GPS) und gibt Dict mit Schlüsseln:
    {'Date': str, 'Lat': float|'', 'Lon': float|''}
    """
    data = {"Date": "", "Lat": "", "Lon": "", "Length": "", "Address": "", "Landmark": ""}
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
                log.exception("_get_exif_data() ValueError")
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
                data["Lat"] = f"{lat:.6f}"
                data["Lon"] = f"{lon:.6f}"
    except Exception as e:
        # still return defaults, but print optional warning
        log.exception("_get_exif_data() Warnung EXIF: ")
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
def _get_video_metadata(path: Path) -> Dict[str, Any]:
    result = {"Date": "", "Lat": "", "Lon": "", "Length": "", "Address": "", "Landmark":""}
    # 1) Versuche moviepy für Dauer (falls moviepy funktioniert)
    try:
        clip = VideoFileClip(path)
        dur = float(clip.duration)
        clip.close()
        result["Length"] = str(dur)
    except Exception:
        log.exception("_get_video_metadata() Exception clip")
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
                    result["Length"] = dur_s
            except Exception:
                pass

        # creation_time: check format.tags and streams[*].tags
        tags = fmt.get("tags") or {}
        creation = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time")

        if creation:
            try:
                c = creation.strip()
                if c.endswith("Z"):
                    c = c[:-1]
                try:
                    dt = datetime.strptime(c, "%Y-%m-%dT%H:%M:%S.%f")
                except ValueError:
                    dt = datetime.strptime(c, "%Y-%m-%dT%H:%M:%S")
                result["Date"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                log.exception(f"⚠️ Fehler beim Parsen von creation_time: {creation}: ")

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
                result["Lat"] = f"{latlon[0]:.6f}"
                result["Lon"] = f"{latlon[1]:.6f}"
                break

        # also try top-level format tags for coords
        if (not result["Lat"] or not result["Lon"]) and tags:
            latlon = _extract_coords_from_video_tags(tags)
            if latlon and latlon[0] is not None:
                result["Lat"] = f"{latlon[0]:.6f}"
                result["Lon"] = f"{latlon[1]:.6f}"

    except Exception:
        log.exception("_get_video_metadata() Exception ffprobe not available")
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

def reverse_geocode(lat:float, lon:float):
    """Wandelt Koordinaten in einen Ortsnamen um (Nominatim - uses OpenStreetMap)."""
    if not lat or not lon:
        return ""
    loc: str = ""
    try:
        geolocator = Nominatim(user_agent="AI MediaAnalyzer")
        location = geolocator.reverse((lat, lon), language="de", timeout=10)
        if location and location.address:
            loc =  location.raw.get("name") or location.raw.get("display_name")
            landmark: str = location.raw.get("tourism") or location.raw.get("historic") or location.raw.get(
                "amenity") or location.raw.get("leisure")
            if loc or landmark:
                return loc, landmark
            else:
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
            return loc, landmark
    except Exception:
        log.exception("reverse_geocode() Exception Nominatim")
    return "",None


def get_nearest_landmark(lat: float, lon: float, radius: int = 500):
    # Overpass API URL
    overpass_url = "http://overpass-api.de/api/interpreter"

    # Overpass QL Abfrage
    overpass_query = f"""
    [out:json]; 
    (
      node["tourism"](around:{radius},{lat},{lon});
      way["tourism"](around:{radius},{lat},{lon});
      relation["tourism"](around:{radius},{lat},{lon});
    ); 
    out center; 
    """

    # Anfrage an die Overpass API
    response = requests.get(overpass_url, params={'data': overpass_query})

    # Überprüfung des Statuscodes
    if response.status_code == 200:
        data = response.json()
        # Wenn Ergebnisse vorhanden sind, die nächste Attraktion zurückgeben
        if data['elements']:
            # Hier könnte man die Entfernung ausrechnen, um die nächste Attraktion zu finden
            # Momentan geben wir einfach die erste gefundene Attraktion zurück
            return data['elements'][0]
        else:
            return None
    else:
        print(f"Fehler beim Abrufen der Daten: {response.status_code}")
        return None


def get_nearest_landmark2(lat:float, lon:float, radius=500):
    # Query: Suche im Radius um lat/lon nach "tourism"-Tags
    overpass_url = "https://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json];
    node["tourism"](around:{radius},{lat},{lon});
    out body;
    """

    response = requests.get(overpass_url, params={'data': overpass_query})
    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError:
            print("Die Antwort konnte nicht als JSON decodiert werden.")
            print("Antwortinhalt:", response.text)
    else:
        print(f"Fehler beim Abrufen der Daten: {response.status_code}")
        print("Antwortinhalt:", response.text)

    if data['elements']:
        # Das erste gefundene Element zurückgeben
        log.debug(f"Found {len(data['elements'])} nearest landmarks")
        return data['elements'][0].get('tags', {}).get('name', 'Unbekannte Landmark')
    return "None"

def extract_mp3_front_cover(mp3_path: str) -> Image.Image | None:
    base, _ = os.path.splitext(mp3_path)
    log.debug(f"mp3_path={mp3_path}, base={base}")
    out_name = f"{base}+cover.png"
    if os.path.exists(out_name):
        log.debug(f"Found file {out_name}")
        return Image.open(out_name)

    try:
        tags = ID3(mp3_path)
    except Exception as e:
        log.error(f"Error reading ID3 tags: {e}")
        return None

    front = None
    fallback = None
    for tag in tags.values():
        log.debug(f"Found tag {tag}")
        if isinstance(tag, APIC):
            log.debug(f"Found APIC tag with type {tag.type}")
            if tag.type == 3:
                front = tag
                break
            fallback = fallback or tag

    tag = front or fallback
    if not tag:
        log.warning(f"{mp3_path} has no image")
        return None

    try:
        img = Image.open(io.BytesIO(tag.data))
        log.debug(f"Write MP3 cover image to {out_name}")
        img.save(out_name)
        return img
    except Exception as e:
        log.error(f"Error opening image: {e}")
        return None

# ---------------- Hilfsfunktionen ----------------
#
# Speichert von einem Video alle <interval> Sekunden einen Frame als Bild
# Gespeichert unter "{base}+{mmss}.png"
#
@staticmethod
def save_video_frames(video_path, interval):
    """Speichert Frames als PNGs im gleichen Ordner."""
    from moviepy.video.io.VideoFileClip import VideoFileClip
    clip = VideoFileClip(video_path)
    base, _ = os.path.splitext(video_path)
    t = 0
    while t < clip.duration:
        frame = clip.get_frame(t)
        img = Image.fromarray(frame)
        mmss = format_time2mmss(t).replace(":", "-")
        out_name = f"{base}+{mmss}.png"
        img.save(out_name)
        t += interval
    clip.close()

#
# Bewahre die Original-Filezeit auf
#
def _preserve_file_times(path:Path):
    stat = os.stat(path)
    return stat.st_atime, stat.st_mtime

#
# Setze die Original-Filezeit zurück
#
def _restore_file_times(path:Path, atime, mtime):
    os.utime(path, (atime, mtime))

def assert_utf8(text: str) -> str:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Text is not valid UTF-8")
    return text
#
# Schreibe AI Metadaten (Bildschreibung, ...) ins Video-File.
def write_ai_metadata(
    path: Path, address: str = "", landmark:str = "", image2text: str ="", transcript: str = "", persons:set = "", et = None):

    log.info(f"Writing ai metadata to {path}")
    kind:str = get_kind_of_media(path)
    atime, mtime = _preserve_file_times(path)
    transcript = assert_utf8(transcript)
    image2text = assert_utf8(image2text)
    address = assert_utf8(address)
    landmark = assert_utf8(landmark)
    adr_mark = f"{address}|{landmark}"
    args = [
            "-charset",
            "utf8" ]
    args.append( "-XMP:CreatorTool=MediaAnalyzer AI")
    if kind == "audio":
        args.append(f"-Comment={image2text}")     # Cover Bild Beschreibung
        args.append(f"-ID3:Lyrics={transcript}")
        args.append(f"-ID3v2:UnsynchronizedLyrics={transcript}")
        args.append(f"-XMP-aimedia:Transcript={transcript}")
    elif kind == "image":
        args.append(f"-XMP:Location={adr_mark}")
        args.append(f"-XMP:FullAddress={adr_mark}")
        args.append(f"-XMP:Description={image2text}")
        args.append(f"-IPTC:Caption-Abstract={image2text}")
        args.append(f"-XMP:Transcript={transcript}")  # sollte leer sein
        args.append(f"-XMP-dc:subject={persons}")
        args.append(f"-XMP:Iptc4xmpExt:PersonInImage={persons}")
    elif kind == "video":
        args.append(f"-XMP:Location={adr_mark}")
        args.append(f"-QuickTime:LocationName={adr_mark}")
        args.append(f"-XMP:FullAddress={adr_mark}")
        args.append(f"-QuickTime:Description={image2text}")
        args.append(f"-XMP:Description={image2text}")
        args.append(f"-XMP-iptcExt:Transcript={transcript}") # Profi Transcript
        args.append(f"-XMP:Transcript={transcript}") # Transcript
        args.append(f"-XMP-dc:subject={persons}")
        args.append(f"-XMP:Iptc4xmpExt:PersonInImage={persons}")
    try:
        if et is None:
            with ExifToolHelper(encoding="utf-8") as et:
                log.warning("write_ai_metadata() Programming performance issue: exiftool et is None, therefore CPU costly instanciation. ")
                et._encoding = "utf-8"
                et.execute(*args, str(path))
        else:
            et._encoding = "utf-8"
            et.execute(*args, str(path))

        _restore_file_times(path, atime, mtime)
        file_orig:Path = Path(f"{path}_original")
        if path.exists() and path.stat().st_size > 0 and file_orig.exists() and file_orig.stat().st_size > 0:
            file_orig.unlink()

    except exiftool.exceptions.ExifToolExecuteError as e:
        log.error(f"ExifTool Error: {e.stderr}")  # Das hier verrät den echten Grund!
        log.exception("write_ai_metadata(): ")

#
# Lese die AI Metadaten
#

def read_ai_metadata(path: Path, et) -> dict:
    # Hinweis: Stelle sicher, dass et.execute_json mit dem Parameter "-G1" aufgerufen wurde
    meta_list = et.execute_json("-G1", "-s", str(path))
    meta = meta_list[0] if meta_list else {}
    kind: str = get_kind_of_media(path)

    # Initialisierung der Variablen
    address = ""
    landmark = ""
    image2text = ""
    audio2text = ""

    if kind == "audio":
        address = ""
        landmark = ""
        # Wichtig: Im JSON heißen die Tags meist 'Group:TagName'
        image2text = meta.get("ID3:Comment") or meta.get("File:Comment") or ""
        audio2text = (meta.get("XMP-aimedia:Transcript") or meta.get("ID3:Lyrics") or
                      meta.get("ID3:UnsynchronizedLyrics") or "")

    elif kind == "image":
        # Kein "-" vor dem Tag-Namen im Dictionary!
        adr_mark = meta.get("XMP:FullAddress") or meta.get("XMP:Location") or ""
        parts = adr_mark.split("|")
        address = parts[0] if len(parts) > 0 else ""
        landmark = parts[1] if len(parts) > 1 else ""
        image2text = (meta.get("XMP:Description") or
                      meta.get("IPTC:Caption-Abstract") or "")

    elif kind == "video":
        adr_mark = (meta.get("XMP:FullAddress") or
                   meta.get("QuickTime:LocationName") or "")
        parts = adr_mark.split("|")
        address = parts[0] if len(parts) > 0 else ""
        landmark = parts[1] if len(parts) > 1 else ""
        image2text = (meta.get("QuickTime:Description") or
                      meta.get("XMP:Description") or "")
        # Korrektur der Klammern und Tag-Namen
        audio2text = (meta.get("XMP-iptcExt:Transcript") or
                      meta.get("XMP:Transcript") or "")

    return {
        "Address": address,
        "Landmark": landmark,
        "caption": image2text,
        "transcript": audio2text, # Komma war hier wichtig
        "creator": meta.get("XMP:CreatorTool") or meta.get("Info:CreatorTool") or ""
    }

def delete_ai_metadata(path: Path, et):
    atime, mtime = _preserve_file_times(path)

    et.execute(
        "-ID3:Comment=",
        "-File:Comment=",
        "-ID3:Lyrics=",
        "-ID3:UnsynchronizedLyrics=",
        "-XMP:FullAddress=",
        "-XMP:Location=",
        "-XMP:Description=",
        "-XMP-aimedia:Transcript=",
        "-IPTC:Caption-Abstract=",
        "-XMP:FullAddress=",
        "-QuickTime:LocationName=",
        "-QuickTime:Description=",
        "-XMP-iptcExt:Transcript=",
        "-XMP:Transcript=",
        path
    )
    _restore_file_times(path, atime, mtime)
    file_orig: Path = Path(f"{path}_original")
    log.debug(f"path: {path}")
    log.debug(f"Original file: {file_orig}")
    if path.exists() and path.stat().st_size > 0 and file_orig.exists() and file_orig.stat().st_size > 0:
        file_orig.unlink()


