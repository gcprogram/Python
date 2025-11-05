import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import requests
import math
import dbutil

########################################################
# Imports multiple GPX files
########################################################

def import_gpx_tracks(db_path, gpx_file_paths):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for file_path in gpx_file_paths:
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            ns = {'': 'http://www.topografix.com/GPX/1/1'}
            ET.register_namespace('', ns[''])

            track_name = os.path.basename(file_path)
            cursor.execute("INSERT INTO tracks (name) VALUES (?)", (track_name,))
            track_id = cursor.lastrowid

            for seg_index, trkseg in enumerate(root.findall('.//{http://www.topografix.com/GPX/1/1}trkseg')):
                for pt_index, trkpt in enumerate(trkseg.findall('{http://www.topografix.com/GPX/1/1}trkpt')):
                    lat = float(trkpt.get('lat'))
                    lon = float(trkpt.get('lon'))
                    ele_elem = trkpt.find('{http://www.topografix.com/GPX/1/1}ele')
                    time_elem = trkpt.find('{http://www.topografix.com/GPX/1/1}time')
                    ele = float(ele_elem.text) if ele_elem is not None else None
                    time = time_elem.text if time_elem is not None else None
                    cursor.execute("""
                        INSERT INTO trackpoints (track_id, segment_index, point_index, lat, lon, ele, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (track_id, seg_index, pt_index, lat, lon, ele, time))

        except Exception as e:
            print(f"Fehler beim Importieren der Datei {file_path}: {e}")

    conn.commit()
    conn.close()

########################################################
# Writes a track from photos into the database
#   format gap_segment_time "hh:mm:ss"
########################################################

def photos2track(db_path, gap_segment_time, progress_callback=None, log_callback=None):

    photos = dbutil.read_photo_pos_time(db_path)

    if not photos:
        return

    gap = timedelta(seconds=sum(x * int(t) for x, t in zip([3600, 60, 1], gap_segment_time.split(":"))))

    start_time = datetime.fromisoformat(photos[0][3])
    end_time = datetime.fromisoformat(photos[-1][3])
    track_name = f"photos {start_time.strftime('%Y-%m-%d %H:%M:%S')} - {end_time.strftime('%Y-%m-%d %H:%M:%S')}"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tracks (name) VALUES (?)", (track_name,))
    track_id = cursor.lastrowid

    segment_index = 0
    point_index = 0
    last_time = datetime.fromisoformat(photos[0][3])

    for filename, lat, lon, timestamp in photos:
        current_time = datetime.fromisoformat(timestamp)
        if current_time - last_time > gap:
            segment_index += 1
            point_index = 0
        cursor.execute("""
            INSERT INTO trackpoints (track_id, segment_index, point_index, lat, lon, ele, timestamp)
            VALUES (?, ?, ?, ?, ?, NULL, ?)
        """, (track_id, segment_index, point_index, lat, lon, timestamp))
        point_index += 1
        last_time = current_time

    log_callback(f"✔️ Foto Positionen in Track mit {segment_index} Segmenten konvertiert. Trennung ab {gap_segment_time}.")
    conn.commit()
    conn.close()

# Gemini

def export_tracks_to_gpx(db_path, output_path, log_callback=None):
    """
    Exportiert alle Tracks aus der Datenbank in eine einzelne GPX-Datei.

    Args:
        db_path (str): Pfad zur SQLite-Datenbank.
        output_path (str): Pfad zur zu erstellenden GPX-Datei.
        log_callback (callable, optional): Funktion zum Loggen von Nachrichten.

    Returns:
        bool: True bei Erfolg, False bei einem Fehler.
    """

    def log(msg):
        """Hilfsfunktion zum Loggen."""
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    conn = None
    try:
        log(f"ℹ️ Starte GPX-Track-Export nach: {output_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. Alle Tracks aus der Datenbank holen
        cursor.execute("SELECT track_id, name FROM tracks ORDER BY track_id")
        tracks_data = cursor.fetchall()

        if not tracks_data:
            log("⚠️ Keine Tracks in der Datenbank zum Exportieren gefunden.")
            return False

        # 2. GPX-Wurzelelement erstellen (GPX 1.1 Standard)
        #    Wir fügen Namespaces hinzu, um eine valide GPX 1.1 Datei zu erzeugen.
        gpx_attrib = {
            "version": "1.1",
            "creator": "GC_Photo_Mapper",
            "xmlns": "http://www.topografix.com/GPX/1/1",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd"
        }
        gpx = ET.Element("gpx", attrib=gpx_attrib)
        # Registriert den Namespace, um 'ns0:' Präfixe zu vermeiden
        ET.register_namespace('', "http://www.topografix.com/GPX/1/1")

        # 3. Metadaten hinzufügen (optional, aber gut für die Validität)
        metadata = ET.SubElement(gpx, "metadata")
        time_meta = ET.SubElement(metadata, "time")
        time_meta.text = datetime.utcnow().isoformat() + "Z"
        bounds_meta = ET.SubElement(metadata, "bounds") # Wird später gefüllt (optional)

        min_lat, max_lat, min_lon, max_lon = 90.0, -90.0, 180.0, -180.0
        has_bounds = False

        # 4. Jeden Track durchgehen und zur GPX-Struktur hinzufügen
        for track_id, track_name in tracks_data:
            log(f"  -> Exportiere Track '{track_name}' (ID: {track_id})")

            # Punkte für den aktuellen Track holen, *geordnet* nach Segment und Punkt!
            cursor.execute(
                """SELECT segment_index, lat, lon, ele, timestamp
                   FROM trackpoints
                   WHERE track_id = ?
                   ORDER BY segment_index, point_index""",
                (track_id,)
            )
            points_data = cursor.fetchall()

            if not points_data:
                log(f"    ⚠️ Track '{track_name}' hat keine Punkte, wird übersprungen.")
                continue

            # 4a. <trk>-Element erstellen
            trk = ET.SubElement(gpx, "trk")
            name_elem = ET.SubElement(trk, "name")
            name_elem.text = track_name if track_name else f"Track {track_id}"

            # 4b. Segmente und Punkte verarbeiten
            current_segment_index = -1
            trkseg = None

            for seg_idx, lat, lon, ele, timestamp in points_data:
                # Grenzen aktualisieren
                min_lat = min(min_lat, lat)
                max_lat = max(max_lat, lat)
                min_lon = min(min_lon, lon)
                max_lon = max(max_lon, lon)
                has_bounds = True

                # Prüfen, ob ein neues Segment beginnt
                if seg_idx != current_segment_index:
                    trkseg = ET.SubElement(trk, "trkseg")
                    current_segment_index = seg_idx

                # <trkpt>-Element erstellen
                trkpt = ET.SubElement(trkseg, "trkpt", lat=str(lat), lon=str(lon))

                # Optionale Elemente hinzufügen
                if ele is not None:
                    ele_elem = ET.SubElement(trkpt, "ele")
                    ele_elem.text = str(ele)

                if timestamp:
                    time_elem = ET.SubElement(trkpt, "time")
                    # Sicherstellen, dass der Zeitstempel im ISO-Format mit 'Z' (UTC) ist,
                    # wenn keine Zeitzoneninfo vorhanden ist, da GPX dies erwartet.
                    ts_text = timestamp.strip()
                    if 'T' in ts_text and not (ts_text.endswith('Z') or '+' in ts_text[10:] or '-' in ts_text[10:]):
                         ts_text += "Z"
                    time_elem.text = ts_text


        # 5. Bounds-Metadaten setzen, falls Punkte vorhanden waren
        if has_bounds:
             bounds_meta.set("minlat", str(min_lat))
             bounds_meta.set("maxlat", str(max_lat))
             bounds_meta.set("minlon", str(min_lon))
             bounds_meta.set("maxlon", str(max_lon))
        else:
            gpx.remove(metadata) # Keine Punkte -> keine Metadaten nötig

        # 6. Den XML-Baum in eine Datei schreiben
        tree = ET.ElementTree(gpx)
        # 'indent' ist in neueren Python-Versionen verfügbar und formatiert die XML-Datei lesbar.
        # Wenn Sie Python < 3.9 verwenden, müssen Sie es evtl. entfernen oder eine andere Methode nutzen.
        try:
            tree.write(output_path, encoding="utf-8", xml_declaration=True) # Grundversion
            # Versuch mit Einrückung für Lesbarkeit (kann bei älterem Python fehlschlagen)
            # ET.indent(tree, space="\t", level=0)
            # tree.write(output_path, encoding="utf-8", xml_declaration=True)

        except TypeError:
            # Fallback, falls ET.indent nicht verfügbar ist oder Probleme macht
            tree.write(output_path, encoding="utf-8", xml_declaration=True)

        log(f"✔️ GPX-Export erfolgreich nach {output_path} geschrieben.")
        return True

    except sqlite3.Error as e:
        log(f"❌ Datenbankfehler beim GPX-Export: {e}")
        return False
    except IOError as e:
        log(f"❌ Dateifehler beim Schreiben von '{output_path}': {e}")
        return False
    except Exception as e:
        log(f"❌ Unerwarteter Fehler beim GPX-Export: {e}")
        return False
    finally:
        if conn:
            conn.close()


# Gemini

def import_gpx_tracks_gemini(db_path, file_path, progress_callback=None, log_callback=None):
    """
    Importiert Tracks aus einer GPX-Datei in die Datenbank.

    Args:
        db_path (str): Pfad zur SQLite-Datenbank.
        file_path (str): Pfad zur GPX-Datei.
        progress_callback (callable, optional): Funktion zur Fortschrittsanzeige (0-100).
        log_callback (callable, optional): Funktion zum Loggen von Nachrichten.
    """

    def log(msg):
        """Hilfsfunktion zum Loggen."""
        if log_callback:
            log_callback(msg)
        else:
            print(msg) # Fallback, falls kein Callback übergeben wird

    conn = None  # Initialisieren, damit es im finally-Block verfügbar ist
    
    try:
        log(f"ℹ️ Starte GPX-Track-Import von: {file_path}")

        # Versuche, die GPX-Datei zu parsen
        tree = ET.parse(file_path)
        root = tree.getroot()

        # GPX-Namespaces sind wichtig! Versuche, den Namespace zu finden.
        # Übliche Namespaces:
        ns_map = {
            'gpx11': 'http://www.topografix.com/GPX/1/1',
            'gpx10': 'http://www.topografix.com/GPX/1/0',
        }
        namespace = {}
        
        # Finde den Namespace des Wurzelelements
        if '}' in root.tag:
            uri = root.tag.split('}')[0][1:]
            if uri in ns_map.values():
                 # Finde den passenden Key (gpx11 oder gpx10)
                 ns_key = [k for k, v in ns_map.items() if v == uri][0]
                 namespace = {'gpx': uri}
                 log(f"ℹ️ GPX Namespace '{uri}' ({ns_key}) erkannt.")
            else:
                 log(f"⚠️ Unbekannter GPX Namespace: {uri}. Versuche Standard-Namespaces.")
                 namespace = {'gpx': ns_map['gpx11']} # Fallback auf 1.1
        else:
            log("⚠️ Kein Namespace im Wurzelelement gefunden. Versuche GPX 1.1.")
            namespace = {'gpx': ns_map['gpx11']}


        # Finde alle <trk>-Elemente
        tracks_found = root.findall('.//gpx:trk', namespace)
        
        # Wenn mit 1.1 nichts gefunden wurde, versuche 1.0 (falls nicht schon erkannt)
        if not tracks_found and namespace['gpx'] != ns_map['gpx10']:
             log("ℹ️ Kein Track mit GPX 1.1 gefunden. Versuche GPX 1.0.")
             namespace = {'gpx': ns_map['gpx10']}
             tracks_found = root.findall('.//gpx:trk', namespace)


        if not tracks_found:
            log("⚠️ Keine <trk>-Elemente in der GPX-Datei gefunden.")
            return

        total_tracks = len(tracks_found)
        log(f"ℹ️ {total_tracks} Track(s) gefunden.")

        # Datenbankverbindung herstellen
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        imported_tracks_count = 0
        total_points_count = 0

        # Iteriere durch jeden gefundenen Track
        for track_idx, trk in enumerate(tracks_found):
            track_name = trk.findtext('gpx:name', default=f"Track_{track_idx+1}", namespaces=namespace)
            import_ts = datetime.now().isoformat()
            source = os.path.basename(file_path)

            try:
                # Neuen Track in die 'tracks'-Tabelle einfügen
                cursor.execute(
                    "INSERT INTO tracks (name, source_file, import_timestamp) VALUES (?, ?, ?)",
                    (track_name, source, import_ts)
                )
                track_id = cursor.lastrowid # Die ID des gerade eingefügten Tracks holen
                log(f"  -> Importiere Track '{track_name}' (ID: {track_id})")

                segments = trk.findall('gpx:trkseg', namespace)
                track_points_count_current = 0

                # Iteriere durch jedes Segment des Tracks
                for seg_idx, trkseg in enumerate(segments):
                    points = trkseg.findall('gpx:trkpt', namespace)
                    points_to_insert = []

                    # Iteriere durch jeden Punkt des Segments
                    for pt_idx, trkpt in enumerate(points):
                        try:
                            lat = float(trkpt.attrib['lat'])
                            lon = float(trkpt.attrib['lon'])
                            
                            ele_elem = trkpt.find('gpx:ele', namespace)
                            ele = float(ele_elem.text) if ele_elem is not None and ele_elem.text else None
                            
                            time_elem = trkpt.find('gpx:time', namespace)
                            timestamp = time_elem.text if time_elem is not None else None

                            points_to_insert.append(
                                (track_id, seg_idx, pt_idx, lat, lon, ele, timestamp)
                            )
                        except (KeyError, ValueError) as e:
                            log(f"    ⚠️ Fehler bei Punkt {pt_idx} in Segment {seg_idx}: {e} - Übersprungen.")

                    # Füge alle Punkte dieses Segments auf einmal ein (effizienter)
                    if points_to_insert:
                        cursor.executemany(
                            """INSERT INTO trackpoints 
                               (track_id, segment_index, point_index, lat, lon, ele, timestamp) 
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            points_to_insert
                        )
                        track_points_count_current += len(points_to_insert)

                log(f"    -> {track_points_count_current} Punkte in {len(segments)} Segment(en) importiert.")
                total_points_count += track_points_count_current
                imported_tracks_count += 1

                # Fortschrittsanzeige aktualisieren
                if progress_callback:
                    progress_callback((track_idx + 1) / total_tracks * 100)

            except sqlite3.Error as db_err:
                log(f"❌ Datenbankfehler beim Import von Track '{track_name}': {db_err}")
                conn.rollback() # Änderungen für diesen Track rückgängig machen
            except Exception as inner_err:
                 log(f"❌ Unerwarteter Fehler beim Import von Track '{track_name}': {inner_err}")
                 conn.rollback()

        # Alle Änderungen bestätigen (committen)
        conn.commit()
        log(f"✔️ GPX-Track-Import abgeschlossen: {imported_tracks_count} Tracks mit {total_points_count} Punkten importiert.")

    except ET.ParseError as e:
        log(f"❌ Fehler beim Parsen der GPX-Datei '{file_path}': {e}")
        if conn: conn.rollback()
    except sqlite3.Error as e:
        log(f"❌ Datenbankfehler: {e}")
        if conn: conn.rollback()
    except FileNotFoundError:
        log(f"❌ GPX-Datei nicht gefunden: {file_path}")
    except Exception as e:
        log(f"❌ Unerwarteter Fehler beim GPX-Import: {e}")
        if conn: conn.rollback()
    finally:
        # Datenbankverbindung sicher schließen
        if conn:
            conn.close()
            
 
