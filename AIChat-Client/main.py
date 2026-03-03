import tkinter as tk
from contextlib import nullcontext
from tkinter import scrolledtext, filedialog, messagebox, StringVar, OptionMenu, ttk
import time
import requests
import json
import os
import threading
import logging
from DocumentProcessor import DocumentProcessor # Verarbeitung von Dokumenten für Übersetzungen

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

CONFIG_FILE = "config.json"


class ChatApp:
    def __init__(self, master):
        self.model_menu = None
        self.master = master
        master.title("Chat mit KI")

        # Einstellungen button
        self.settings_button = tk.Button(master, text="Einstellungen", command=self.open_settings)
        self.settings_button.pack()

        self.chat_area = scrolledtext.ScrolledText(master, wrap=tk.WORD, state='normal')
        self.chat_area.pack(expand=True, fill='both')

        self.user_input = tk.Entry(master)
        self.user_input.pack(fill='x')

        self.send_button = tk.Button(master, text="Senden", command=self.send_message)
        self.send_button.pack()

        self.file_button = tk.Button(master, text="Datei hochladen", command=self.upload_file)
        self.file_button.pack()

        # Konfigurationsparameter
        self.api_key = ""
        self.ip = ""
        self.port = ""
        self.model = ""
        self.models = []
        self.menu_options = []
        self.response_id = ""
        # Tags für die Formatierung definieren
        self.chat_area.tag_configure("reasoning", background="#f5f5f5", foreground="#666666")
        self.chat_area.tag_configure("message", background="#e0e0e0", foreground="black")
        self.chat_area.tag_configure("bold", font=("Arial", 10, "bold"))

        # In __init__ nach self.chat_area.tag_configure...

        # Style für die Progressbar definieren
        self.style = ttk.Style()
        self.style.theme_use('default')
        self.style.configure("green.Horizontal.TProgressbar", foreground='green', background='green')
        self.style.configure("red.Horizontal.TProgressbar", foreground='red', background='red')

        # Status-Frame ganz unten
        self.status_frame = tk.Frame(master, bd=1, relief=tk.SUNKEN)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_var = tk.StringVar(value="Bereit")
        self.status_label = tk.Label(self.status_frame, textvariable=self.status_var, anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, padx=5)

        self.progress = ttk.Progressbar(self.status_frame, orient=tk.HORIZONTAL, length=150, mode='determinate',
                                        style="green.Horizontal.TProgressbar")
        self.progress.pack(side=tk.RIGHT, padx=5, pady=2)

        # Status-Bar ganz unten hinzufügen
        #self.status_var = tk.StringVar(value="Bereit")
        #self.status_label = tk.Label(master, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        #self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.last_type = None  # Merken, was zuletzt ausgegeben wurde
        # Übersetzer aktivieren
        self.processor = DocumentProcessor(max_chunk_chars=6000)

        # Standard-Prompts (könnten auch in die Config)
        self.translation_prompt = "Du bist ein professioneller Übersetzer für [Zielsprache]. Beachte den Stil: [Formell/Informell]. Fachbegriffe: [Glossar]."
        self.glossary = ""

        # UI Element für den Prompt (vereinfacht als Attribut,
        # könnte man in ein Textfeld in der GUI auslagern)
        self.system_instructions = tk.StringVar(value=self.translation_prompt)
        # Konfigurationsdatei laden
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                self.api_key = config.get("api_key", "")
                self.ip = config.get("ip", "")
                self.port = config.get("port", "")
                self.model = config.get("model", "")
                self.models = config.get("models", [])

    def open_settings(self):
        settings_window = tk.Toplevel(self.master)
        settings_window.title("Einstellungen")

        # IP-Adresse
        tk.Label(settings_window, text="IP-Adresse:").grid(row=0, column=0, padx=10, pady=5, sticky='e')
        self.ip_entry = tk.Entry(settings_window)
        self.ip_entry.insert(0, self.ip)  # Eintrag mit aktuellem Wert vorbelegen
        self.ip_entry.grid(row=0, column=1, padx=10, pady=5)

        # Port
        tk.Label(settings_window, text="Port:").grid(row=1, column=0, padx=10, pady=5, sticky='e')
        self.port_entry = tk.Entry(settings_window)
        self.port_entry.insert(0, self.port)  # Eintrag mit aktuellem Wert vorbelegen
        self.port_entry.grid(row=1, column=1, padx=10, pady=5)

        # API-Schlüssel
        tk.Label(settings_window, text="API-Schlüssel:").grid(row=2, column=0, padx=10, pady=5, sticky='e')
        self.token_entry = tk.Entry(settings_window, show="*")
        self.token_entry.insert(0, self.api_key)  # Eintrag mit aktuellem Wert vorbelegen
        self.token_entry.grid(row=2, column=1, padx=10, pady=5)

        if self.ip and self.port and self.api_key:
            self.load_models()

        # Modell
        tk.Label(settings_window, text="Modell:").grid(row=3, column=0, padx=10, pady=5, sticky='e')
        self.model_var = tk.StringVar(settings_window)
        self.model_var.set(self.model)  # Vorbelegen des aktuellen Modells
        # Falls die Liste leer sein könnte, einen Standardwert setzen
        menu_options = self.models
        if not self.models:
            menu_options = ["Keine Modelle verfügbar"]
        self.model_menu = tk.OptionMenu(settings_window, self.model_var, *menu_options)
        self.model_menu.grid(row=3, column=1, padx=10, pady=5)

        # Modelle laden Button
        self.load_models_button = tk.Button(settings_window, text="Modelle laden", command=self.load_models)
        self.load_models_button.grid(row=4, column=0, padx=10, pady=5)

        # Speichern Button
        self.save_button = tk.Button(settings_window, text="Speichern", command=self.save_settings)
        self.save_button.grid(row=4, column=1, padx=10, pady=5)

    def load_models(self):
        log.info("> load_models()")
        try:
            # 1. Daten abrufen (Beispielhaft via Requests)
            # Ersetze die URL durch deine tatsächliche API-Endpunkt-URL
            # response = requests.get(f"http://{self.ip}:{self.port}/v1/models")
            # data = response.json()
            data = self.get_models()
            log.info(f"Modelle stehen zur Verfügung: {data}")

            # 2. Die "key"-Elemente extrahieren
            log.info(f"{data}")
            # Nur hinzufügen, wenn der Key "key" auch wirklich existiert
            self.models = [model["key"] for model in data if "key" in model]
            log.info(f"keys: {self.models}")

            # 3. Das OptionMenu-Widget aktualisieren
            menu = self.model_menu["menu"]
            menu.delete(0, "end")  # Alte Einträge entfernen

            for model_key in self.models:
                # Hier fügen wir jeden Key hinzu und sorgen dafür,
                # dass beim Klick die model_var gesetzt wird
                menu.add_command(
                    label=model_key,
                    command=lambda value=model_key: self.model_var.set(value)
                )

            # 4. Optional: Den ersten Eintrag automatisch auswählen, falls nichts selektiert ist
            if self.models and not self.model_var.get():
                self.model_var.set(self.models[0])

            log.info(f"{len(self.models)} Modelle erfolgreich geladen.")
            log.info("< load_models()")

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Laden der Modellliste: {e}")
            log.error("< load_models()")

    def get_models(self):
        log.info("> get_models()")
        url = f"http://{self.ip}:{self.port}/api/v1/models"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                log.info("< get_models()")
                return response.json().get("models", [])
            else:
                log.error("< get_models(): Falscher Statuswert bei Laden der Modellliste.")
                self.master.after(0, lambda: [
                    self.status_var.set("Falscher Statuswert bei Laden der Modellliste"),
                    self.progress.configure(style="red.Horizontal.TProgressbar", value=100)
                ])
                return []
        except Exception as e:
                err_short = str(e)[:40] + "..." if len(str(e)) > 40 else str(e)
                self.master.after(0, lambda: [
                    self.status_var.set(f"< get_models(): {err_short}"),
                    self.progress.configure(style="red.Horizontal.TProgressbar", value=100)
                ])

    def save_settings(self):
        log.info("> save_settings()")
        self.api_key = self.token_entry.get()
        self.ip = self.ip_entry.get()
        self.port = self.port_entry.get()
        self.model = self.model_var.get()

        config = {
            "api_key": self.api_key,
            "ip": self.ip,
            "port": self.port,
            "model": self.model,
            "models": self.models
        }
        self.response_id = "" # start new Chat when saving
        self.chat_area.delete("1.0", tk.END)

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)

        log.info("Einstellungen gespeichert.")
        log.info("< save_settings()")

    def chat_with_ai(self, message):
        log.info(f"> chat_with_ai() gestartet für Modell: {self.model}")
        url = f"http://{self.ip}:{self.port}/api/v1/chat"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Sicherstellen, dass die Payload so aussieht, wie die API sie braucht.
        # Falls es ein OpenAI-kompatibler Endpunkt ist, müsste es 'messages' sein.
        payload = {
            "input": message,  # Beibehalten, falls deine API das so braucht
            "model": self.model,
            "stream": True
        }

        if self.response_id:
            payload["previous_response_id"] = self.response_id

        try:
            # 1. Timeout hinzugefügt (10 Sek auf Verbindung, None auf Stream)
            log.info(f"Sende Request an {url}...")
            response = requests.post(url, headers=headers, json=payload, stream=True, timeout=(10, None))

            # 2. Sofort den Status loggen!
            log.info(f"Response erhalten: Status {response.status_code}")

            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8').strip()
                        if decoded_line.startswith("data: "):
                            json_str = decoded_line[6:]
                            # Innerhalb der for-Schleife in chat_with_ai:
                            try:
                                chunk = json.loads(json_str)
                                chunk_type = chunk.get("type", "")

                                # FALL 1: Modell lädt noch (Progress-Anzeige)
                                if chunk_type == "model_load.progress":
                                    p_value = chunk.get("progress", 0)

                                    if self.load_start_time is None:
                                        self.load_start_time = time.time()

                                    # Berechnung der Restzeit
                                    elapsed = time.time() - self.load_start_time
                                    if p_value > 0:
                                        total_estimated_time = elapsed / p_value
                                        remaining_time = max(0, total_estimated_time - elapsed)
                                        time_str = f"{int(remaining_time)}s verbleibend"
                                    else:
                                        time_str = "Berechne..."

                                    def update_p(v=p_value, t=time_str):
                                        self.progress["value"] = v * 100
                                        self.progress["style"] = "green.Horizontal.TProgressbar"
                                        self.status_var.set(f"Modell lädt... ({t})")

                                    self.master.after(0, update_p)

                                # FALL 2: Laden beendet / Prompt-Verarbeitung
                                elif chunk_type == "model_load.end":
                                    self.load_start_time = None  # Reset für nächstes Mal
                                    self.master.after(0, lambda: [self.status_var.set("Modell bereit."),
                                                                  self.progress.configure(value=100)])


                                # FALL 3: Echtes Streaming (Reasoning / Message)
                                # Delta-Events für Reasoning und Message (wie besprochen)
                                elif ".delta" in chunk_type:
                                    # Status-Bar zurücksetzen, wenn die erste Antwort kommt
                                    if self.status_var.get() != "KI schreibt...":
                                        self.master.after(0, lambda: self.status_var.set("KI schreibt..."))
                                    item = {
                                        "type": chunk_type.split(".")[0],
                                        "content": chunk.get("content", "")
                                    }
                                    self.master.after(0, self._update_chat_ui, item)

                                # Ende des Chats
                                elif chunk_type == "chat.end":
                                    self.master.after(0, lambda: self.status_var.set("Bereit"))

                            except json.JSONDecodeError:
                                continue
            else:
                err_msg = f"Server Fehler: {response.status_code} - {response.text}"
                log.error(err_msg)
                self.master.after(0, lambda: self.chat_area.insert(tk.END, f"\n{err_msg}\n"))

        except requests.exceptions.Timeout:
            log.error("Timeout: Der Server antwortet nicht schnell genug.")
            self.master.after(0, lambda: self.chat_area.insert(tk.END,
                                                               "\nFehler: Verbindung zum Server zeitüberschreitung.\n"))
        except Exception as e:
            err_short = str(e)[:40] + "..." if len(str(e)) > 40 else str(e)
            self.master.after(0, lambda: [
                self.status_var.set(f"Verbindungsfehler: {err_short}"),
                self.progress.configure(style="red.Horizontal.TProgressbar", value=100)
            ])

    def _update_chat_ui(self, item):
        content_type = item.get("type")
        content_text = item.get("content", "")

        if not content_text:
            return

        # Spezialbehandlung für den Ladevorgang
        if content_type == "loading":
            # Wir löschen die letzte Zeile nicht (kompliziert in Tkinter),
            # aber wir markieren es als Systemnachricht
            if self.last_type != "loading":
                self.chat_area.insert(tk.END, "\n")
                self.last_type = "loading"

            # Cursor an den Anfang der Zeile setzen ist im Text-Widget schwierig,
            # daher hängen wir es hier einfach an oder nutzen ein Label.
            # Für den Anfang reicht eine einfache Statuszeile:
            self.chat_area.insert(tk.END, content_text)
            self.chat_area.see(tk.END)
            return

        # Rest der Logik für Reasoning und Message...
        if content_type != self.last_type:
            # Zeilenumbruch vor neuem Block, außer ganz am Anfang
            if self.last_type is not None:
                self.chat_area.insert(tk.END, "\n")

            header = "Reasoning:\n" if content_type == "reasoning" else "KI:\n"
            tag = "reasoning" if content_type == "reasoning" else "message"

            self.chat_area.insert(tk.END, header, (tag, "bold"))
            self.last_type = content_type

        # Den Text-Schnipsel mit dem richtigen Tag (Farbe) einfügen
        tag = "reasoning" if content_type == "reasoning" else "message"
        self.chat_area.insert(tk.END, content_text, tag)

        # Sofort zum Ende scrollen
        self.chat_area.see(tk.END)

    def send_message(self):
        log.info("> send_message(): sending message")
        user_message = self.user_input.get()
        if not user_message:
            return

        self.chat_area.insert(tk.END, f"Du: {user_message}\n")
        self.user_input.delete(0, tk.END)
        self.last_type = None  # Reset für die neue Antwort

        # Thread starten, damit die GUI flüssig bleibt
        threading.Thread(target=self.chat_with_ai, args=(user_message,), daemon=True).start()
        log.info("< send_message(): after threading started")

    def upload_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Dokumente", "*.txt *.pdf *.docx *.epub")]
        )
        if not file_path:
            return

        # Startet die Pipeline in einem eigenen Thread, um die GUI nicht zu blockieren
        threading.Thread(target=self.process_translation_pipeline, args=(file_path,), daemon=True).start()

    def process_translation_pipeline(self, file_path):
        try:
            self.master.after(0, lambda: self.status_var.set("Extrahiere Text..."))
            markdown_text = self.processor.file_to_markdown(file_path)

            # 1. Chunks erstellen
            self.processor.max_chunk_chars = 4000  # Beispielwert für Übersetzung
            chunks = self.processor.create_chunks(markdown_text)

            self.master.after(0, lambda: self.chat_area.insert(tk.END,
                                                               f"\n[System]: Dokument geladen. {len(chunks)} Chunks erstellt.\n"))

            # 2. Glossar erstellen (Optionaler Schritt)
            self.master.after(0, lambda: self.status_var.set("Erstelle Glossar..."))
            # Wir nehmen den ersten Chunk für das Glossar (reicht oft aus)
            self.glossary = self.generate_glossary(chunks[0])
            self.master.after(0, lambda: self.chat_area.insert(tk.END, f"[Glossar]: {self.glossary}\n"))

            # 3. Übersetzung mit Kontext-Fenster
            previous_context = ""
            for i, chunk in enumerate(chunks):
                self.master.after(0, lambda: self.status_var.set(f"Übersetze Chunk {i + 1}/{len(chunks)}..."))

                # Prompt zusammenbauen
                full_prompt = (
                    f"ANWEISUNG: {self.system_instructions.get()}\n\n"
                    f"GLOSSAR (strikt einhalten):\n{self.glossary}\n\n"
                    f"KONTEXT (vorheriger Abschnitt, nicht übersetzen):\n...{previous_context}\n\n"
                    f"TEXT ZUM ÜBERSETZEN:\n{chunk}"
                )

                # Wir nutzen die bestehende chat_with_ai Logik,
                # müssen aber warten, bis ein Chunk fertig ist.
                # Dafür brauchen wir eine kleine Anpassung (Helper-Funktion).
                translated_chunk = self.send_sync_request(full_prompt)

                # Die letzten 200 Zeichen als Kontext für den nächsten Chunk merken
                previous_context = chunk[-200:] if len(chunk) > 200 else chunk

                self.master.after(0, lambda: self.status_var.set("Bereit"))

        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("Fehler", f"Pipeline Fehler: {str(e)}"))

    def generate_glossary(self, text_sample):
        """Fragt die KI nach den wichtigsten Begriffen."""
        prompt = f"Extrahiere ein Glossar der wichtigsten Fachbegriffe und Eigennamen aus diesem Text für eine Übersetzung. Antworte kurz im Format: Begriff: Übersetzung.\n\nText:\n{text_sample[:2000]}"
        return self.send_sync_request(prompt)

    def send_sync_request(self, prompt):
        """Hilfsfunktion: Sendet Request und wartet auf die komplette Antwort (blockierend im Thread)."""
        url = f"http://{self.ip}:{self.port}/api/v1/chat"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"input": prompt, "model": self.model, "stream": False}  # Stream aus für einfachere Logik hier

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            if response.status_code == 200:
                data = response.json()
                # Hier musst du den Pfad zum Content anpassen, je nach deiner API-Antwort-Struktur
                result = data.get("content", "Fehler beim Abrufen der Antwort")

                # UI Update im Hauptthread
                self.master.after(0, lambda: self._update_chat_ui(
                    {"type": "message", "content": f"\n--- Übersetzung Chunk ---\n{result}\n"}))
                return result
            return "Fehler"
        except Exception as e:
            return f"Fehler: {str(e)}"

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatApp(root)
    root.geometry("500x600")  # Fenstergröße setzen
    root.mainloop()
