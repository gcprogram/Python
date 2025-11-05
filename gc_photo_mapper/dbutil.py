import os
import sqlite3

########################################################
# Datenbankinitialisierung
#   - geocaches
#   - photos
#   - tracks
#   - trackpoints
############################ääääääääääääääääääääääääääää
DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS geocaches (
    gc_code TEXT PRIMARY KEY,
    name TEXT,
    lat REAL,
    lon REAL,
    available INTEGER,
    archived INTEGER,
    difficulty REAL,
    terrain REAL,
    container TEXT,
    type TEXT,
    placed_by TEXT,
    country TEXT,
    state TEXT
);

CREATE TABLE IF NOT EXISTS photos (
    filename TEXT PRIMARY KEY,
    lat REAL,
    lon REAL,
    timestamp TEXT,
    gc_code TEXT,
    distance REAL,
    width INTEGER,
    height INTEGER,
    thumbnail BLOB
   
);

CREATE TABLE IF NOT EXISTS tracks (
    track_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    source_file TEXT,
    import_timestamp TEXT
);

CREATE TABLE IF NOT EXISTS trackpoints (
    point_id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    segment_index INTEGER NOT NULL,
    point_index INTEGER NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    ele REAL,
    timestamp TEXT,
    FOREIGN KEY(track_id) REFERENCES tracks(track_id) ON DELETE CASCADE,
    UNIQUE(track_id, segment_index, point_index)
);

CREATE TABLE IF NOT EXISTS icons (
    filename TEXT PRIMARY KEY,
    type TEXT,
    dataurl BLOB
);
"""

########################################################
# Create database
########################################################

def initialize_database(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(DB_SCHEMA)
    conn.commit()
    conn.close()

########################################################
# Delete all geocaches from database
########################################################

def clear_geocaches(self):
    conn = sqlite3.connect(self.db_path)
    conn.execute("DELETE FROM geocaches")
    conn.commit()
    conn.close()

########################################################
# Delete all photos from database.
# Better drop and re-create
########################################################

def clear_photos(self):
    conn = sqlite3.connect(self.db_path)
    conn.execute("DROP TABLE photos")
    conn.commit()
    conn.close()
    initialize_database(self.db_path)

########################################################
# Delete specific track from database
########################################################

def clear_track(self,track):
    conn = sqlite3.connect(self.db_path)
    conn.execute("DELETE FROM trackpoints WHERE track_id = ?", (track,))
    conn.execute("DELETE FROM tracks WHERE track_id = ?", (track,))
    conn.commit()
    conn.close()

########################################################
# Delete all track from database and reset track_id to 0
########################################################

def clear_tracks(self):
    conn = sqlite3.connect(self.db_path)
    conn.execute("DROP TABLE trackpoints")
    conn.execute("DROP TABLE tracks")
    conn.commit()
    conn.close()
    initialize_database(self.db_path)
    
########################################################
# Delete all cache icons in database
########################################################

def clear_icons(self):
    conn = sqlite3.connect(self.db_path)
    conn.execute("DELETE FROM icons")
    conn.commit()
    conn.close()

########################################################
# Get number of icons in database
########################################################

def get_number_icons(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Lese alle Icons vorab in ein Dictionary {type: dataurl}
    cursor.execute("SELECT count(type) FROM icons")
    rows = cursor.fetchone()
    conn.close()

    if not rows:
        return 0
    return rows[0]

########################################################
# Read all cache icons from database
########################################################

def read_icons(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Lese alle Icons vorab in ein Dictionary {type: dataurl}
    cursor.execute("SELECT type, dataurl FROM icons")
    icon_dict = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return icon_dict
 
########################################################
# Writes all cache icons to database
########################################################

def write_icons(db_path, filename, type_label, dataurl): 
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO icons (filename, type, dataurl)
        VALUES (?, ?, ?)
        """, (filename, type_label, dataurl))
    conn.commit()
    conn.close()

########################################################
# Returns number of Photos in the database.
########################################################

