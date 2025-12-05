#!/usr/bin/env python3
# gui_main.py
import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from ui.main_window import GNSSMonitorWindow

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = GNSSMonitorWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()