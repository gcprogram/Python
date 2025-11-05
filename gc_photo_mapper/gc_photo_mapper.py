import os
import io
import sqlite3
import webbrowser
from PIL import Image, ImageTk
from PIL.ExifTags import TAGS, GPSTAGS
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import xml.etree.ElementTree as ET
import openpyxl
from datetime import datetime
import re
# Subroutines of this program
import tracks
import dbutil
import gpx
import picutil
import maputil


########################################################
# Hilfsfunktion, um mit EXIF-GPS Daten umzugehen, die
# entweder als Tupel[3] oder als Matrix[3][2] kommen.
########################################################

def to_float(val):
    try:
        if isinstance(val, tuple) and len(val) == 2:
            return float(val[0]) / float(val[1])
        else:
            return float(val)
    except (TypeError, IndexError, ZeroDivisionError, ValueError):
        return None


########################################################
# Hilfsfunktion d,m,s -> degrees
########################################################

def convert_to_degrees(value):
    if isinstance(value, tuple) and len(value) == 3:
        d, m, s = value
    else:
        d = to_float(value[0])
        m = to_float(value[1])
        s = to_float(value[2])
        if None in (d, m, s):
            return None
    return d + (m / 60.0) + (s / 3600.0)


########################################################
# Alle EXIF Daten aus Photos holen
########################################################

def get_exif_data(img):
    exif = {}
    info = img._getexif()
    if info is None:
        return exif

    for tag, value in info.items():
        decoded = TAGS.get(tag, tag)
        if decoded == "GPSInfo":
            gps_data = {}
            for t in value:
                sub_decoded = GPSTAGS.get(t, t)
                gps_data[sub_decoded] = value[t]
            exif["GPSInfo"] = gps_data
        else:
            exif[decoded] = value
    return exif


########################################################
# GPS Lat, Lon Positionen aus EXIF Daten holen
#  return (float latitude, float longitude)
########################################################

def get_lat_lon(exif_data):
    gps_info = exif_data.get("GPSInfo", {})
    if not gps_info:
        return None, None

    lat = lon = None
    try:
        lat = convert_to_degrees(gps_info["GPSLatitude"])
        if gps_info["GPSLatitudeRef"] == "S":
            lat = -lat
        lon = convert_to_degrees(gps_info["GPSLongitude"])
        if gps_info["GPSLongitudeRef"] == "W":
            lon = -lon
    except (KeyError, TypeError, ZeroDivisionError):
        return None, None

    return lat, lon

########################################################
# Extracts timestamp from EXIF, filename or file timestamp
########################################################

def extract_timestamp_from_exif_or_filename(filename):
    try:
        with Image.open(filename) as img:
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == "DateTimeOriginal":
                        try:
                            return datetime.strptime(value, "%Y:%m:%d %H:%M:%S").isoformat()
                        except Exception:
                            return value  # Fallback
    except Exception:
        pass

    # Versuche Datum aus Dateinamen im Format yyyymmdd_HHMMSS
    match = re.search(r"(20\d{6}_\d{6})", filename)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").isoformat()
        except Exception:
            pass

    # Fallback: Dateisystem-Zeit (Erstellzeit oder Änderungszeit)
    try:
        ts = os.path.getmtime(filename)
        return datetime.fromtimestamp(ts).isoformat()
    except Exception:
        return None
    

########################################################
# Read photos and their GPS positions to database
########################################################

