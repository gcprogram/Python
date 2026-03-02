import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox
import requests
import json


class ChatApp:
    def __init__(self, master):
        self.master = master
        master.title("Chat mit KI")

        # Eingabefelder für IP und Port
        self.ip_label = tk.Label(master, text="IP-Adresse:")
        self.ip_label.pack()
        self.ip_entry = tk.Entry(master)
        self.ip_entry.pack()

        self.port_label = tk.Label(master, text="Port:")
        self.port_label.pack()
        self.port_entry = tk.Entry(master)
        self.port_entry.pack()

        self.token_label = tk.Label(master, text="API-Schlüssel:")
        self.token_label.pack()
        self.token_entry = tk.Entry(master, show="*")
        self.token_entry.pack()

        self.chat_area = scrolledtext.ScrolledText(master, wrap=tk.WORD, state='normal', width=50, height=20)
        self.chat_area.pack()

        self.user_input = tk.Entry(master, width=50)
        self.user_input.pack()

        self.send_button = tk.Button(master, text="Senden", command=self.send_message)
        self.send_button.pack()

        self.file_button = tk.Button(master, text="Datei hochladen", command=self.upload_file)
        self.file_button.pack()

    def chat_with_ai(self, message):
        api_key = self.token_entry.get()
        ip = self.ip_entry.get()
        port = self.port_entry.get()
        url = f"http://{ip}:{port}/api/v1/chat"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "message": message
        }
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            return response.json().get("reply", "Keine Antwort erhalten.")
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
            # Hier kannst du die Logik hinzufügen, um die Datei zu senden
            self.chat_area.insert(tk.END, f"Datei hochgeladen: {file_path}\n")
            # Füge hier die Logik zum Hochladen der Datei zur KI hinzu
            # z.B. self.send_file_to_ai(file_path)


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatApp(root)
    root.mainloop()
