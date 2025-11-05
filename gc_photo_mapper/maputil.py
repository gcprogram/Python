import os
import re
import numpy as np
from sklearn.neighbors import BallTree
import folium
from folium.plugins import MarkerCluster
from folium import PolyLine
from io import BytesIO
import base64
import math
import dbutil

########################################################
# Hilfsfunktion: Abstand zwischen zwei Koordinaten-
# punkten berechnen.
########################################################

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


########################################################
# Mapping der Photos zu einem Geocache (GCCODE)
########################################################

def map2gccode(db_path, max_distance, log_callback=None):
    
    photos = dbutil.read_photo_name_pos(db_path)
    caches = dbutil.read_geocaches_pos(db_path)
    count = 0
    for filename, plat, plon in photos:
        best_gc = None
        best_dist = max_distance
        for gc_code, clat, clon in caches:
            dist = haversine(plat, plon, clat, clon)
            if dist <= best_dist:
                best_gc = gc_code
                best_dist = dist
        if best_gc:
            dbutil.write_photo_gccode(db_path, filename, best_gc, best_dist)
            count += 1

    if log_callback:
        log_callback(f"✔️ Mapping abgeschlossen: {count} Fotos zu Geocaches zugeordnet im Radius {max_distance} m.")

########################################################
# Mapping der Photos zu einem Geocache (GCCODE)
# Performante Version. Zählt außerdem die Anzahl der
# verschiedenen zugeordneten Geocaches.
#
# Mappt Fotos performant zu Geocaches mittels eines 
# BallTree für eine schnelle "Nächste Nachbarn"-Suche.
# 
# Returns mapped_photo_count, found_caches
########################################################

def map2gccode_performant(db_path, max_distance, log_callback=None):
    photos = dbutil.read_photo_name_pos(db_path) # -> [(name, lat, lon), ...]
    caches_data = dbutil.read_geocaches_pos(db_path) # -> [(gcode, lat, lon), ...]

    if not photos or not caches_data:
        if log_callback:
            log_callback("Keine Fotos oder Caches zum Verarbeiten gefunden.")
        return 0, 0
    
    # Trennen der Cache-Daten für die Verarbeitung
    cache_codes = [c[0] for c in caches_data]
    # Koordinaten müssen für den BallTree in Radiant umgerechnet werden
    caches_coords_rad = np.radians([(c[1], c[2]) for c in caches_data])

    # 1. Einen BallTree aus den Geocache-Koordinaten erstellen.
    # Dies ist ein einmaliger Aufwand.
    tree = BallTree(caches_coords_rad, metric='haversine')

    if log_callback:
        log_callback(f"Starte optimiertes Mapping für {len(photos)} Fotos...")

    mapped_photos_count = 0
    assigned_gccodes = set()

    # Koordinaten aller Fotos auf einmal vorbereiten
    photos_coords = [(p[1], p[2]) for p in photos]
    photos_coords_rad = np.radians(photos_coords)

    # 2. Den Baum für alle Fotos auf einmal abfragen.
    # `query_radius` findet für jeden Punkt alle Nachbarn innerhalb der Distanz.
    # Die Distanz muss in Radiant angegeben werden (Erdradius ca. 6371 km).
    max_dist_rad = max_distance / 6371.0
    
    # `indices` ist eine Liste von Listen, z.B. [[5, 12], [8], [], [23, 42]]
    # Jede innere Liste enthält die Indizes der Caches im Radius des jeweiligen Fotos.
    indices = tree.query_radius(photos_coords_rad, r=max_dist_rad, return_distance=False)

    # 3. Ergebnisse verarbeiten
    for i, photo_indices in enumerate(indices):
        if not photo_indices.any(): # Prüfen, ob Caches gefunden wurden
            continue

        # Wenn mehrere Caches im Radius sind, den nächstgelegenen finden.
        # `query` findet den 1 nächsten Nachbarn.
        dist, nearest_idx = tree.query(photos_coords_rad[i:i+1], k=1)
        
        # Index und Distanz aus den Ergebnis-Arrays extrahieren
        best_gc_index = nearest_idx[0][0]
        best_dist_km = dist[0][0] * 6371.0 # Distanz zurück in km umrechnen

        best_gc = cache_codes[best_gc_index]
        filename = photos[i][0]
        
        dbutil.write_photo_gccode(db_path, filename, best_gc, best_dist_km)
        mapped_photos_count += 1
        assigned_gccodes.add(best_gc)

    unique_geocache_count = len(assigned_gccodes)

    if log_callback:
        log_callback(f"Fertig: Mapped Fotos(GC)={mapped_photos_count}, Mapped Caches={unique_geocache_count}")


    return mapped_photos_count, unique_geocache_count
    
