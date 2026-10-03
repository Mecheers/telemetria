from PyQt6 import QtWidgets, QtGui
from app.ui.main_window import MainWindow


def main():
    app = QtWidgets.QApplication([])

    # Fijar explícitamente una fuente con tamaño válido.
    # En Windows/Qt algunas fuentes heredadas pueden informar pointSize() = -1
    # cuando fueron definidas originalmente en píxeles. Algunos widgets intentan
    # reutilizar ese valor mediante QFont.setPointSize(), generando:
    # QFont::setPointSize: Point size <= 0 (-1)
    app_font = QtGui.QFont("Segoe UI", 10)
    app.setFont(app_font)

    w = MainWindow()
    # Si tu PC tiene problemas con OpenGL en fullscreen, comentá la línea de abajo y usá showMaximized()
    w.showFullScreen()
    # w.showMaximized()
    app.exec()