########################################################
# Helper function calcuates distance in [m] for 2 pos
########################################################
def haversine2(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

########################################################
# Calculate profile car, bike, or foot from 
# velocity. 
########################################################
 
def estimate_profile(distance_km, duration_h):
    if duration_h == 0:
        return "foot"  # fallback
    speed_kmh = distance_km / duration_h
    if speed_kmh < 6:
        return "foot"
    elif speed_kmh < 25:
        return "bike"
    else:
        return "car"

########################################################
# Uses Graphhopper to calcuate a route.
########################################################

def request_route(profile, p1, p2, server_url="http://localhost:8989"):
    url = f"{server_url}/route"
    params = {
        "point": [f"{p1[0]},{p1[1]}", f"{p2[0]},{p2[1]}"],
        "profile": profile,
        "points_encoded": False,
        "instructions": False,
        "locale": "de"
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    return r.json()

def route_photo_sequence(db_path):
    photos = dbutil.get_photo_pos_time(db_path)
   
    if not photos or len(photos) < 2:
        print("Nicht genug Fotos mit GPS und Zeitstempel.")
        return

    for i in range(len(photos) - 1):
        file1, lat1, lon1, ts1 = photos[i]
        file2, lat2, lon2, ts2 = photos[i+1]
        t1 = datetime.fromisoformat(ts1)
        t2 = datetime.fromisoformat(ts2)
        delta_h = (t2 - t1).total_seconds() / 3600
        distance = haversine2(lat1, lon1, lat2, lon2)
        if distance > 60:
            profile = estimate_profile(distance/1000.0, delta_h)
            print(f"Foto {i} → {i+1}: {distance:.0f} m in {delta_h:.2f} h → {profile}")
            try:
                if profile == "car":
                    route = request_route(profile, (lat1, lon1), (lat2, lon2))
                    coords = route['paths'][0]['points']['coordinates']
                    print(f"→ Route mit {len(coords)} Punkten erhalten.")
                else:
                    print("  Graphhopper unable to calc foot route")
            except Exception as e:
                print(f"❌ Fehler bei Routing {i}-{i+1}: {e}")
        else:
            print(f"Foto [i] → {i+1}: {distance:.0f} m skip routing because of low distance.")