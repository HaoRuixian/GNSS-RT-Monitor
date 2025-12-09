# ui/dialogs.py
import importlib.util
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QGroupBox, QFormLayout, 
                             QLineEdit, QCheckBox, QHBoxLayout, QPushButton, 
                             QFileDialog, QMessageBox, QStyle)
from PyQt6.QtGui import QIcon

class ConfigDialog(QDialog):
    def __init__(self, parent=None, initial_settings=None):
        super().__init__(parent)
        self.setWindowTitle("NTRIP Settings")
        self.resize(400, 400)
        self.settings = initial_settings or {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # OBS
        grp = QGroupBox("Observation Stream")
        fl = QFormLayout()
        self.obs_h = QLineEdit(self.settings.get('OBS', {}).get('host',''))
        self.obs_p = QLineEdit(str(self.settings.get('OBS', {}).get('port','2101')))
        self.obs_m = QLineEdit(self.settings.get('OBS', {}).get('mountpoint',''))
        self.obs_u = QLineEdit(self.settings.get('OBS', {}).get('user',''))
        self.obs_pw = QLineEdit(self.settings.get('OBS', {}).get('password',''))
        self.obs_pw.setEchoMode(QLineEdit.EchoMode.Password)
        fl.addRow("Host:", self.obs_h)
        fl.addRow("Port:", self.obs_p)
        fl.addRow("Mount:", self.obs_m)
        fl.addRow("User:", self.obs_u)
        fl.addRow("Pwd:", self.obs_pw)
        grp.setLayout(fl)
        layout.addWidget(grp)
        
        # EPH
        self.chk_eph = QCheckBox("Enable Ephemeris")
        self.chk_eph.setChecked(self.settings.get('EPH_ENABLED', False))
        layout.addWidget(self.chk_eph)
        
        grp2 = QGroupBox("Ephemeris Stream")
        fl2 = QFormLayout()
        self.eph_h = QLineEdit(self.settings.get('EPH', {}).get('host',''))
        self.eph_p = QLineEdit(str(self.settings.get('EPH', {}).get('port','2101')))
        self.eph_m = QLineEdit(self.settings.get('EPH', {}).get('mountpoint',''))
        self.eph_u = QLineEdit(self.settings.get('EPH', {}).get('user',''))
        self.eph_pw = QLineEdit(self.settings.get('EPH', {}).get('password',''))
        self.eph_pw.setEchoMode(QLineEdit.EchoMode.Password)
        fl2.addRow("Host:", self.eph_h)
        fl2.addRow("Port:", self.eph_p)
        fl2.addRow("Mount:", self.eph_m)
        fl2.addRow("User:", self.eph_u)
        fl2.addRow("Pwd:", self.eph_pw)
        grp2.setLayout(fl2)
        layout.addWidget(grp2)
        
        btns = QHBoxLayout()
        b_load = QPushButton("Load File")
        # 添加打开文件图标
        open_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        if not open_icon.isNull():
            b_load.setIcon(open_icon)
        b_load.clicked.connect(self.load_file)
        
        b_save = QPushButton("Connect")
        # 添加保存图标
        save_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        if not save_icon.isNull():
            b_save.setIcon(save_icon)
        b_save.clicked.connect(self.accept)
        btns.addWidget(b_load)
        btns.addStretch()
        btns.addWidget(b_save)
        layout.addLayout(btns)

    def load_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Config", "", "Python (*.py)")
        if f:
            try:
                spec = importlib.util.spec_from_file_location("cfg", f)
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)
                if hasattr(m, 'NTRIP_HOST'): self.obs_h.setText(str(m.NTRIP_HOST))
                if hasattr(m, 'NTRIP_PORT'): self.obs_p.setText(str(m.NTRIP_PORT))
                if hasattr(m, 'MOUNTPOINT'): self.obs_m.setText(str(m.MOUNTPOINT))
                if hasattr(m, 'USER'): self.obs_u.setText(str(m.USER))
                if hasattr(m, 'PASSWORD'): self.obs_pw.setText(str(m.PASSWORD))
                if hasattr(m, 'EPH_HOST'): 
                    self.chk_eph.setChecked(True)
                    self.eph_h.setText(str(m.EPH_HOST))
                    self.eph_m.setText(str(m.EPH_MOUNTPOINT))
                    self.eph_u.setText(str(m.EPH_USER))
                    self.eph_pw.setText(str(m.EPH_PASSWORD))
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def get_settings(self):
        return {
            'OBS': {'host': self.obs_h.text(), 'port': self.obs_p.text(), 'mountpoint': self.obs_m.text(), 'user': self.obs_u.text(), 'password': self.obs_pw.text()},
            'EPH_ENABLED': self.chk_eph.isChecked(),
            'EPH': {'host': self.eph_h.text(), 'port': self.eph_p.text(), 'mountpoint': self.eph_m.text(), 'user': self.eph_u.text(), 'password': self.eph_pw.text()}
        }
