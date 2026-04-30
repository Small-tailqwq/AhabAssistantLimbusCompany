"""Background scan worker — runs AssetLibraryModel.scan() on a QThread."""

from PySide6.QtCore import QThread, Signal


class ScanWorker(QThread):
    """Runs the heavy `model.scan()` on a background thread."""

    progress = Signal(int, int)  # current, total
    finished = Signal(object)  # diff result
    error = Signal(str)  # error message

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model

    def run(self):
        try:
            diff = self.model.scan(progress_callback=self._on_progress)
            self.finished.emit(diff)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, current: int, total: int):
        self.progress.emit(current, total)
