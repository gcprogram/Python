# media_gui.py
import os
import threading
import pandas as pd
from tkinter import (
    Tk, Frame, Button, Label, filedialog, ttk, messagebox, Text,
    Scrollbar, Checkbutton, IntVar, StringVar, Menu, Toplevel, Canvas, PhotoImage, END, BOTH, X, Y, RIGHT, BOTTOM, W
)
from tqdm import tqdm
from PIL import Image, ImageTk, ExifTags

from ai_tools import AITools
from media_tools import _get_exif_data, _get_video_metadata, get_meta_data, get_kind_of_media, format_time2mmss
import subprocess
from moviepy.video.io.VideoFileClip import VideoFileClip

class MediaAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🧭 Medien Analyse")
        self.root.geometry("1200x750")
        # Cache für Thumbnail-Pfade
        self._last_thumb_path = None
        self._last_thumb_image = None
        self.folder = None
        self.create_menu()
        self.create_top_controls()
        self.create_table()

        self.aitools = None
        self.current_folder = None

    # ---------------- Menü ----------------
    def create_menu(self):
        menubar = Menu(self.root)
        filemenu = Menu(menubar, tearoff=0)
        filemenu.add_command(label="Bulk Load", command=self.choose_folder)
        filemenu.add_command(label="Single File", command=self.choose_single_file)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        self.root.config(menu=menubar)
        # Hilfe-Menü
        helpmenu = Menu(menubar, tearoff=0)
        helpmenu.add_command(label="Was ist das?", command=self.show_help_info)
        helpmenu.add_command(label="Info BLIP", command=self.show_help_blip)
        helpmenu.add_command(label="Info WHISPER", command=self.show_help_whisper)
        helpmenu.add_separator()
        helpmenu.add_command(label="Info", command=self.show_info)
        menubar.add_cascade(label="Hilfe", menu=helpmenu)

        self.root.config(menu=menubar)

    def show_help_info(self):
        messagebox.showinfo("Was ist das?", "Mit dieser Anwendung kannst Du Deine Medienalben\n"
                                                        "Fotos, Videos und sogar Audiodateien\n"
                                                        "automatisch beschreiben lassen. Dazu werden zwei\n"
                                                        "KI-Modelle genutzt, die lokal ausgeführt werden.\n"
                                                        "Deine Daten sind sicher. Ausgabe ist eine exportierbare\n"
                                                        "Liste, die Filename, Orte, Bild- und Audio-Inhalt erkennt.\n"
                                                        "Audios können als Text ausgegeben werden (multilingual).\n"
                                                        "Aus Videos werden Einzelbilder herausgezogen und beschrieben.\n\n"
                                                        "Beispiel Anwendungsfälle:\n"
                                                        "Urlaubsbilder: Ort herausfinden und Kurzbeschreibung, was darauf ist.\n"
                                                        "Lernvideos: Transkipt erstellen und alle 30 sec Bild speichern.\n"
                                                        "Hörbuch: In Text verwandeln.")

    def show_help_blip(self):
        messagebox.showinfo("Info", "Die Offline KI BLIP macht kurze Bildbeschreibungen.\n" 
            "Man kann die maximale Anzahl Tokens anpassen, aber in der Realität verändert sich nicht viel.\n"
            "Voreinstellung hier ist 100.\n"
            "\nBLIP  wurde von Salesforce Research entwickelt und\n"
            "steht unter der Apache License 2.0 https://spdx.org/licenses/Apache-2.0.html\n"
                            )
    def show_help_whisper(self):
        messagebox.showinfo("Info", "Die Offline KI Whisper transkribiert Audios.\n" 
            "️Mögliche Whisper-Modelle zur Auswahl:\n"
            "Name	Größe (RAM)	Geschwindigkeit	Genauigkeit	Bemerkung\n"
            "tiny\t	~75 MB	\t⚡ Sehr schnell	\t😐 Gering	Nur für sehr saubere, kurze Audios ohne Akzent\n"
            "base\t	~142 MB	\t🔸 Schnell	\t🙂 Mittelmäßig	Gute Wahl bei klarer Sprache, ruhiger Umgebung\n"
            "small\t	~466 MB	\t⚖️ Ausgewogen	\t👍 Gut	Sehr gutes Preis-Leistungs-Verhältnis (Standard)\n"
            "medium\t	~1.5 GB	\t🐢 Langsamer	\t💪 Sehr gut	Bessere Erkennung bei Akzenten & Hintergrundgeräuschen\n"
            "large / large-v2 / large-v3	~3–6 GB	\t🐌 Deutlich langsamer	\t🧠 Exzellent	Fast professionelle Qualität, sehr robust bei Rauschen, Akzent, Mehrsprachigkeit\n"
            "\nWhisper wurde von OpenAI entwickelt und\n"
            "          steht unter der MIT Lizenz https://spdx.org/licenses/MIT.html\n"
        )

    def show_info(self):
        messagebox.showinfo("Info", "Version 1.0\nErstellt von Stefan Markgraf.\n"
                                 "Lizenz: MIT\n\n"
                                 "Benutzte KI-Modelle und Services:\n"
                                 "* BLIP - Bildbeschreibung\n"
                                 "* WHISPER - Audio Transkripte\n"
                                 "* NOMINATIM - Koordinaten zu Adresse (OpenStreetMaps basiert)")


        # ---------------- Layout / Konfiguration ----------------
    def create_top_controls(self):
        config_frame = Frame(self.root)
        config_frame.pack(fill=X, pady=10, padx=10)

        # --- Zeile 1: Transkriptionsmodell ---
        Label(config_frame, text="🎙 Transkriptionsmodell:", font=("Arial", 11)).grid(row=0, column=0, sticky=W, padx=5)
        self.model_var = StringVar(value="small")
        self.model_menu = ttk.Combobox(
            config_frame,
            textvariable=self.model_var,
            values=["tiny", "base", "small", "medium", "large-v3"],
            state="readonly", width=10
        )
        self.model_menu.grid(row=0, column=1, sticky=W, padx=5)
        self.save_transcript_var = IntVar(value=0)
        Checkbutton(config_frame, text="Transkripte speichern", variable=self.save_transcript_var).grid(row=0, column=2, sticky=W)

        # --- Zeile 2: Analyse-Intervall ---
        Label(config_frame, text="⏱ Video Analyse-Intervall (Sek.):", font=("Arial", 11)).grid(row=1, column=0, sticky=W, padx=5)
        self.interval_var = StringVar(value="10")
        ttk.Entry(config_frame, textvariable=self.interval_var, width=6).grid(row=1, column=1, sticky=W, padx=5)
        self.save_frames_var = IntVar(value=0)
        Checkbutton(config_frame, text="Frames speichern", variable=self.save_frames_var).grid(row=1, column=2, sticky=W)


        # --- Zeile 3: Ordnerwahl ---
        Label(config_frame, text="📂 Analyse File/Ordner:", font=("Arial", 11)).grid(row=2, column=0, sticky=W, padx=5, pady=(10,0))
        Button(config_frame, text="Ordner auswählen", command=self.choose_folder).grid(row=2, column=1, sticky=W, padx=5, pady=(10,0))
        Button(config_frame, text="File auswählen", command=self.choose_single_file).grid(row=2, column=2, sticky=W, padx=5, pady=(10, 0))

        # Fortschritt
        self.status_label = Label(config_frame, text="Status", font=("Arial", 10))
        self.status_label.grid(row=3, column=0, sticky=W, padx=5, pady=(10, 0))
        self.status_label2 = Label(config_frame, text="Fortschritt:", font=("Arial", 10))
        self.status_label2.grid(row=3, column=1, sticky=W, padx=5, pady=(10, 0))
        self.progress = ttk.Progressbar(config_frame, orient="horizontal", length=400, mode="determinate")
        self.progress.grid(row=3, column=2, sticky=W, padx=5, pady=(10,0))

    # ---------------- Tabelle ----------------
    def create_table(self):
        table_frame = Frame(self.root)
        table_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        cols = ("File", "Type", "Date", "Lat", "Lon", "Length", "Address", "Image", "Audio")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=20)
        for col in cols:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_column(c, False))
            width = {"File": 105, "Type": 35, "Date": 100, "Lat":55, "Lon":55, "Length": 50, "Address": 150, "Image": 250, "Audio": 250}.get(col, 100)
            self.tree.column(col, width=width, anchor="w")

        # Scrollbars anlegen
        vsb = Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)

        # Treeview <-> Scrollbars koppeln
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Grid-Layout: tree in (0,0), vsb in (0,1), hsb in (1,0)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        # Thumbnail-Hover
        self.thumb_window = None
        self._last_thumb_path = None
        self._last_thumb_image = None
        self.tree.bind("<Motion>", self.on_hover)
        self.tree.bind("<Leave>", self.on_leave)

        # Double-Click Play
        self.tree.bind("<Double-1>", self.on_double_click)

        # Make the tree expand when window is resized
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

    # ---- Thumbnail Hover ----
    def on_hover(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            self.hide_thumbnail()
            return
        row_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row_id or col != "#1":  # Spalte 1 = Datei
            self.hide_thumbnail()
            return

        values = self.tree.item(row_id, "values")
        if not values:
            return
        filename = values[0]
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            self.hide_thumbnail()
            return
        #folder = getattr(self, "current_folder", "")
        folder = self.folder
        print("file=", filename)
        print("folder=", folder)

        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            self.hide_thumbnail()
            return

        # Debounce: gleiches File wie letztes? Dann nicht neu laden
        if self._last_thumb_path == path:
            return

        self._last_thumb_path = path
        if filename.lower().endswith((".jpg", ".jpeg", ".png")):
            self.show_image_thumbnail(path, event.x_root, event.y_root)
        elif filename.lower().endswith((".mp4", ".mov", ".avi")):
            self.show_video_thumbnail(path, event.x_root, event.y_root)

    def show_video_thumbnail(self, path, x, y):
        try:
            clip = VideoFileClip(path)
            mid = clip.duration / 2
            frame = clip.get_frame(mid)  # numpy array
            clip.close()
            img = Image.fromarray(frame)
            img.thumbnail((200, 200))
            photo = ImageTk.PhotoImage(img)
            self._last_thumb_image = photo
            self._show_thumbnail_window(photo, x, y)
        except Exception:
            self.hide_thumbnail()

    def _show_thumbnail_window(self, photo, x, y):
        if self.thumb_window:
            self.thumb_window.destroy()
        self.thumb_window = Toplevel(self.root)
        self.thumb_window.overrideredirect(True)
        self.thumb_window.geometry(f"+{x + 20}+{y + 20}")
        label = Label(self.thumb_window, image=photo)
        label.image = photo
        label.pack()

    def on_leave(self, event):
        self.hide_thumbnail()
        self._last_thumb_path = None
        self._last_thumb_image = None

    def show_image_thumbnail(self, path, x, y):
        try:
            img = Image.open(path)
            # Orientierung aus EXIF
            try:
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == 'Orientation':
                        break
                exif = img._getexif()
                if exif and orientation in exif:
                    o = exif[orientation]
                    if o == 3:
                        img = img.rotate(180, expand=True)
                    elif o == 6:
                        img = img.rotate(270, expand=True)
                    elif o == 8:
                        img = img.rotate(90, expand=True)
            except Exception:
                pass
            img.thumbnail((200, 200))
            photo = ImageTk.PhotoImage(img)
            self._last_thumb_image = photo
            self._show_thumbnail_window(photo, x, y)
        except Exception:
            self.hide_thumbnail()

    def hide_thumbnail(self):
        if self.thumb_window:
            self.thumb_window.destroy()
            self.thumb_window = None

    def setup_click_play(self):
        self.tree.bind("<Double-1>", self.on_double_click)

    def on_double_click(self, event):
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        values = self.tree.item(row_id, "values")
        filename = values[0]
        folder = getattr(self, "current_folder", "")
        path = os.path.join(folder, filename)
        if os.path.exists(path) and filename.lower().endswith((".mp4", ".mov", ".avi")):
            # Standard Video-Player öffnen
            if os.name == "nt":  # Windows
                os.startfile(path)
            elif os.name == "posix":  # macOS/Linux
                print("masOS, Linux Playback not implemented yet")
                #subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", path])


    # ---- Tabellen-Sortierung ----
    def sort_column(self, col, reverse):
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        try:
            items.sort(key=lambda t: (float(t[0]) if t[0].replace('.', '', 1).isdigit() else t[0].lower()),
                        reverse=reverse)
        except Exception:
            items.sort(key=lambda t: t[0].lower(), reverse=reverse)
        for index, (val, k) in enumerate(items):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    # ---------------- Analyse ----------------
    def choose_folder(self):
        self.folder = filedialog.askdirectory(title="Verzeichnis wählen")
        if self.folder:
            threading.Thread(target=self.analyze_folder, args=(self.folder,), daemon=True).start()

    def choose_single_file(self):
        file = filedialog.askopenfilename(
            title="Datei wählen",
            filetypes=[("Medien", "*.jpg *.jpeg *.png *.mp4 *.mov *.avi *.mp3 *.wav *.m4a *.flac"), ("Alle Dateien", "*.*")]
        )
        if file:
            self.folder = os.path.dirname(file)
            threading.Thread(target=self.analyze_single_file, args=(file,), daemon=True).start()

    def analyze_folder(self, file_path):
        self.status_label.config(text="📦 Lade KI-Modelle...")
        self.root.update_idletasks()

        whisper_choice:str = self.model_var.get()
        self.aitools = AITools(audio_model_size=whisper_choice)
        interval = int(self.interval_var.get())

        records = []
        if os.path.isdir(file_path):
            # Erzeuge eine Liste von Dateipfaden für alle Dateien im Verzeichnis
            folder = file_path
            all_files = [os.path.join(root, f) for root, _, files in os.walk(file_path) for f in files]

        elif os.path.isfile(file_path):
            # Setze all_files auf eine Liste, die nur den angegebenen Dateipfad enthält
            folder = os.path.dirname(file_path)
            all_files = [file_path]
        else:
            # Bei ungültigem Pfad kann hier ein Fehler ausgelöst oder behandelt werden
            all_files = []
            print("Der angegebene Pfad ist weder eine Datei noch ein Verzeichnis.")

        total = len(all_files)
        self.progress["maximum"] = total
        self.status_label.config(text=f"🔍 Analysiere {total} Dateien...")

        self.tree.delete(*self.tree.get_children())

        for i, path in enumerate(tqdm(all_files, desc="Analysiere")):
            kind = get_kind_of_media(path)
            if kind == "unknown":
                self.progress["value"] = i + 1
                continue
            relpath = os.path.relpath(path, folder)
            rec = {"File": relpath, "Type": kind.capitalize(), "Date": "", "Lat": "", "Lon": "", "Length": "", "Address": "", "Image": "", "Audio": ""}
            image_text = ""
            audio_text = ""
            try:
                meta = get_meta_data(path)
                rec["Date"] = meta.get("Date", "")
                rec["Address"] = meta.get("Address", "")
                rec["Lat"] = meta.get("Lat", "")
                rec["Lon"] = meta.get("Lon", "")
                rec["Length"] = meta.get("Length", "")
                if kind == "image":
                    image_text = self.aitools.describe_image(path)
                    if self.save_transcript_var.get():
                        self._save_transcript(file_path, image_text.translate(str.maketrans("|", '\n')))
                elif kind == "video":
                    image_text = self.aitools.describe_video_by_frames(path, interval)
                    audio_text = self.aitools.transcribe_audio(path)
                    if self.save_frames_var.get():
                        self._save_video_frames(path, interval)
                elif kind == "audio":
                    audio_text = self.aitools.transcribe_audio(path)

                rec["Audio"] = audio_text
                rec["Image"] = image_text
                text = ""
                # Saved transcript contains Audio+Image Content
                if self.save_transcript_var.get():
                    if audio_text != "" and image_text != "":
                        text = "\"" + audio_text + "\"\n\n " + image_text.translate(str.maketrans("|", '\n'))
                    elif kind == "audio" or "video":
                        text = "\"" + audio_text + "\"\n\n " + image_text.translate(str.maketrans("|", '\n'))

                    textfile = f"{path}.txt"
                    if text != "":
                        with open(textfile, "w", encoding="utf-8") as f:
                            f.write(text)

            except Exception as e:
                print("⚠️ Fehler bei:", path, e)

            records.append(rec)
            self.tree.insert("", "end", values=tuple(rec.values()))
            self.progress["value"] = i + 1
            self.root.update_idletasks()
            if total == 1:
                text = audio_text + "\n\n " + image_text.translate(str.maketrans("|", '\n'))
                self.show_result_window(file_path, kind, text)

        df = pd.DataFrame(records)
        out_path = os.path.join(folder, "_media_analysis.csv")
        df.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig")
        out_file = os.path.basename(out_path)
        self.status_label.config(text=f"✅ Fertig → {out_file}")

        messagebox.showinfo("Fertig", f"Analyse abgeschlossen.\nDatei gespeichert unter:\n{out_path}")

    # ---------------- Single File Mode ----------------
    def analyze_single_file(self, file_path):
        self.analyze_folder(file_path)

    def show_result_window(self, file_path, kind, result_text):
        win = Toplevel(self.root)
        win.title(f"Analyse: {os.path.basename(file_path)}")
        win.geometry("800x600")

        Label(win, text=f"Type: {kind.capitalize()}", font=("Arial", 11, "bold")).pack(pady=5)
        Label(win, text=f"File: {file_path}", font=("Arial", 9)).pack(pady=2)

        text_area = Text(win, wrap="word")
        text_area.pack(fill=BOTH, expand=True, padx=10, pady=10)
        text_area.insert(END, result_text)
        text_area.config(state="disabled")

    # ---------------- Hilfsfunktionen ----------------
    def _save_video_frames(self, video_path, interval):
        """Speichert Frames als PNGs im gleichen Ordner."""
        from moviepy.video.io.VideoFileClip import VideoFileClip
        clip = VideoFileClip(video_path)
        base, _ = os.path.splitext(video_path)
        t = 0
        while t < clip.duration:
            frame = clip.get_frame(t)
            img = Image.fromarray(frame)
            seq = int(t / interval) + 1
            mmss = format_time2mmss(t).replace(":", "-")
            out_name = f"{base} - {mmss}.png"
            img.save(out_name)
            t += interval
        clip.close()

    def _save_transcript(self, file_path, text):
        """Speichert Transkript in .txt-Datei."""
        base, _ = os.path.splitext(file_path)
        txt_path = base + "_transkript.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    root = Tk()
    app = MediaAnalyzerGUI(root)
    root.mainloop()
