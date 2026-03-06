import os
import fitz  # install PyMuPDF, nicht fitz!
from docx import Document
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
# pip install pymupdf python-docx ebooklib beautifulsoup4 lxml

class DocumentProcessor:
    def __init__(self, max_chunk_chars=6000):
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
            book = epub.read_epub(file_path)
            chapters = []
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    chapters.append(soup.get_text())
            return "\n\n".join(chapters)

        else:
            raise ValueError(f"Dateiformat {ext} wird nicht unterstützt.")

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

    # In DocumentProcessor.py hinzufügen/ersetzen:

    def create_smart_chunks(self, text, overlap_chars=300):
        """
        Erstellt Chunks, die an Satzenden orientiert sind und eine Überlappung besitzen.
        """
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            # Ende des Chunks bestimmen
            end = start + self.max_chunk_chars
            if end >= text_len:
                chunks.append(text[start:].strip())
                break

            # Suche nach dem besten Trenner (Satzende) innerhalb eines Suchfensters
            # Wir suchen rückwärts ab 'end'
            search_window = text[end - 500:end]  # Letzte 500 Zeichen vor dem harten Limit
            best_cut = -1
            for separator in ['. ', '! ', '? ', '\n']:
                pos = search_window.rfind(separator)
                if pos > best_cut:
                    best_cut = pos

            if best_cut != -1:
                actual_end = (end - 500) + best_cut + 1
            else:
                # Kein Satzzeichen? Nimm das letzte Leerzeichen
                actual_end = text.rfind(' ', start, end)
                if actual_end <= start:
                    actual_end = end  # Harter Schnitt als Notlösung

            chunks.append(text[start:actual_end].strip())

            # Überlappung für den nächsten Chunk
            # Wir gehen nicht zum Ende, sondern ein Stück zurück
            start = actual_end - overlap_chars
            # Sicherstellen, dass wir uns vorwärts bewegen
            if start < 0: start = 0
            if start <= chunks[-1].find(text[actual_end - overlap_chars:actual_end]):  # Verhindert Endlosschleifen
                start = actual_end

        return chunks
# --- Beispiel der Nutzung ---
if __name__ == "__main__":
    processor = DocumentProcessor(max_chunk_chars=6000)

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