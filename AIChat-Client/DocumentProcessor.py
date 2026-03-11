import os
import re
import fitz  # install PyMuPDF, nicht fitz!
from docx import Document
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
# pip install pymupdf python-docx ebooklib beautifulsoup4 lxml

class DocumentProcessor:
    def __init__(self, max_chunk_chars=3500):
        self.max_chunk_chars = max_chunk_chars

    def file_to_markdown(self, file_path):
        """Extrahiert Text aus verschiedenen Formaten und gibt 'sauberes' Markdown zurück."""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()

        elif ext == '.pdf':
            text = ""
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text("text") + "\n\n"
            return text

        elif ext == '.docx':
            doc = Document(file_path)
            # Einfache Markdown-Konvertierung: Überschriften erkennen
            full_text = []
            for para in doc.paragraphs:
                if para.style.name.startswith('Heading'):
                    full_text.append(f"## {para.text}")
                else:
                    full_text.append(para.text)
            return "\n\n".join(full_text)

        elif ext == '.epub':
            try:
                book = epub.read_epub(file_path)
                chapters = []
                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_DOCUMENT:
                        chapters.append(item.get_content())

                text = ""
                for html_src in chapters:
                    soup = BeautifulSoup(html_src, 'lxml-xml')
                    # Wichtig: Text mit Leerzeichen trennen, damit Sätze nicht verkleben
                    text += soup.get_text(separator=' ') + "\n"

                if not text.strip():
                    log.error("EPUB extraktion ergab leeren Text")
                    return ""
                return text
            except Exception as e:
                log.error(f"EPUB Fehler: {e}")
                return ""

        else:
            raise ValueError(f"Dateiformat {ext} wird nicht unterstützt.")

    #
    # Wird nur noch vom main hier benutzt. Macht chunks ohne Überlappung
    #
    def create_chunks(self, text):
        """Teilt den Text in Chunks auf, ohne Absätze zu zerreißen."""
        # Wir trennen am doppelten Zeilenumbruch (typischer Absatz)
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Prüfen, ob der Absatz alleine schon zu lang ist
            if len(para) > self.max_chunk_chars:
                # Notfall-Option: Wenn ein einzelner Absatz zu lang ist,
                # müssen wir ihn leider hart an Satzenden trennen
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""

                # Hier könnte man noch eine Logik einbauen, die nach Sätzen (.) trennt
                # Für den Moment nehmen wir ihn als einen (zu großen) Chunk oder teilen ihn hart
                chunks.append(para[:self.max_chunk_chars])
                continue

            # Passt der neue Absatz noch in den aktuellen Chunk?
            if len(current_chunk) + len(para) + 2 <= self.max_chunk_chars:
                current_chunk += para + "\n\n"
            else:
                # Chunk voll -> speichern und neuen beginnen
                chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"

        # Den letzten Rest hinzufügen
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def create_smart_chunks(self, text, overlap_chars=0):
        chunks = []
        start = 0
        text_len = len(text)

        if text_len == 0:
            return []

        while start < text_len:
            end = start + self.max_chunk_chars
            if end >= text_len:
                # Letzter Chunk
                context = text[max(0, start - overlap_chars):start]
                chunks.append((context, text[start:].strip()))
                break

            # Suche Trenner (Satzende) im Fenster der letzten 500 Zeichen des Chunks
            search_window = text[end - 500:end]
            best_cut = -1
            for separator in ['. ', '! ', '? ', '.<', '.\n']:
                pos = search_window.rfind(separator)
                if pos > best_cut:
                    best_cut = pos

            # Wenn kein Satzzeichen gefunden wurde, nimm das Ende des Fensters
            actual_end = (end - 500) + best_cut + 1 if best_cut != -1 else end

            # Falls actual_end aus irgendeinem Grund nicht voranschreitet, erzwinge Fortschritt
            if actual_end <= start:
                actual_end = end

            context = text[max(0, start - overlap_chars):start]
            new_content = text[start:actual_end].strip()
            chunks.append((context, new_content))

            start = actual_end

        return chunks  # <--- WICHTIG: Die Variable muss hier stehen!

    def get_boundary_sentences(self, text, mode="last", count=2):
        """
        Liefert die ersten oder letzten N Sätze eines Strings zurück.
        mode: "first" oder "last"
        count: Anzahl der Sätze
        """
        if not text or not isinstance(text, str):
            return ""

        # Regex: Splittet bei . ! ? gefolgt von Leerzeichen oder Zeilenumbruch
        # Nutzt Lookbehind (?<=[...]), um das Satzzeichen nicht zu löschen
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())

        # Filtern: Nur Sätze mit Inhalt behalten
        sentences = [s.strip() for s in sentences if len(s.strip()) > 1]

        if mode == "first":
            selected = sentences[:count]
        else:
            selected = sentences[-count:]

        return " ".join(selected)

# --- Beispiel der Nutzung ---
if __name__ == "__main__":
    processor = DocumentProcessor(max_chunk_chars=4000)

    try:
        # Pfad zu deiner Testdatei
        file = "KGND.docx"
        markdown_text = processor.file_to_markdown(file)

        print(f"--- Extraktion abgeschlossen ({len(markdown_text)} Zeichen) ---")

        text_chunks = processor.create_chunks(markdown_text)

        for i, chunk in enumerate(text_chunks):
            print(f"\n--- CHUNK {i + 1} ({len(chunk)} Zeichen) ---")
            print(chunk[:100] + "...")  # Nur die ersten 100 Zeichen zur Vorschau

    except Exception as e:
        print(f"Fehler: {e}")