def get_number_photos(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM photos")
    rows = cursor.fetchone()
    conn.close()

    if not rows:
        return 0
    return rows[0]

########################################################
########################################################
def get_photo_source_dir(db_path, time_min, time_max):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM photos WHERE lat IS NOT NULL AND lon IS NOT NULL AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp", (time_min, time_max,))
    rows = cursor.fetchone()
    conn.close()
    if not rows:
        return None

    # Verwende Verzeichnis des ersten Fotos als Basis
    first_photo_path = rows[0][0]
    source_dir = os.path.dirname(os.path.abspath(first_photo_path)) or os.getcwd()
    return source_dir

########################################################
# Read count, time_min and time_max in photos table
########################################################
def get_photos_tmin_tmax(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT count(timestamp),min(timestamp),max(timestamp) FROM photos WHERE lat IS NOT NULL AND lon IS NOT NULL AND timestamp IS NOT NULL")
    rows = cursor.fetchone()
    conn.close()

    if not rows:
        return (0,"1970-01-01T00:00:00","9999-12-31T23:59:59")
    return rows[0],rows[1],rows[2]

########################################################
# Get bounding box for all photos
# [ [lat_min, lon_min], {lat_max, lon_max] ]
########################################################

def get_photo_bounding_box(db_path, time_min, time_max):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT min(lat), min(lon), max(lat), max(lon) FROM photos WHERE lat IS NOT NULL AND lon IS NOT NULL AND timestamp IS NOT NULL AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp", (time_min, time_max))
    row = cursor.fetchall()
    conn.close()
    if not row:
        return None
    return [ [row[0][0], row[0][1]] , [row[0][2], row[0][3] ] ];

########################################################
# Reads all photos with position and time
# Returns array of filename,lat,lon,timestamp
########################################################

def read_photo_pos_time(db_path, time_min, time_max):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT filename, lat, lon, timestamp FROM photos WHERE lat IS NOT NULL AND lon IS NOT NULL AND timestamp IS NOT NULL AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp", (time_min, time_max))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return None
    return rows;

########################################################
# Reads all photos with all attributes
# Returns array of filename,lat,lon,timestamp
########################################################

def read_photo_full(db_path, time_min, time_max):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT filename, lat, lon, gc_code, width, height, thumbnail FROM photos WHERE lat IS NOT NULL AND lon IS NOT NULL and timestamp >= ? and timestamp <= ?", (time_min, time_max))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return None
    return rows

########################################################
# Reads all photos where thumbnail have not been 
# generated
########################################################

def read_photo_without_thumbnail(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # create thumbnails only when not created
    cursor.execute("SELECT filename, thumbnail FROM photos WHERE lat IS NOT NULL AND lon IS NOT NULL AND thumbnail IS NULL")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return None
    return rows

########################################################
# Reads all photos with name and position 
# generated
########################################################

def read_photo_name_pos(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # create thumbnails only when not created
    cursor.execute("SELECT filename, lat, lon FROM photos WHERE lat IS NOT NULL AND lon IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return None
    return rows

########################################################
# Reads all photos
# Returns list with [filename, gccode]
########################################################

def read_photo_gccode(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # create thumbnails only when not created
    cursor.execute("SELECT filename, gc_code FROM photos")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return None
    return rows

########################################################
# writesgccode to photos
########################################################

def write_photo_gccode(db_path, filename, best_gc, best_dist):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
                UPDATE photos SET gc_code = ?, distance = ? WHERE filename = ?
            """, (best_gc, best_dist, filename))
    conn.commit()
    conn.close()    

########################################################
# Writes thumbnail 
########################################################

def write_photo_thumbnail(db_path, filepath, w, h, buffer):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE photos SET thumbnail = ?, width = ?, height = ? WHERE filename = ?", ( sqlite3.Binary(buffer), w, h, filepath))
    conn.commit()
    conn.close()


########################################################
# Update filename:
# filename may change due to GCCODE renaming.
########################################################

def update_photo_filename(db_path, new_filepath, old_filepath):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE photos SET filename = ? WHERE filename = ?", ( new_filepath, old_filepath))
    conn.commit()
    conn.close()
    
########################################################
# Reads number of Geocaches (WPT) in the database
# Returns integer
########################################################

def get_number_geocaches(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM geocaches")
    rows = cursor.fetchone()
    conn.close()

    if not rows:
        return 0
    return rows[0]


########################################################
# Reads Geocaches from the database with all attributes
# necessary for the map
########################################################

def read_geocaches(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT gc_code, name, lat, lon, type FROM geocaches WHERE lat IS NOT NULL AND lon IS NOT NULL")
    geocaches = cursor.fetchall()
    conn.close()
    if not geocaches:
        return None
    return geocaches

def read_geocaches_pos(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT gc_code, lat, lon FROM geocaches WHERE lat IS NOT NULL AND lon IS NOT NULL")
    geocaches = cursor.fetchall()
    conn.close()
    if not geocaches:
        return None
    return geocaches


def get_geocaches_col_names(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT gc_code, name, lat, lon, type FROM geocaches WHERE lat IS NOT NULL AND lon IS NOT NULL")
    cursor.fetchone()
    col_names = [d[0] for d in cursor.description]
    conn.close()
    if not col_names:
        return None
    return col_names


########################################################
# Reads all Geocaches from the database
########################################################

def read_geocaches_full(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM geocaches WHERE lat IS NOT NULL AND lon IS NOT NULL")
    geocaches = cursor.fetchall()
    conn.close()
    if not geocaches:
        return None
    return geocaches


########################################################
# Reads all Photo-mapped Geocaches with time of 
# minimal distance
#
# Ruft alle Fotos ab, die einem Geocache zugeordnet sind, und verbindet sie
# mit den entsprechenden Cache-Details für die Anzeige.
#
# Gibt eine Liste von Tupeln zurück, wobei jedes Tupel eine Zeile in der
# Tabelle repräsentiert.
#
# Spalten: Zeit, Abstand, GC-Code, Cache-Name, Cache-Typ
########################################################

def fetch_mapped_photos_for_display(db_path):
    query = """
        WITH RankedPhotos AS (
            SELECT
                p.timestamp,
                p.distance,
                p.gc_code,
                g.name,
                g.type,
                -- Schritt 1: Nummeriere alle Fotos pro gc_code durch.
                -- Die Sortierung (ORDER BY) entscheidet über die Reihenfolge:
                -- Zuerst nach Abstand aufsteigend, dann nach Zeitstempel aufsteigend.
                -- Die Zeile mit dem besten Ergebnis bekommt die Nummer (rn) 1.
                p.filename,
                ROW_NUMBER() OVER (
                    PARTITION BY p.gc_code
                    ORDER BY p.distance ASC, p.timestamp ASC
                ) as rn
            FROM
                photos AS p
            JOIN
                geocaches AS g ON p.gc_code = g.gc_code
            WHERE
                p.gc_code IS NOT NULL AND p.gc_code != ''
        )
        -- Schritt 2: Wähle aus den nummerierten Ergebnissen nur die Zeilen aus,
        -- die die Nummer 1 haben. Das ist genau ein Foto pro Geocache.
        SELECT
            timestamp,
            distance,
            gc_code,
            name,
            type,
            filename
        FROM
            RankedPhotos
        WHERE
            rn = 1
        ORDER BY
            timestamp DESC; -- Standard-Sortierung: Neueste zuerst
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Datenbankfehler beim Abrufen der besten Fotos pro Cache: {e}")
        return []
        
########################################################
# Reads Thumbnail for Photo
########################################################
        
def fetch_thumbnail_for_photo(db_path, filename):
    """Holt gezielt nur das Thumbnail-BLOB für einen einzelnen Dateinamen."""
    query = "SELECT thumbnail FROM photos WHERE filename = ?"
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (filename,))
            result = cursor.fetchone() # Wir erwarten nur ein Ergebnis
            return result[0] if result else None
    except sqlite3.Error as e:
        print(f"Fehler beim Laden des Thumbnails für '{filename}': {e}")
        return None
        
        
########################################################
# Reads number of Trackpoints in the database
########################################################
def get_number_trackpoints(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM trackpoints")
    rows = cursor.fetchone()
    conn.close()

    if not rows:
        return 0
    return rows[0]


########################################################
# Reads all track_id in the database
########################################################
def read_track_ids(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT distinct track_id FROM trackpoints")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return None
    return rows


########################################################
# Reads one track in the database
########################################################

def read_track(db_path, track_id):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT segment_index, lat, lon FROM trackpoints
        WHERE track_id = ?
        ORDER BY segment_index, point_index
    """, (track_id,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return None
    return rows
