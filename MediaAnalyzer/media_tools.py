# media_tools.py
import exifread
import subprocess
import json
import re
import os
from moviepy.video.io.VideoFileClip import VideoFileClip  # <- korrigierter Import
from typing import Tuple, Dict, Any

def _convert_to_degrees(value):
    """Hilfsfunktion: wandelt GPS EXIF-Werte in Dezimalgrad um."""
    try:
        d = float(value[0].num) / float(value[0].den)
        m = float(value[1].num) / float(value[1].den)
        s = float(value[2].num) / float(value[2].den)
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        return None

def get_exif_data(path: str) -> Dict[str, Any]:
    """
    Liest EXIF aus Bildern (Datum, GPS) und gibt Dict mit Schlüsseln:
    {'Date': str, 'Lat': float|'', 'Lon': float|''}
    """
    data = {"Date": "", "Lat": "", "Lon": ""}
    try:
        with open(path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
        # Datum
        date = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime") or tags.get("EXIF DateTimeDigitized")
        if date:
            data["Date"] = str(date)

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
                data["Lat"], data["Lon"] = lat, lon
    except Exception as e:
        # still return defaults, but print optional warning
        # print("Warnung EXIF:", e)
        pass
    return data


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


def _extract_coords_from_tags(tags: Dict[str, Any]) -> Tuple[Any, Any]:
    """
    Gehe Tag-Dict durch und suche nach möglichen Location-/GPS-Feldern.
    """
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


def get_video_metadata(path: str) -> Dict[str, Any]:
    """
    Extrahiere Informationen aus Videos:
    - Date (creation_time falls vorhanden)
    - Lat, Lon falls in Tags vorhanden (ISO6709 etc.)
    - duration in mm:ss (versucht moviepy, ansonsten ffprobe)
    - summary: einfacher bereinigter Dateiname
    """
    result = {"Date": "", "Lat": "", "Lon": "", "duration": "", "summary": ""}
    # 1) Versuche moviepy für Dauer (falls moviepy funktioniert)
    try:
        clip = VideoFileClip(path)
        dur = float(clip.duration)
        clip.close()
        minutes = int(dur // 60)
        seconds = int(dur % 60)
        result["duration"] = f"{minutes}:{seconds:02d}"
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
        if not result["duration"]:
            dur_s = fmt.get("duration")
            try:
                if dur_s:
                    durf = float(dur_s)
                    minutes = int(durf // 60)
                    seconds = int(durf % 60)
                    result["duration"] = f"{minutes}:{seconds:02d}"
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
            latlon = _extract_coords_from_tags(stags)
            if latlon and latlon[0] is not None:
                result["Lat"], result["Lon"] = latlon
                break

        # also try top-level format tags for coords
        if (not result["Lat"] or not result["Lon"]) and tags:
            latlon = _extract_coords_from_tags(tags)
            if latlon and latlon[0] is not None:
                result["Lat"], result["Lon"] = latlon

    except Exception:
        # falls ffprobe nicht verfügbar oder fehlerhaft -> ignore
        pass

    # 3) Fallback: einfachen summary aus Dateiname
    result["summary"] = os.path.basename(path).replace("_", " ").replace("-", " ")
    return result

def _format_time2mmss(sekunden: float) -> str:
    """
    Formatiert eine Gleitkommazahl, die Sekunden darstellt,
    in den String mm:ss.

    Args:
        sekunden (float): Die Gesamtanzahl der Sekunden.

    Returns:
        str: Der formatierte Zeit-String im Format 'mm:ss'.
    """
    # Berechnet die Minuten (ganzzahlig) und die verbleibenden Sekunden (float)
    ganz_minuten, rest_sekunden_float = divmod(sekunden, 60)
    ganz_sekunden = int(round(rest_sekunden_float))

    # Optional: Korrektur, falls die Rundung auf 60 Sekunden führt
    if ganz_sekunden == 60:
        ganz_minuten += 1
        ganz_sekunden = 0

    formatted_time = f"{int(ganz_minuten):02d}:{ganz_sekunden:02d}"

    return formatted_time
