import os
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
import tempfile

########################################################
# Read GPX file to database
########################################################

def import_gpx_with_progress(file_path, db_path, progress_callback=None, log_callback=None):
    def is_gpx_with_caches(gpx_path):
        try:
            tree = ET.parse(gpx_path)
            root = tree.getroot()
            namespace = {
                'gpx': 'http://www.topografix.com/GPX/1/0',
                'groundspeak': 'http://www.groundspeak.com/cache/1/0/1'
            }
            for wpt in root.findall("gpx:wpt", namespace):
                if wpt.find('groundspeak:cache', namespace) is not None:
                    return True
            return False
        except Exception:
            return False

    # Wenn ZIP-Datei: zuerst entpacken und geeignete GPX finden
    if zipfile.is_zipfile(file_path):
        with zipfile.ZipFile(file_path, 'r') as zipf:
            tempdir = tempfile.mkdtemp()
            gpx_files = [name for name in zipf.namelist() if name.lower().endswith('.gpx')]
            zipf.extractall(tempdir)
            for gpx in gpx_files:
                full_path = os.path.join(tempdir, gpx)
                if is_gpx_with_caches(full_path):
                    import_gpx_with_progress(full_path, db_path, progress_callback, log_callback)
                    return
            if log_callback:
                log_callback("⚠️ Keine geeignete GPX-Datei mit Geocaches im ZIP-Archiv gefunden.")
        return

    # GPX-Datei wie gehabt verarbeiten
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    namespace = {
        'gpx': 'http://www.topografix.com/GPX/1/0',
        'groundspeak': 'http://www.groundspeak.com/cache/1/0/1'
    }

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        waypoints = root.findall("gpx:wpt", namespace)
        total = len(waypoints)
        count = 0

        for idx, wpt in enumerate(waypoints):
            lat = float(wpt.attrib['lat'])
            lon = float(wpt.attrib['lon'])
            gccode = wpt.findtext('gpx:name', default='', namespaces=namespace)
            cache = wpt.find('groundspeak:cache', namespace)
            if cache is None:
                continue

            name = cache.findtext('groundspeak:name', default='', namespaces=namespace)
            data = {
                'gc_code': gccode,
                'name': name,
                'available': 1 if cache.attrib.get('available') == 'True' else 0,
                'archived': 1 if cache.attrib.get('archived') == 'True' else 0,
                'difficulty': float(cache.findtext('groundspeak:difficulty', default='0', namespaces=namespace)),
                'terrain': float(cache.findtext('groundspeak:terrain', default='0', namespaces=namespace)),
                'container': cache.findtext('groundspeak:container', default='', namespaces=namespace),
                'type': cache.findtext('groundspeak:type', default='', namespaces=namespace),
                'placed_by': cache.findtext('groundspeak:placed_by', default='', namespaces=namespace),
                'country': cache.findtext('groundspeak:country', default='', namespaces=namespace),
                'state': cache.findtext('groundspeak:state', default='', namespaces=namespace),
                'lat': lat,
                'lon': lon
            }

            cursor.execute('''
                INSERT OR REPLACE INTO geocaches (gc_code, name, lat, lon, available, archived, difficulty, terrain, container, type, placed_by, country, state)
                VALUES (:gc_code, :name, :lat, :lon, :available, :archived, :difficulty, :terrain, :container, :type, :placed_by, :country, :state)
            ''', data)

            count += 1
            if progress_callback:
                progress_callback(idx / total * 100)

        conn.commit()
        if log_callback:
            log_callback(f"✔️ GPX-Import abgeschlossen ({count} Geocaches importiert).")
    except Exception as e:
        if log_callback:
            log_callback(f"❌ Fehler beim GPX-Import: {e}")
    finally:
        conn.close()