########################################################
# Mapping der Photos zu einem Geocache (GCCODE) und
# umbenennen der Photos mit Postfix GCCODE.
#
#   Benennt Fotodateien um, indem ein Geocache-Code (GCCODE) hinzugefügt,
#   aktualisiert oder entfernt wird.
#    Die Funktion verarbeitet eine Liste von (Dateiname, GCCODE)-Tupeln.
#   - Wenn ein GCCODE vorhanden ist, wird er dem Dateinamen (vor der Endung)
#     hinzugefügt. Ein eventuell bereits vorhandener GCCODE wird dabei ersetzt.
#   - Wenn der GCCODE `None` oder leer ist, wird ein eventuell im Dateinamen
#     vorhandener GCCODE entfernt.
#   - Existiert die Quelldatei nicht, wird eine Warnung ausgegeben.
########################################################

def rename_photos_gccode(db_path):

    try:
        photos = dbutil.read_photo_gccode(db_path)
    except NameError:
        print("Fehler: Die Funktion 'read_photo_with_gccode' ist nicht definiert.")
        # Zu Demonstrationszwecken wird hier eine Beispielliste erstellt
        photos = [
            ('c:\\temp\\20250614_1234.jpg', 'GCA12345'),           # Fall 1: GCCODE hinzufügen
            ('c:\\temp\\photo_alt_GC11111.jpg', 'GC22222'),        # Fall 2: GCCODE ersetzen
            ('c:\\temp\\bild_zum_loeschen_GC99999.jpg', None),     # Fall 3: GCCODE entfernen (mit None)
            ('c:\\temp\\noch_ein_bild_GC88888.jpg', ''),           # Fall 4: GCCODE entfernen (mit leerem String)
            ('c:\\temp\\unveraendert.jpg', None),                  # Fall 5: Keine Änderung nötig
        ]

    # Regex, um einen GCCODE am Ende eines Dateinamens (vor der Endung) zu finden.
    # Beispiel: In "foto_GCA12345.jpg" wird "_GCA12345" gefunden.
    gccode_pattern = re.compile(r'_GC[A-Z0-9]+$')

    renamed_count = 0
    for original_path, gccode in photos:
        try:
            # 1. Prüfen, ob die Datei überhaupt existiert
            if not os.path.isfile(original_path):
                print(f"Warnung: Datei nicht gefunden, übersprungen: '{original_path}'")
                continue

            # 2. Pfad und Dateinamen aufteilen
            directory, filename_with_ext = os.path.split(original_path)
            basename, extension = os.path.splitext(filename_with_ext)

            # 3. Vorhandenen GCCODE aus dem Dateinamen entfernen
            # re.sub() entfernt den Teil, falls er existiert, ansonsten bleibt der String unverändert.
            base_clean = gccode_pattern.sub('', basename)

            # 4. Neuen Dateinamen basierend auf dem GCCODE erstellen
            if gccode:  # True für alle nicht-leeren Strings
                # Neuen GCCODE an den bereinigten Namen anhängen
                new_basename = f"{base_clean}_{gccode}"
            else:
                # Wenn der GCCODE None oder leer ist, wird nur der bereinigte Name verwendet
                new_basename = base_clean

            # 5. Umbenennung durchführen, falls sich der Name geändert hat
            if new_basename != basename:
                new_path = os.path.join(directory, new_basename + extension)
                print(f"Umbenennung: '{original_path}' -> '{new_path}'")
                os.rename(original_path, new_path)
                dbutil.update_photo_filename(db_path, original_path, new_path)
                renamed_count += 1
            else:
                print(f"Info: Keine Umbenennung für '{original_path}' notwendig.")

        except Exception as e:
            print(f"Fehler beim Verarbeiten von '{original_path}': {e}")
    
    print(f"\nVerarbeitung abgeschlossen. {renamed_count} Datei(en) wurden umbenannt.")


########################################################
# Add thumbnails from DB to map
########################################################

