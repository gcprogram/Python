import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, StringVar, OptionMenu
import requests
import json
import os

CONFIG_FILE = "config.json"


class ChatApp:
    def __init__(self, master):
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

        # Speichern Button
        self.save_button = tk.Button(settings_window, text="Speichern", command=self.save_settings)
        self.save_button.grid(row=3, column=0, padx=10, pady=5)

        # Modell
        tk.Label(settings_window, text="Modell:").grid(row=4, column=0, padx=10, pady=5, sticky='e')
        self.model_var = tk.StringVar(settings_window)
        self.model_var.set(self.model)  # Vorbelegen des aktuellen Modells
        # Falls die Liste leer sein könnte, einen Standardwert setzen
        menu_options = self.models
        if not self.models:
            menu_options = ["Keine Modelle verfügbar"]
        self.model_menu = tk.OptionMenu(settings_window, self.model_var, *menu_options)
        self.model_menu.grid(row=4, column=1, padx=10, pady=5)

        # Modelle laden Button
        self.load_models_button = tk.Button(settings_window, text="Modelle laden", command=self.load_models)
        self.load_models_button.grid(row=5, column=0, padx=10, pady=5)

        # Speichern Button
        #self.save_button = tk.Button(settings_window, text="Speichern", command=self.save_settings)
        #self.save_button.grid(row=5, column=0, padx=10, pady=5)

    def load_models(self):
        try:
            # 1. Daten abrufen (Beispielhaft via Requests)
            # Ersetze die URL durch deine tatsächliche API-Endpunkt-URL
            # response = requests.get(f"http://{self.ip}:{self.port}/v1/models")
            # data = response.json()
            data = self.get_models()
            print(f"Modelle stehen zur Verfügung: {data}")

            # 2. Die "key"-Elemente extrahieren
            print(f"{data}")
            # Nur hinzufügen, wenn der Key "key" auch wirklich existiert
            self.models = [model["key"] for model in data if "key" in model]
            print(f"keys: {self.models}")

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

            print(f"{len(self.models)} Modelle erfolgreich geladen.")

        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Laden der Modelle: {e}")

    def get_models(self):
        url = f"http://{self.ip}:{self.port}/api/v1/models"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.json().get("models", [])
            else:
                print("get_models(): Falscher Statuswert bei Laden der Modell.")
                return []
        except Exception as e:
            print("get_models(): Exception {e}")

    def save_settings(self):
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

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)

        messagebox.showinfo("Erfolg", "Einstellungen gespeichert.")
        self.load_models()

    def chat_with_ai(self, message):
        url = f"http://{self.ip}:{self.port}/api/v1/chat"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": message,
            "model": self.model,
        }
        if self.response_id:
            payload = {
                "input": message,
                "model": self.model,
                "previous_response_id": self.response_id
            }
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            print(f"Response: {response.json()}")
            data = response.json()
            # Wir greifen auf "output" zu, nehmen das erste Element [0] und daraus den "content"
            self.response_id = data.get("response_id")
            print("response_id={self.response_id}")
            return data.get("output", [{}])[0].get("content", "Keine Antwort erhalten.")
        else:
            return f"Fehler ({response.status_code}): {response.text}"

    def send_message(self):
        user_message = self.user_input.get()
        if not user_message:
            return

        self.chat_area.insert(tk.END, f"Du: {user_message}\n")
        ai_reply = self.chat_with_ai(user_message)
        self.chat_area.insert(tk.END, f"KI: {ai_reply}\n")
        self.user_input.delete(0, tk.END)

    def upload_file(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            self.chat_area.insert(tk.END, f"Datei hochgeladen: {file_path}\n")
            # Hier kannst du die Logik für das Hochladen der Datei einfügen.


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatApp(root)
    root.geometry("500x600")  # Fenstergröße setzen
    root.mainloop()
