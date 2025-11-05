import threading
import time
import queue # Für eine robustere Kommunikation (optional, aber gute Praxis)
import picutil

def long_task_function(self):
    picutils.create_thumbnail_db(self.db_path, self.size, self.update_progress, self.log_message)


def start_long_task_thread(self):

    # Erstellen eines neuen Threads.
    # daemon=True bedeutet, dass der Thread automatisch beendet wird,
    # wenn das Hauptprogramm (und damit der Tkinter-Loop) beendet wird.
    self.worker_thread = threading.Thread(target=self.long_task_function, daemon=True)
    self.worker_thread.start()