def import_photos_from_directory(photo_dir, db_path, progress_callback=None, log_callback=None):
    files = [f for f in os.listdir(photo_dir) if f.lower().endswith(('.jpg', '.jpeg'))]
    total = len(files)
    if total == 0:
        if log_callback:
            log_callback("⚠️ Keine JPEG-Dateien gefunden.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    imported = 0

    for idx, filename in enumerate(files, 1):
        path = os.path.join(photo_dir, filename)
        timestamp = extract_timestamp_from_exif_or_filename(filename)
        # TODO: would be faster to use exif_data from open file 3 lines below
        try:
            img = Image.open(path)
            exif_data = get_exif_data(img)
            lat, lon = get_lat_lon(exif_data)
            path = path.replace("\\","/")
            if lat is not None and lon is not None:
                cursor.execute('''
                    INSERT OR REPLACE INTO photos (filename, lat, lon, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (path, lat, lon, timestamp))
                imported += 1
#                if log_callback:
#                    log_callback(f"✓ {filename}: {lat:.5f}, {lon:.5f}")
            else:
                if log_callback:
                    log_callback(f"⚠️ {filename}: Keine GPS-Daten gefunden.")
        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ Fehler bei {path}: {e}")
        finally:
            img.close()

        if progress_callback:
            progress_callback(idx / total * 100)

    conn.commit()
    conn.close()

    if log_callback:
        log_callback(f"✔️ EXIF-Import abgeschlossen ({imported} von {total} Dateien mit GPS).")

########################################################
# Uses GPS data and time from photos table to create
# a gpx track with the positions. 
########################################################

def export_photos_as_gpx(db_path, output_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT lat, lon, timestamp FROM photos WHERE lat IS NOT NULL AND lon IS NOT NULL AND timestamp IS NOT NULL ORDER BY timestamp")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return False

    gpx = ET.Element("gpx", version="1.1", creator="Exif Data Importer", xmlns="http://www.topografix.com/GPX/1/1")
    trk = ET.SubElement(gpx, "trk")
    name = ET.SubElement(trk, "name")
    name.text = "Photo Track"
    trkseg = ET.SubElement(trk, "trkseg")

    for lat, lon, timestamp in rows:
        trkpt = ET.SubElement(trkseg, "trkpt", lat=str(lat), lon=str(lon))
        time_elem = ET.SubElement(trkpt, "time")
        time_elem.text = timestamp + "Z" if not timestamp.endswith("Z") else timestamp

    tree = ET.ElementTree(gpx)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return True

########################################################
# Export photo table as Excel file
########################################################

def export_photos_as_excel(db_path, path, with_thumbnails):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM photos")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return False

    col_names = [d[0] for d in cur.description]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(col_names)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return True

########################################################
# Reads images, creates thumbnails of size 200x200 and
# saves them in a thumbnail directory
# Example: 
#   thumbrel_dir = "thumbs"
#   thumb_prefix = "/t_"
#   source_path  = "path/yyyymmdd_HHMM.jpg"
#   thumbpath    = "path/thumbs/t_yyyymmdd_HHMM.jpg"
########################################################

def photo_to_thumbname(source_path, thumbrel_dir="thumbs", thumb_prefix="t_"):
    thumbpath = None
    thumbrel_path = None
    if source_path.lower().endswith((".jpg", ".jpeg")):
        thumbrel_path = os.path.join(thumbrel_dir, thumb_prefix + os.path.basename(source_path)).replace("\\","/");
        thumbpath = os.path.join( os.path.dirname(source_path),thumbrel_dir, thumb_prefix + os.path.basename(source_path))
        thumbpath = thumbpath.replace("\\","/");
#        print(f"photo_to_thumbname photo={source_path} -> thumbrel={thumbrel_path}, thumbpath={thumbpath}");
    return thumbrel_path, thumbpath    


########################################################
# Zeigt das generierte HTML-File an.
# Öffnet den Webbrowser mit der Karte.
########################################################

def open_map_window(self):
    html_file = maputil.generate_map(self)
    if html_file:
        webbrowser.open(f"file://{os.path.abspath(html_file)}")
    else:
        messagebox.showinfo("Keine Fotos", "Es sind keine Fotos mit GPS-Daten vorhanden.")

########################################################
# Sets fields in GUI with values:
#   time_min of photos
#   time_max of photos
#   number of photos
#   number of geocaches
#   number of track points
#   number of different tracks
########################################################

def set_fields(self):
    photo_cnt,tmin,tmax = dbutil.get_photos_tmin_tmax(self.db_path)    
    self.tk_photo_count.set(photo_cnt)
    self.tk_time_min.set(tmin)
    self.tk_time_max.set(tmax)
    geocaches_cnt = dbutil.get_number_geocaches(self.db_path)
    self.tk_geocaches_count.set(geocaches_cnt)
    trackpnts_cnt = dbutil.get_number_trackpoints(self.db_path)
    self.tk_trackpnts_count.set(trackpnts_cnt)
    trackids = dbutil.read_track_ids(self.db_path)
    self.tk_track_ids.set(trackids)


########################################################
# GUI mit Menü, Radiusfeld und Buttons
########################################################

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Geocaching Photo Mapper")
        self.db_path = "geo_data.db"
        self.source_dir = os.getcwd()
        self.zoom = -1
        dbutil.initialize_database(self.db_path)
        self.tk_gap_segment_time = tk.StringVar(value="00:20:00")
        self.tk_mapping_radius_m = tk.StringVar(value="100")
        self.tk_photo_count = tk.StringVar(value="0")
        self.tk_geocaches_count = tk.StringVar(value="0")
        self.tk_trackpnts_count = tk.StringVar(value="0")
        self.tk_track_ids = tk.StringVar(value="")
        self.tk_time_min = tk.StringVar(value="1970-01-01T00:00:00")
        self.tk_time_max = tk.StringVar(value="2100-12-31T23:59:59")
        self.sort_timestamp_asc = False

        self.size = (200, 200)
        self.show_track = True
        self.show_geocaches = True
        self.show_photos = True    # show photos directly or markers first?
        self.build_menu()
        
        self.photo_data_map = {}
        self.build_gui()


    def build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Geocaches importieren", command=self.import_gpx)
        file_menu.add_command(label="Fotos importieren", command=self.import_photos)
        file_menu.add_command(label="Tracks importieren", command=self.import_tracks)
        file_menu.add_separator()
        file_menu.add_command(label="Geocaches exportieren", command=self.export_geocaches)
        file_menu.add_command(label="Fotos exportieren", command=self.export_photos)
        file_menu.add_command(label="Tracks exportieren", command=self.export_tracks)
        file_menu.add_command(label="Photo-Track exportieren", command=self.export_photos_track)
        file_menu.add_separator()
        file_menu.add_command(label="Beenden", command=self.root.quit)
        
        delete_menu = tk.Menu(menubar, tearoff=0)
        delete_menu.add_command(label="Geocaches löschen", command=self.clear_geocaches)
        delete_menu.add_command(label="Fotos löschen", command=self.clear_photos)      
        delete_menu.add_command(label="Track löschen", command=self.clear_track)
        delete_menu.add_command(label="Alle Tracks löschen", command=self.clear_tracks)

        map_menu = tk.Menu(menubar, tearoff=0)
        map_menu.add_command(label="Photos -> Geocache", command=self.run_mapping)
        map_menu.add_command(label="Photos -> Direkter Track", command=self.photos2track)
        map_menu.add_command(label="Photos -> Routing Track", command=self.photos2routing)
        map_menu.add_command(label="Photos umbenennen nach GCCODE", command=self.photos_rename)
        map_menu.add_command(label="Track -> Photos ohne EXIF", command=self.unimplemented)
        map_menu.add_separator()
        map_menu.add_command(label="Zeige Track ", command=self.unimplemented)
        map_menu.add_command(label="Zeige Fotos ", command=self.unimplemented)
        map_menu.add_command(label="Zeige Geocaches ", command=self.unimplemented)
        map_menu.add_separator()
        map_menu.add_command(label="Karte anzeigen", command=lambda: open_map_window(self))
       
        
        menubar.add_cascade(label="Datei",   menu=file_menu)
        menubar.add_cascade(label="Löschen", menu=delete_menu)
        menubar.add_cascade(label="Mapping", menu=map_menu)
        self.root.config(menu=menubar)

    def slider_changed(self, value):
        self.zoom = int(float(value))  # Wert ist ein String, wird zu float, dann int 
        self.zoom_label.config(text = f"Zoom({self.zoom}):")

    def build_gui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        # Wichtig, damit der Frame und die Tabelle mit dem Fenster wachsen
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frm.columnconfigure(list(range(6)), weight=1) # Spalten für Widgets
        frm.rowconfigure(7, weight=1) # Zeile für die Tabelle soll wachsen

        # gui row 0
        ttk.Label(frm, text="Geocaches Anzahl:"                ).grid(row=1, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.tk_geocaches_count, width=7, state="readonly").grid(row=1, column=1, sticky="w")
           
        # gui row 1   
        ttk.Label(frm, text="Fotos Anzahl:"                    ).grid(row=0, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.tk_photo_count, width=7, state="readonly").grid(row=0, column=1, sticky="w")
        ttk.Label(frm, text="Startzeit:"                       ).grid(row=0, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.tk_time_min, width=19    ).grid(row=0, column=3, sticky="w")
        ttk.Label(frm, text="Endzeit:"                         ).grid(row=0, column=4, sticky="e")
        ttk.Entry(frm, textvariable=self.tk_time_max, width=19    ).grid(row=0, column=5, sticky="w")
        
        # gui row 2
        ttk.Label(frm, text="Trackpunkte Anzahl:"              ).grid(row=2, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.tk_trackpnts_count, width=7, state="readonly").grid(row=2, column=1, sticky="w")
        ttk.Label(frm, text="Segment Gap (hh:mm:ss):"          ).grid(row=2, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.tk_gap_segment_time, width=19).grid(row=2, column=3, sticky="w")        
        ttk.Label(frm, text="Tracks IDs:"                      ).grid(row=2, column=4, sticky="e")
        ttk.Entry(frm, textvariable=self.tk_track_ids, width=19, state="normal" ).grid(row=2, column=5, sticky="w")

        # gui row 3
        ttk.Label(frm, text="Mapping-Radius (m):"                 ).grid(row=3, column=0, sticky="e")
        ttk.Entry(frm, textvariable=self.tk_mapping_radius_m, width=7).grid(row=3, column=1, sticky="w")
        ttk.Button(frm, text="🧭 Mapping durchführen", command=self.run_mapping).grid(row=3, column=2, sticky="e")
        ttk.Button(frm, text="🗺️ Karte anzeigen", command=lambda: open_map_window(self)).grid(row=3, column=3, sticky="w")
        self.zoom_label = ttk.Label(frm, text="Zoom(-1):") 
        self.zoom_label.grid(row=3, column=4, sticky="e")
        slider = ttk.Scale(frm, from_=-1, to=20, orient=tk.HORIZONTAL, length=150, command=self.slider_changed)
        slider.grid(row=3, column=5, sticky="w")

        # gui row 4
        self.progress = ttk.Progressbar(frm, length=400)
        self.progress.grid(row=4, column=0, columnspan=6, pady=5, sticky="ew")

        # gui row 5
        ttk.Label(frm, text="Log:"                 ).grid(row=5, column=0, sticky="w")
        
        # gui row 6
        self.log = tk.Text(frm, height=6, wrap="word")
        self.log.grid(row=6, column=0, columnspan=6, pady=10, sticky="nsew")

        # gui row 7: Die Tabelle (Treeview) für die Ergebnisse

        # Ein Frame, um die Tabelle und die Scrollbar zusammenzuhalten
        tree_frame = ttk.Frame(frm)
        tree_frame.grid(row=7, column=0, columnspan=6, sticky="nsew", pady=(5, 0))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        # Spalten-IDs und die anzuzeigenden Titel definieren
        columns = ('timestamp', 'distance', 'gccode', 'name', 'type')
        
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings')

        # Spaltenüberschriften definieren
        # Beim Definieren der Spaltenüberschrift fügen wir den 'command' hinzu
        self.tree.heading('timestamp', text='Zeit des Fotos ▼', command=self.sort_by_timestamp)
        self.tree.heading('distance', text='Abstand')
        self.tree.heading('gccode', text='GC-Code')
        self.tree.heading('name', text='Cache-Name')
        self.tree.heading('type', text='Cache-Typ')

        # Spaltenbreiten anpassen
        self.tree.column('timestamp', width=120, stretch=tk.NO)
        self.tree.column('distance', width=55, stretch=tk.NO, anchor='e') # rechtsbündig
        self.tree.column('gccode', width=70, stretch=tk.NO)
        self.tree.column('name', width=300)
        self.tree.column('type', width=120)
        # Photo anzeigen bei Click
        self.tree.bind('<<TreeviewSelect>>', self.on_photo_select)

        self.tree.grid(row=0, column=0, sticky="nsew")

        # Scrollbar hinzufügen und mit dem Treeview verbinden
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky='ns')

        # Daten beim Start laden und anzeigen
        self.populate_results_table()
        # set fields
        set_fields(self)
        picutil.read_icons_files(self.db_path, self.source_dir, self.update_progress, self.log_message)
        # Eine Queue für die Kommunikation vom Worker-Thread zum GUI-Thread
        #self.task_queue = queue.Queue()

    def unimplemented(self):
        self.log.insert(tk.END, "❌ Diese Funktion ist noch nicht implementiert" + "\n")
        self.log.see(tk.END)
        
    def log_message(self, msg):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def update_progress(self, percent):
        self.progress["value"] = percent
        self.root.update_idletasks()

    def import_gpx(self):
        file_path = filedialog.askopenfilename(filetypes=[("GPX- oder PQ-Dateien", "*.gpx *.zip")])
        if file_path:
            gpx.import_gpx_with_progress(file_path, self.db_path, self.update_progress, self.log_message)
        set_fields(self)  

    def import_photos(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            import_photos_from_directory(dir_path, self.db_path, self.update_progress, self.log_message)
            set_fields(self)
            picutil.create_thumbnail(self.db_path, self.size, self.update_progress, self.log_message)


    def import_tracks(self):
        file_path = filedialog.askopenfilename(filetypes=[("GPX-Track-Dateien", "*.gpx")])
        if file_path:
            tracks.import_gpx_tracks_gemini(self.db_path, file_path, self.update_progress, self.log_message)
        set_fields(self)  

    def photos2track(self):
        tracks.photos2track(self.db_path,self.gap_segment_time.get(), self.update_progress, self.log_message)
        set_fields(self)

    def photos2routing(self):
        tracks.route_photo_sequence(self.db_path)
        set_fields(self)

    def photos_rename(self):
        maputil.rename_photos_gccode(self.db_path)
        self.log_message("✔️ Fotos umbenannt")

    def run_mapping(self):
        try:
            radius_m = float(self.tk_mapping_radius_m.get())
            maputil.map2gccode_performant(self.db_path, radius_m, self.log_message)
            self.populate_results_table()
        except ValueError:
            self.log_message("❌ Ungültiger Radiuswert.")

    def populate_results_table(self):
        """Löscht die Tabelle und füllt sie mit den aktuellen Daten aus der DB."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.photo_data_map.clear()

        # mapped_photos enthält jetzt KEIN thumbnail mehr
        mapped_photos = dbutil.fetch_mapped_photos_for_display(self.db_path)

        for photo_data in mapped_photos:
            # Das Tupel hat jetzt nur noch 6 Elemente
            timestamp, distance, gccode, name, cache_type, filename = photo_data

            display_values = (timestamp, f"{distance:.1f} m", gccode, name, cache_type)
            iid = self.tree.insert('', tk.END, values=display_values)

            # Speichere nur noch den Dateinamen
            self.photo_data_map[iid] = filename

        self.sort_timestamp_asc = False
        self.tree.heading('timestamp', text='Zeit des Fotos ▼')

    def sort_by_timestamp(self):
        """Sortiert die Treeview-Einträge nach der Zeitstempel-Spalte."""
        # 1. Alle Zeilen aus dem Treeview als Liste von Tupeln holen
        # Format: [(wert_zum_sortieren, item_id), ...]
        items = [(self.tree.set(item, 'timestamp'), item) for item in self.tree.get_children('')]

        # 2. Sortierrichtung umschalten (toggeln)
        self.sort_timestamp_asc = not self.sort_timestamp_asc

        # 3. Liste sortieren. Da der Zeitstempel im Format 'JJJJ-MM-TT HH:MM:SS'
        #    ist, funktioniert eine einfache String-Sortierung korrekt.
        items.sort(reverse=not self.sort_timestamp_asc)

        # 4. Items in der neuen Reihenfolge im Treeview anordnen
        for index, (val, item) in enumerate(items):
            self.tree.move(item, '', index)

        # 5. Spaltenüberschrift mit Pfeil aktualisieren, um die Sortierrichtung anzuzeigen
        header_text = "Zeit des Fotos " + ("▲" if self.sort_timestamp_asc else "▼")
        self.tree.heading('timestamp', text=header_text)

    # Lazy loading of Photo for Popup
    def on_photo_select(self, event):
        """Holt bei Auswahl den Dateinamen und lädt DANN ERST das Thumbnail."""
        selected_items = self.tree.selection()
        if not selected_items:
            return

        selected_iid = selected_items[0]

        if selected_iid in self.photo_data_map:
            # 1. Nur den Dateinamen aus unserem Map holen
            filename = self.photo_data_map[selected_iid]

            # 2. JETZT das Thumbnail gezielt aus der DB laden
            thumbnail_blob = dbutil.fetch_thumbnail_for_photo(self.db_path, filename)

            # 3. Das Popup mit den vollständigen Daten aufrufen
            self.show_image_popup(filename, thumbnail_blob)


    #############################################
    # Popup Fenster für das Bild
    #############################################
    def show_image_popup(self, filename, thumbnail_blob):
        """Öffnet ein Popup-Fenster, um das angegebene Bild anzuzeigen."""
        
        image_to_show = None
        
        # 1. Versuche, das Bild von der Festplatte zu laden
        if os.path.exists(filename):
            try:
                image_to_show = Image.open(filename)
                title = os.path.basename(filename) or "Bildanzeige" # Standardtitel
            except Exception as e:
                print(f"Fehler beim Laden der Original-Datei '{filename}': {e}")
                image_to_show = None # Fallback zum Thumbnail
        
        # 2. Wenn das Laden von der Festplatte fehlschlug, versuche das Thumbnail
        if image_to_show is None:
            if thumbnail_blob:
                try:
                    # BLOB-Daten in ein für Pillow lesbares Format umwandeln
                    image_stream = io.BytesIO(thumbnail_blob)
                    image_to_show = Image.open(image_stream)
                    title = f"{os.path.basename(filename)} (Thumbnail aus DB)"
                except Exception as e:
                    print(f"Fehler beim Laden des Thumbnails aus der DB: {e}")
            else:
                # Kein Thumbnail vorhanden
                print(f"Datei '{filename}' nicht gefunden und kein Thumbnail in der DB.")

        # Neues Popup-Fenster erstellen
        popup = tk.Toplevel(self.root)
        popup.title(title)
        
        if image_to_show:
            # Bildgröße an den Bildschirm anpassen, falls es zu groß ist
            max_w = self.root.winfo_screenwidth() * 0.8
            max_h = self.root.winfo_screenheight() * 0.8
            image_to_show.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            
            # Bild in ein Tkinter-kompatibles Format umwandeln
            photo_image = ImageTk.PhotoImage(image_to_show)
            
            label = ttk.Label(popup, image=photo_image)
            
            # WICHTIG: Referenz auf das Bild speichern, sonst wird es vom
            # Garbage Collector gelöscht und nicht angezeigt!
            label.image = photo_image
            label.pack(padx=1, pady=1) # minimaler Rand, damit Klick gut funktioniert
        else:
            # Fallback, wenn kein Bild geladen werden konnte
            label = ttk.Label(popup, text=f"Bild konnte nicht geladen werden:\n{filename}", padding=20)
            label.pack()
            
        # 3. Klick-Event an das Label binden (egal ob Bild oder Text angezeigt wird)
        if label:
            label.bind("<Button-1>", lambda event: popup.destroy())
        
        # Optional: Auch Klick auf das Fenster selbst schließt es
        popup.bind("<Button-1>", lambda event: popup.destroy())
    
        popup.transient(self.root) # Hält das Popup über dem Hauptfenster
        popup.grab_set()          # Macht das Popup modal
        self.root.wait_window(popup) # Wartet, bis das Popup geschlossen wird



    def clear_geocaches(self):
        dbutil.clear_geocaches(self)
        self.tk_geocaches_count.set(0)
        self.log_message("🗑️ Geocache-Tabelle geleert.")
        set_fields(self)  

    def clear_photos(self):
        dbutil.clear_photos(self)
        self.tk_photo_count.set(0)
        self.log_message("🗑️ Foto-Tabelle geleert.")
        set_fields(self)  

    def clear_track(self):
        track = self.tk_track_ids.get()
        if (len(track.split(" ")) > 1):
            self.log_message("❌ Es darf nur ein Track in dem Track IDs Feld stehen.")
            return
        dbutil.clear_track(self,track)
        self.log_message(f"🗑️ Track {track} gelöscht.")
        set_fields(self)

    def clear_tracks(self):
        dbutil.clear_tracks(self)
        self.log_message("🗑️ Tracks und Trackpoints-Tabelle geleert.")
        set_fields(self)  
        
    def export_geocaches(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel-Dateien", "*.xlsx")])
        if path:
            rows = dbutil.read_geocaches_full(self.db_path)
            col_names = dbutil.get_geocaches_col_names(self.db_path)
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(col_names)
            for row in rows:
                ws.append(row)
            wb.save(path)
            self.log_message(f"✔️ Geocaches exportiert nach {path}")

    def export_photos(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel-Dateien", "*.xlsx")])
        if path:
            status = export_photos_as_excel(self.db_path, path, True)
            if status:
                self.log_message(f"✔️ Photos Tabelle exportiert nach {path}")
            else:
                self.log_message(f"❌ Photos Tabelle konnte nicht exportiert werden nach {path}")

    def export_photos_track(self):
        path = filedialog.asksaveasfilename(defaultextension=".gpx", filetypes=[("GPX-Track-Dateien", "*.gpx")])
        if path:
            status = export_photos_as_gpx(self.db_path, path)
            if status:
                self.log_message(f"✔️ Photo Track exportiert nach {path}")
            else:
                self.log_message(f"❌ Photo Track konnte nicht exportiert werden nach {path}")
           
    def export_tracks(self):
        path = filedialog.asksaveasfilename(defaultextension=".gpx", filetypes=[("GPX-Track-Dateien", "*.gpx")])
        if path:
            status = tracks.export_tracks_to_gpx(self.db_path, path)
            if status:
                self.log_message(f"✔️ Track exportiert nach {path}")
            else:
                self.log_message(f"❌ Track konnte nicht exportiert werden nach {path}")

               
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()


# IDEEN:
# - Fortschrittsbalken bei Photomap
# - Bilder umbenennen nach GCCODE
# - Umbenennen rückgängig machen
# - Fehlende Position setzen, wenn Track einen Wert in der Nähe
# - Fehlende Position: Extrapolierte Position zwischen zwischen Phoot-Position
# - Fehlender errechnete Position in EXIF übertragen
# - Liste mit gemappten Caches ausgeben.
# - Liste mit Found Caches einlesen (über GPX PQ, C:GEO Export oder CSV von Found-Liste  
#
# Syntax:
#
# folium.Marker(
#    location,        # [latitude, longitude]
#    popup=None,      # Text oder HTML-Popup (optional)
#    tooltip=None,    # Text beim Hover (optional)
#    icon=None,       # folium.Icon() oder folium.DivIcon() (optional)
#    draggable=False  # Ob der Marker verschiebbar ist (optional)
#).add_to(map)
#
# Syntax CustomIcon: (viele Marker gleichen Types)
# icon = folium.CustomIcon('type_traditional.png', icon_size=(24, 24))
# folium.Marker(location=[lat, lon], icon=icon).add_to(m)
#
