from PyQt6.QtCore import QObject, QEvent
from PyQt6 import QtCore


class EscFilter(QObject):
    def __init__(self, window):
        super().__init__()
        self.window = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Escape:
                self.window.exit_fullscreen()
                return True
        return False
