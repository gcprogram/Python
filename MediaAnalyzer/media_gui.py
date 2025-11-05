# media_gui.py
import os
import sys
import threading
import subprocess
from datetime import datetime
import pandas as pd
from tkinter import (
    Tk, Frame, Button, Label, filedialog, ttk, messagebox, Text,
    Scrollbar, Checkbutton, IntVar, StringVar, Menu, Toplevel, END, BOTH, X, Y, RIGHT, BOTTOM, W
)
from tqdm import tqdm
from geopy.geocoders import Nominatim
from PIL import Image, ImageTk
from caption_tools import DescriptionGenerator
from media_tools import get_exif_data, get_video_metadata

MEDIA_EXT = {
    ".jpg": "image", ".jpeg": "image", ".png": "image",
    ".mp4": "video", ".mov": "video", ".avi": "video",
    ".wav": "audio", ".mp3": "audio", ".m4a": "audio", ".flac": "audio"
}


class MediaAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🧭 Reise-Medien Analyse")
        self.root.geometry("1200x750")

        self.create_menu()
        self.create_top_controls()
        self.create_table()

        self.captioner = None
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
        self.model_menu.grid(row=0, column=1, padx=5)

        # --- Zeile 1b: Analyse-Intervall ---
        Label(config_frame, text="⏱ Video Analyse-Intervall (Sek.):", font=("Arial", 11)).grid(row=0, column=2, sticky=W, padx=15)
        self.interval_var = StringVar(value="10")
        ttk.Entry(config_frame, textvariable=self.interval_var, width=6).grid(row=0, column=3, padx=5)

        # --- Zeile 2: Optionen ---
        Label(config_frame, text="⚙️ Optionen:", font=("Arial", 11)).grid(row=1, column=0, sticky=W, padx=5, pady=(5,0))
        self.save_frames_var = IntVar(value=0)
        self.save_transcript_var = IntVar(value=0)
        Checkbutton(config_frame, text="Frames speichern", variable=self.save_frames_var).grid(row=1, column=1, sticky=W)
        Checkbutton(config_frame, text="Transkripte speichern", variable=self.save_transcript_var).grid(row=1, column=2, sticky=W)

        # --- Zeile 3: Ordnerwahl ---
        Label(config_frame, text="📂 Wähle einen Ordner:", font=("Arial", 11)).grid(row=2, column=0, sticky=W, padx=5, pady=(10,0))
        Button(config_frame, text="Ordner auswählen", command=self.choose_folder).grid(row=2, column=1, padx=5, pady=(10,0))

        # Fortschritt
        self.progress = ttk.Progressbar(config_frame, orient="horizontal", length=400, mode="determinate")
        self.progress.grid(row=2, column=2, padx=20, pady=(10,0))
        self.status_label = Label(config_frame, text="", font=("Arial", 10))
        self.status_label.grid(row=2, column=3, sticky=W, pady=(10,0))

    # ---------------- Tabelle ----------------
    def create_table(self):
        table_frame = Frame(self.root)
        table_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        cols = ("Datei", "Typ", "Datum", "Ort", "Lat", "Lon", "Dauer", "Beschreibung", "Transkript")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=20)
        for col in cols:
            self.tree.heading(col, text=col)
            width = {"Datei": 250, "Beschreibung": 250, "Transkript": 250}.get(col, 100)
            self.tree.column(col, width=width, anchor="w")

        vsb = Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.tree.pack(fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)
        hsb.pack(side=BOTTOM, fill=X)

    # ---------------- Analyse ----------------
    def choose_folder(self):
        folder = filedialog.askdirectory(title="Verzeichnis wählen")
        if folder:
            threading.Thread(target=self.analyze_folder, args=(folder,), daemon=True).start()

    def choose_single_file(self):
        file = filedialog.askopenfilename(
            title="Datei wählen",
            filetypes=[("Medien", "*.jpg *.jpeg *.png *.mp4 *.mov *.avi *.mp3 *.wav *.m4a *.flac"), ("Alle Dateien", "*.*")]
        )
        if file:
            threading.Thread(target=self.analyze_single_file, args=(file,), daemon=True).start()

    def analyze_folder(self, folder):
        self.status_label.config(text="📦 Lade KI-Modelle...")
        self.root.update_idletasks()

        whisper_choice:StringVar = self.model_var.get()
        self.captioner = DescriptionGenerator(audio_model_size=whisper_choice)
        interval = int(self.interval_var.get())

        records = []
        all_files = [os.path.join(root, f) for root, _, files in os.walk(folder) for f in files]
        total = len(all_files)
        self.progress["maximum"] = total
        self.status_label.config(text=f"🔍 Analysiere {total} Dateien...")

        self.tree.delete(*self.tree.get_children())

        for i, path in enumerate(tqdm(all_files, desc="Analysiere")):
            ext = os.path.splitext(path)[1].lower()
            if ext not in MEDIA_EXT:
                self.progress["value"] = i + 1
                continue
            kind = MEDIA_EXT[ext]
            relpath = os.path.relpath(path, folder)
            rec = {"Datei": relpath, "Typ": kind.capitalize(), "Datum": "", "Ort": "", "Lat": "", "Lon": "", "Dauer": "", "Beschreibung": "", "Transkript": ""}
            cap_text = ""
            try:
                if kind == "image":
                    exif = get_exif_data(path)
                    rec["Datum"] = exif.get("Date", "")
                    rec["Lat"], rec["Lon"] = exif.get("Lat", ""), exif.get("Lon", "")
                    cap_text = self.captioner.generate_caption(path)
                    rec["Beschreibung"] = cap_text
                elif kind == "video":
                    meta = get_video_metadata(path)
                    rec["Datum"], rec["Lat"], rec["Lon"] = meta.get("Date", ""), meta.get("Lat", ""), meta.get("Lon", "")
                    rec["Dauer"] = meta.get("duration", "")
                    cap_text = self.captioner.summarize_video_with_frames(
                        path,
                        interval=interval
                    )
                    rec["Beschreibung"] = cap_text
                    rec["Transkript"] = self.captioner.transcribe_audio(path)
                    if self.save_frames_var.get():
                        self._save_video_frames(path, interval)
                    if self.save_transcript_var.get():
                        self._save_transcript(path, rec["Transkript"] + "\n\n" + cap_text.translate(str.maketrans("|", '\n')))

                elif kind == "audio":
                    textfile = path + ".txt"
                    result = self.captioner.transcribe_audio(path)
                    rec["Beschreibung"] = result
                    if self.save_transcript_var.get():
                        with open(textfile, "w", encoding="utf-8") as f:
                            f.write(result.get("text", ""))
            except Exception as e:
                print("⚠️ Fehler bei:", path, e)

            records.append(rec)
            self.tree.insert("", "end", values=tuple(rec.values()))
            self.progress["value"] = i + 1
            self.root.update_idletasks()

        df = pd.DataFrame(records)
        out_path = os.path.join(folder, "_media_analysis.csv")
        df.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig")
        self.status_label.config(text=f"✅ Fertig → {out_path}")
        messagebox.showinfo("Fertig", f"Analyse abgeschlossen.\nDatei gespeichert unter:\n{out_path}")

    # ---------------- Single File Mode ----------------
    def analyze_single_file(self, file_path):
        whisper_choice:StringVar = self.model_var.get()
        interval = int(self.interval_var.get())
        self.captioner = DescriptionGenerator(audio_model_size=whisper_choice)

        ext = os.path.splitext(file_path)[1].lower()
        kind = MEDIA_EXT.get(ext, "unknown")
        records = []
        rec = {"Datei": os.path.basename(file_path), "Typ": kind.capitalize(), "Datum": "", "Ort": "", "Lat": "", "Lon": "", "Dauer": "",
               "Beschreibung": "", "Transkript": ""}

        result_text = ""
        cap_text = ""
        audio_text = ""
        try:
            if kind == "image":
                exif = get_exif_data(file_path)
                rec["Datum"] = exif.get("Date", "")
                rec["Lat"], rec["Lon"] = exif.get("Lat", ""), exif.get("Lon", "")
                cap_text = self.captioner.generate_caption(file_path)
                if self.save_transcript_var.get():
                    self._save_transcript(file_path, cap_text.translate(str.maketrans("|", '\n')))
            elif kind == "video":
                meta = get_video_metadata(file_path)
                rec["Datum"], rec["Lat"], rec["Lon"] = meta.get("Date", ""), meta.get("Lat", ""), meta.get("Lon", "")
                rec["Dauer"] = meta.get("duration", "")
                cap_text = self.captioner.summarize_video_with_frames(file_path, interval=interval)
                audio_text = self.captioner.transcribe_audio(file_path)
                rec["Transkript"] = audio_text
                if self.save_frames_var.get():
                    self._save_video_frames(file_path, interval)
                if self.save_transcript_var.get():
                    self._save_transcript(file_path, audio_text + "\n\n" + cap_text.translate(str.maketrans("|", '\n')))
            elif kind == "audio":
                audio_text = self.captioner.transcribe_audio(file_path).strip()
                rec["Transkript"] = audio_text
                if audio_text:
                    audio_text = "Kein Transkript verfügbar."
                if self.save_transcript_var.get():
                    self._save_transcript(file_path, audio_text)

            rec["Transkript"] = audio_text
            rec["Beschreibung"] = cap_text
            text = audio_text + "\n\n" + cap_text.translate(str.maketrans("|", '\n'))
            self.show_result_window(file_path, kind, text)

        except Exception as e:
            print("⚠️ Fehler bei:", file_path, e)
        records.append(rec)
        self.tree.insert("", "end", values=tuple(rec.values()))


    def show_result_window(self, file_path, kind, result_text):
        win = Toplevel(self.root)
        win.title(f"Analyse: {os.path.basename(file_path)}")
        win.geometry("800x600")

        Label(win, text=f"Typ: {kind.capitalize()}", font=("Arial", 11, "bold")).pack(pady=5)
        Label(win, text=f"Datei: {file_path}", font=("Arial", 9)).pack(pady=2)

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
            out_name = f"{base} - {seq:04d}.png"
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
