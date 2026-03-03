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