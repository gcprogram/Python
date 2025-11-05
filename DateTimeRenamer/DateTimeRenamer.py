import os
import re
import datetime
from tkinter import Tk, filedialog, ttk, Menu, messagebox

# Metadaten-Bibliotheken
from PIL import Image  # Für JPEGs/PNGs (Exif)
from mutagen.id3 import ID3  # Für WAVs (ID3-Tags)
from mutagen.mp4 import MP4  # Für MP4s
import exiftool  # Bester Allrounder, erfordert separate ExifTool-Installation!


class DateTimeRenamer:
    # Windows-kompatibles Format: YYYY-MM-DD HH.MM.SS
    DATE_FORMAT_STR = "%Y-%m-%d %H-%M-%S"
    # Regulärer Ausdruck, um das gesetzte Präfix zu erkennen
    DATE_PREFIX_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2} )")

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

    def __init__(self, master):
        self.master = master
        master.title("DateTimeRenamer")

        self.directory_path = None
        self.rename_mode = 'rename'  # 'rename' oder 'remove'
        self.file_list = []  # Speichert [(old_name, new_name, full_path, status)]

        self.setup_menu()
        self.setup_ui()

    # --- 1. Metadaten-Funktionen ---

    def get_date_from_metadata(self, filepath):
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
                                return datetime.strptime(date_value, self.DATE_FORMAT_STR)
                            except ValueError:
                                # Versuche, nur das Datum zu parsen
                                try:
                                    return datetime.strptime(date_value[:10], "%Y-%m-%d")
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
                    return datetime.strptime(date_str, "%Y-%m-%d %H-%M-%S")
            except:
                pass

        # 3. Fallback: Rückgabe des Dateisystem-Datums
        return fallback_date

    # --- 2. GUI-Setup und Logik ---

    def setup_menu(self):
        """Erstellt das Menü für die Modusauswahl."""
        menubar = Menu(self.master)
        self.master.config(menu=menubar)

        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Verzeichnis wählen", command=self.select_directory)
        menubar.add_cascade(label="Aktion", menu=file_menu)

        action_menu = Menu(menubar, tearoff=0)
        self.mode_var = self.rename_mode
        action_menu.add_command(label="1. Umbenennung (Datum hinzufügen)", command=lambda: self.set_mode('rename'))
        action_menu.add_command(label="2. Präfix entfernen", command=lambda: self.set_mode('remove'))
        menubar.add_cascade(label="Modus", menu=action_menu)

        self.master.bind("<F5>", lambda event: self.generate_preview())

    def set_mode(self, mode):
        """Setzt den Modus und aktualisiert die Vorschau."""
        self.rename_mode = mode
        if mode == 'rename':
            self.mode_label.config(text="Modus: ➡️ DATUM HINZUFÜGEN")
        else:
            self.mode_label.config(text="Modus: ⬅️ PRÄFIX ENTFERNEN")
        self.generate_preview()  # Neue Vorschau generieren

    def setup_ui(self):
        """Erstellt die Haupt-UI-Elemente."""
        # Top Frame für Status und Button
        top_frame = ttk.Frame(self.master, padding="10")
        top_frame.pack(fill='x')

        self.mode_label = ttk.Label(top_frame, text="Modus: ➡️ DATUM HINZUFÜGEN", font=('Arial', 10, 'bold'))
        self.mode_label.pack(side='left')

        self.dir_label = ttk.Label(top_frame, text="Verzeichnis: (noch nicht ausgewählt)")
        self.dir_label.pack(side='left', padx=10)

        # Treeview für die Vorschau
        tree_frame = ttk.Frame(self.master, padding="10")
        tree_frame.pack(fill='both', expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=("alt", "neu", "status"), show="headings")
        self.tree.heading("alt", text="Alter Dateiname (Original)")
        self.tree.heading("neu", text="Neuer Dateiname (Vorschau)")
        self.tree.heading("status", text="Status / Hinweis")
        self.tree.column("alt", width=300)
        self.tree.column("neu", width=300)
        self.tree.column("status", width=150)
        self.tree.pack(fill='both', expand=True)

        # Separator und Button
        ttk.Separator(self.master, orient='horizontal').pack(fill='x', padx=10, pady=5)

        button_frame = ttk.Frame(self.master, padding="10")
        button_frame.pack(fill='x')

        ttk.Button(button_frame, text="Vorschau aktualisieren (F5)", command=self.generate_preview).pack(side='left')
        self.rename_button = ttk.Button(button_frame, text="Änderungen AUSFÜHREN", command=self.execute_renaming,
                                        state='disabled')
        self.rename_button.pack(side='right')

    def select_directory(self):
        """Öffnet einen Dialog zur Auswahl des Verzeichnisses."""
        new_dir = filedialog.askdirectory(title="Wählen Sie das Verzeichnis")
        if new_dir:
            self.directory_path = new_dir
            self.dir_label.config(text=f"Verzeichnis: {os.path.basename(self.directory_path)}")
            self.generate_preview()

    def generate_preview(self):
        """Generiert die Liste der Umbenennungen (Vorschau) und füllt das Treeview."""
        if not self.directory_path:
            messagebox.showwarning("Achtung", "Bitte wählen Sie zuerst ein Verzeichnis aus.")
            return

        self.file_list = []
        self.tree.delete(*self.tree.get_children())
        can_rename = False

        for item_name in os.listdir(self.directory_path):
            full_path = os.path.join(self.directory_path, item_name)

            if os.path.isdir(full_path):
                continue

            match = self.DATE_PREFIX_PATTERN.match(item_name)
            original_name_without_prefix = item_name[len(match.group(0)):].strip() if match else item_name

            new_name = None
            status = "Keine Änderung"

            if self.rename_mode == 'rename':
                if match:
                    status = "Bereits umbenannt"
                    new_name = item_name
                else:
                    # Datum aus Metadaten oder Fallback holen
                    creation_date = self.get_date_from_metadata(full_path)

                    if creation_date:
                        date_prefix = creation_date.strftime(self.DATE_FORMAT_STR)
                        new_name = f"{date_prefix} {item_name}"
                        status = "Wird umbenannt"
                        can_rename = True
                    else:
                        status = "Kein Datum gefunden"
                        new_name = item_name

            elif self.rename_mode == 'remove':
                if match:
                    new_name = original_name_without_prefix
                    status = "Präfix entfernen"
                    can_rename = True
                else:
                    new_name = item_name
                    status = "Kein Präfix gefunden"

            if new_name and new_name != item_name:
                # Füge die Zeile zur Treeview hinzu (gelb für Änderungen)
                self.tree.insert("", "end", values=(item_name, new_name, status), tags=('change',))
                self.file_list.append((item_name, new_name, full_path, status))
            else:
                # Füge die Zeile zur Treeview hinzu (grau für keine Änderungen)
                self.tree.insert("", "end", values=(item_name, new_name, status), tags=('no_change',))

        # Styling für Treeview-Tags
        self.tree.tag_configure('change', background='#FFFFCC')  # Gelb für Änderung
        self.tree.tag_configure('no_change', background='#F0F0F0')  # Grau für keine Änderung

        # Button-Status aktualisieren
        self.rename_button.config(state='normal' if can_rename else 'disabled')

    def execute_renaming(self):
        """Führt die in der Vorschau generierten Umbenennungen tatsächlich aus."""
        if not self.file_list:
            messagebox.showwarning("Achtung", "Keine Umbenennungen in der Liste. Bitte zuerst Vorschau generieren.")
            return

        if not messagebox.askyesno("Bestätigung",
                                   f"Sind Sie sicher, dass Sie {len([f for f in self.file_list if f[1] != f[0]])} Dateien umbenennen möchten?"):
            return

        success_count = 0
        error_count = 0

        for old_name, new_name, full_path, status in self.file_list:
            if old_name != new_name:
                try:
                    new_full_path = os.path.join(self.directory_path, new_name)
                    os.rename(full_path, new_full_path)
                    success_count += 1
                except OSError as e:
                    print(f"Fehler beim Umbenennen von {old_name} zu {new_name}: {e}")
                    error_count += 1
                except Exception as e:
                    print(f"Unerwarteter Fehler: {e}")
                    error_count += 1

        # Nach der Ausführung die Vorschau neu laden
        self.generate_preview()

        if error_count == 0:
            messagebox.showinfo("Fertig", f"Umbenennung abgeschlossen: {success_count} Dateien erfolgreich geändert.")
        else:
            messagebox.showwarning("Fertig mit Fehlern",
                                   f"Umbenennung abgeschlossen: {success_count} erfolgreich, {error_count} Fehler.")


# --- Hauptausführung ---
if __name__ == "__main__":
    # Prüfe auf PyExifTool-Installation
    try:
        import exiftool
    except ImportError:
        messagebox.showerror("Fehler",
                             "Das 'pyexiftool'-Modul ist nicht installiert. Bitte 'pip install pyexiftool' ausführen.")
        exit()

    # Prüfe auf ExifTool-Anwendung (sehr schwierig zuverlässig in Python,
    # daher wird es oft beim ersten Aufruf in get_date_from_metadata fehlschlagen,
    # wenn es nicht im PATH ist.)

    root = Tk()
    app = DateTimeRenamer(root)
    root.mainloop()