def map_photos(db_path, m, time_min, time_max, self, progress_callback=None, log_callback=None):
    # now read again from DB
    rows = dbutil.read_photo_full(db_path, time_min, time_max)
    if not rows:
        return None
    cluster = MarkerCluster().add_to(m)
    #

    total = len(rows)
    idx = 0
    for filepath, lat, lon, gc_code, width, height, thumbimg in rows:
        if (not os.path.exists(filepath)) and thumbimg is None:
            continue
        filename = os.path.basename(filepath)
        try:
            buffer = BytesIO(thumbimg)
            encoded_string = base64.b64encode(buffer.getvalue()).decode("utf-8")
            url = f"data:image/jpeg;base64,{encoded_string}"
            tooltip_html = filename
            if gc_code is not None:
                tooltip_html = f"{gc_code}:<br/>{filename}"
                #print(f"gc_code for alt {alt}")
            if width >= height:
                icon_html = f"<img src='{url}' style='width:50px; height:auto;'>"
            else:
                icon_html = f"<img src='{url}' style='height:50px; width:auto;'>"
            popup_html = f"<img src='{url}'>"
            folium.Marker(
                location=[lat, lon], 
                icon=folium.DivIcon(html=icon_html),
                tooltip=tooltip_html,
                popup=popup_html).add_to(cluster)
 
        except Exception as e:
            log_callback(f"⚠️ {filename}: Fehler beim Schreiben der Map: {e}")

        idx += 1;
        if progress_callback:
            progress_callback(idx/ total * 100)


########################################################
# Adds the Cache icons to the map.
# Fügt base64-bildbasierte Icons aus der Tabelle 'icons' 
# je nach Cache-Typ auf die Karte (ohne Popup).
########################################################

def map_gc_icons(db_path, m):
    icon_dict = dbutil.read_icons(db_path)
    geocaches = dbutil.read_geocaches(db_path)

    for gc_code, _, lat, lon, cache_type in geocaches:
        icon_dataurl = icon_dict.get(cache_type)
        if not icon_dataurl:
            continue  # überspringe, falls kein passendes Icon
        icon_html = f"<img src='{icon_dataurl}' style='width:20px; height:auto;'>"
        folium.Marker(
            location=(lat, lon),
            icon=folium.DivIcon(html=icon_html),
            icon_size=(20, 20),
            tooltip=gc_code
        ).add_to(m)
        
########################################################
# Adds a tracks to the map.
# Multiple tracks are seperated.
# Multiple segments with a track are draw with a dashed line.
# Points within same segment are connected with a line.
########################################################

def map_tracks(db_path, m, track_ids):

    for track_id in track_ids:
        rows = dbutil.read_track(db_path, track_id)

        if not rows:
            continue
            
        segments = {}
        for seg, lat, lon in rows:
            segments.setdefault(seg, []).append((lat, lon))

        previous_last_point = None

        for seg_index in sorted(segments):
            points = segments[seg_index]

            # Segmentlinie (durchgezogen)
            PolyLine(points, color='blue', weight=3, opacity=0.8).add_to(m)

            # Verbindungslinie zum vorherigen Segment (gestrichelt)
            if previous_last_point:
                PolyLine(
                    [previous_last_point, points[0]],
                    color='gray', weight=2, opacity=0.5,
                    dash_array='5,5'
                ).add_to(m)

            previous_last_point = points[-1]


########################################################
# Creates HTML file for map with 
# photos, track and geocache icons
########################################################
                
def generate_map(self):

    # Benutzerdefinierten zusätzlicher CSS-Code für randloses Popup
    # Dieser Code macht den Popup-Container komplett transparent und entfernt alle Abstände.
    custom_css = """
<style>
.leaflet-popup-content-wrapper {
    background: transparent;
    border: none;
    box-shadow: none;
}
.leaflet-popup-content {
    margin: 0 !important;
    padding: 0 !important;
}
</style>
"""

    time_min = self.tk_time_min.get()
    time_max = self.tk_time_max.get()
    self.source_dir = dbutil.get_photo_source_dir(self.db_path, time_min, time_max)
    html_path = os.path.join(self.source_dir, "photo_map.html")

    # read min and max lat and lon coordinates
    bounds = dbutil.get_photo_bounding_box(self.db_path, time_min, time_max)
    if not bounds:
        return None  

    if self.zoom < 0:
        m = folium.Map()
        m.fit_bounds(bounds)
    else:
        m = folium.Map(location=bounds[0],zoom_start = self.zoom)
   
    # 2. CSS-Code zum <head> der HTML-Datei hinzu injezieren
    m.get_root().header.add_child(folium.Element(custom_css))
   
    if self.show_photos:
        map_photos(self.db_path, m, time_min, time_max, self, self.update_progress, self.log_message)
    if self.show_track:
        map_tracks(self.db_path, m, self.tk_track_ids.get())
    if self.show_geocaches:
        map_gc_icons(self.db_path, m)
    m.save(html_path)
    return html_path
