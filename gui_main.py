#!/usr/bin/env python3
# gui_main.py
import sys
import os
import platform
import ctypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor
from ui.main_window import GNSSMonitorWindow

def main():

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = QPalette()

    # Background
    palette.setColor(QPalette.ColorRole.Window, QColor(250, 250, 250))
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))

    # Text
    palette.setColor(QPalette.ColorRole.WindowText, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.Text, QColor(20, 20, 20))

    # Button
    palette.setColor(QPalette.ColorRole.Button, QColor(245, 245, 245))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(30, 30, 30))

    # Highlight (Blue accent color)
    palette.setColor(QPalette.ColorRole.Highlight, QColor(52, 125, 255)) 
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

    app.setPalette(palette)
    
    font = app.font()
    font.setFamily("Microsoft YaHei")
    font.setPointSize(9) 
    app.setFont(font)

    window = GNSSMonitorWindow()
    window.show()
    
    sys.exit(app.exec())
if __name__ == "__main__":
    main()