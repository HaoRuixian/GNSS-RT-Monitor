# ui/main_window.py
import time
import threading
from datetime import datetime
from collections import deque, defaultdict
import numpy as np

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTableWidget, QTableWidgetItem, QLabel, QTextEdit, 
                             QSplitter, QHeaderView, QTabWidget, QComboBox, 
                             QCheckBox, QPushButton, QFrame, QApplication, QDialog)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer
from PyQt5.QtGui import QColor, QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from ui.color_def import get_sys_color, get_signal_color
from ui.workers import NtripWorker, StreamSignals
from core.rtcm_handler import RTCMHandler
from ui.widgets import SkyplotWidget, MultiSignalBarWidget, PlotSNRWidget
from ui.dialogs import ConfigDialog


class GNSSMonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GNSS Monitor V0.1")
        self.resize(1600, 900)
        
        # --- 核心修改：数据缓存区 ---
        # 用于存储合并后的所有卫星状态 { 'G01': sat_obj, 'C02': sat_obj ... }
        self.merged_satellites = {}
        # 记录每颗卫星最后一次更新的时间戳，用于判断是否过期
        self.sat_last_seen = {}
        # -------------------------

        # 历史数据 (画折线图用)
        self.sat_history = defaultdict(lambda: deque(maxlen=2000))
        self.current_sat_list = []
        
        # 默认启用的系统
        self.active_systems = {'G', 'R', 'E', 'C', 'J', 'S'} 

        # 信号连接
        self.signals = StreamSignals()
        self.signals.log_signal.connect(self.append_log)
        self.signals.epoch_signal.connect(self.process_gui_epoch)
        self.signals.status_signal.connect(self.update_status)
        self.threads = []

        # 默认配置
        self.settings = {
            'OBS': {'host': '', 'port': 2101, 'mountpoint': '', 'user': '', 'password': ''},
            'EPH_ENABLED': False,
            'EPH': {}
        }
        
        self.setup_ui()
        
        # 启动定时器，每秒检查一次是否有卫星过期 (防止卫星下线后一直卡在屏幕上)
        self.cleanup_timer = threading.Timer(1.0, self.cleanup_stale_satellites)
        self.cleanup_timer.daemon = True
        self.cleanup_timer.start()

        self.open_config_dialog()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- 1. 顶部控制栏  ---
        top_bar = QHBoxLayout()
        btn_cfg = QPushButton("⚙ Config")
        btn_cfg.clicked.connect(self.open_config_dialog)
        top_bar.addWidget(btn_cfg)
        
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        top_bar.addWidget(line)

        top_bar.addWidget(QLabel("Systems:"))
        self.chk_sys = {}
        for sys_char, name in [('G','GPS'), ('R','GLONASS'), ('E','Galileo'), ('C','BeiDou'), ('J','QZSS'), ('S','SBAS')]:
            chk = QCheckBox(name)
            chk.setChecked(sys_char in self.active_systems)
            chk.stateChanged.connect(self.on_filter_changed)
            color = get_sys_color(sys_char)
            chk.setStyleSheet(f"QCheckBox {{ color: {color}; font-weight: bold; }}")
            self.chk_sys[sys_char] = chk
            top_bar.addWidget(chk)

        top_bar.addStretch()
        
        self.lbl_status_obs = QLabel("OBS: OFF")
        self.lbl_status_eph = QLabel("EPH: OFF")
        for lbl in [self.lbl_status_obs, self.lbl_status_eph]:
            lbl.setStyleSheet("background-color: #ddd; padding: 4px 8px; border-radius: 4px;")
            top_bar.addWidget(lbl)
        layout.addLayout(top_bar)

        # --- 2. 主界面分割 ---
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：星空图
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        self.skyplot = SkyplotWidget()
        left_layout.addWidget(self.skyplot)
        splitter.addWidget(left_widget)

        # 右侧：标签页 (主 Tabs)
        self.main_tabs = QTabWidget() # 改个名防止混淆
        
        # === Tab 1: Dashboard (经过改造) ===
        tab_over = QWidget()
        vbox_over = QVBoxLayout(tab_over)
        
        # 1. 顶部柱状图 (全局)
        vbox_over.addWidget(QLabel("<b>Multi-Signal SNR Overview</b>"))
        self.bar_chart = MultiSignalBarWidget()
        self.bar_chart.setMinimumHeight(200) #稍微调小一点给表格留空间
        vbox_over.addWidget(self.bar_chart)
        
        # 2. 下部：分系统子标签页
        vbox_over.addWidget(QLabel("<b>Detailed Measurements (Split by GNSS)</b>"))
        self.sub_tabs = QTabWidget()
        
        # 定义我们需要哪些子表格
        # 键是 tab显示名，值是系统ID列表（'ALL'代表所有）
        self.table_groups = {
            'ALL': ['G', 'R', 'E', 'C', 'J', 'S'],
            'GPS': ['G'],
            'BeiDou': ['C'],
            'GLONASS': ['R'],
            'Galileo': ['E']
        }
        self.tables = {} # 存储创建好的表格对象

        headers = ["PRN", "Sys", "El(°)", "Az(°)", "Freq", "SNR", "Pseudorange (m)", "Phase (cyc)"]
        
        for tab_name in self.table_groups.keys():
            t_widget = QTableWidget()
            t_widget.setColumnCount(len(headers))
            t_widget.setHorizontalHeaderLabels(headers)
            
            # 列宽调整
            header = t_widget.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # PRN
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # Sys
            header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Freq
            header.setSectionResizeMode(6, QHeaderView.Stretch) # Pseudo
            header.setSectionResizeMode(7, QHeaderView.Stretch) # Phase
            
            t_widget.verticalHeader().setVisible(False)
            # 注意：我们这里不开启 setAlternatingRowColors，因为我们要手动根据卫星分组染色
            
            self.sub_tabs.addTab(t_widget, tab_name)
            self.tables[tab_name] = t_widget

        vbox_over.addWidget(self.sub_tabs)
        self.main_tabs.addTab(tab_over, "Dashboard")
        
        # === Tab 2: Analysis (保持不变) ===
        tab_an = QWidget()
        vbox_an = QVBoxLayout(tab_an)
        h_ctrl = QHBoxLayout()
        h_ctrl.addWidget(QLabel("Target Satellite:"))
        self.combo_sat = QComboBox()
        self.combo_sat.currentTextChanged.connect(self.refresh_analysis_plot)
        h_ctrl.addWidget(self.combo_sat)
        h_ctrl.addWidget(QLabel("Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Time Sequence", "Elevation","sin(Elevation)"])
        self.combo_mode.currentTextChanged.connect(self.refresh_analysis_plot)
        h_ctrl.addWidget(self.combo_mode)
        h_ctrl.addStretch()
        vbox_an.addLayout(h_ctrl)
    
        self.analysis_plot = PlotSNRWidget()
        vbox_an.addWidget(self.analysis_plot)
        
        self.main_tabs.addTab(tab_an, "SNR Display")
        
        splitter.addWidget(self.main_tabs)
        
        # 调整比例
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        splitter.setCollapsible(0, False)
        
        layout.addWidget(splitter, stretch=1)

        # --- 3. 日志 ---
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(80)
        self.log_area.setStyleSheet("background: #222; color: #0f0; font-family: Monospace;")
        layout.addWidget(self.log_area)

    # --- 逻辑处理 ---

    def on_filter_changed(self):
        self.active_systems = {k for k, chk in self.chk_sys.items() if chk.isChecked()}
        # 过滤器改变时，使用缓存的 merged_satellites 立即重绘
        self.refresh_all_widgets()

    def cleanup_stale_satellites(self):
        """定期清理超过5秒没更新的卫星"""
        now = time.time()
        to_remove = []
        for prn, last_time in self.sat_last_seen.items():
            if now - last_time > 5.0: # 5秒超时
                to_remove.append(prn)
        
        if to_remove:
            for prn in to_remove:
                del self.merged_satellites[prn]
                del self.sat_last_seen[prn]
            # 注意：在非 GUI 线程调用 GUI 更新需要小心，这里简单起见，
            # 我们等下一个 epoch 到来时自然会刷新，或者使用 signal 触发。
            # 这里为了线程安全，我们暂不直接触发重绘，而是让 process_gui_epoch 承担重绘任务

        # 重新启动定时器
        self.cleanup_timer = threading.Timer(2.0, self.cleanup_stale_satellites)
        self.cleanup_timer.daemon = True
        self.cleanup_timer.start()

    @pyqtSlot(object)
    def process_gui_epoch(self, epoch_data):
        """
        这里是关键修改：
        1. 接收新数据
        2. 更新到 merged_satellites 字典
        3. 刷新界面显示 merged_satellites 的内容
        """
        now = time.time()
        current_dt = datetime.now()

        # --- 步骤1：合并数据 ---
        for prn, sat in epoch_data.satellites.items():
            self.merged_satellites[prn] = sat
            self.sat_last_seen[prn] = now
            
            # 同时更新历史记录 (用于折线图)
            el = getattr(sat, "el", getattr(sat, "elevation", 0)) or 0
            snr_map = {c: s.snr for c, s in sat.signals.items() if s and getattr(s, 'snr', 0)}
            self.sat_history[prn].append({'time': current_dt, 'el': el, 'snr': snr_map})

        # --- 步骤2：统一刷新界面 ---
        self.refresh_all_widgets()

    def refresh_all_widgets(self):
        # 使用 self.merged_satellites 而不是原始 epoch_data
        
        # 1. Update Skyplot
        self.skyplot.update_satellites(self.merged_satellites, self.active_systems)
        
        # 2. Update Bar Chart
        self.bar_chart.update_data(self.merged_satellites, self.active_systems)
        
        # 3. Update Table
        self.update_table()
        
        # 4. Analysis Plot
        if self.combo_sat.currentText():
            self.refresh_analysis_plot()

    def update_table(self):
        # 1. 准备数据
        active_prns_in_view = [] # 用于更新下拉框
        sys_map = {'G': 'GPS', 'R': 'GLO', 'E': 'GAL', 'C': 'BDS', 'J': 'QZS', 'S': 'SBS'}
        
        # 定义两种背景色，用于区分不同卫星 (浅白 / 浅灰)
        bg_colors = [QColor("#ffffff"), QColor("#b9b9b9")]

        # 清空所有子表格
        for t in self.tables.values():
            t.setRowCount(0)

        # 排序
        sorted_sats = sorted(self.merged_satellites.items())

        # 遍历卫星
        sat_counter = 0 # 卫星计数器，用于决定颜色
        
        for key, sat in sorted_sats:
            sys_char = key[0]
            
            # 基础信息
            el = getattr(sat, "el", getattr(sat, "elevation", 0)) or 0
            az = getattr(sat, "az", getattr(sat, "azimuth", 0)) or 0
            
            # 确定这颗卫星应该显示的颜色
            current_bg = bg_colors[sat_counter % 2]
            sat_counter += 1

            # 遍历这颗卫星的所有信号 (Signal)
            # 排序信号代码: 1C, 2W, 5Q...
            sorted_codes = sorted(sat.signals.keys())
            
            # 如果没有信号，也跳过
            if not sorted_codes: continue
            
            # 记录这颗卫星是否已经被添加到 active_prns (避免重复)
            added_to_dropdown = False

            # === 核心：每个信号生成一行 ===
            for code in sorted_codes:
                sig = sat.signals[code]
                if not sig: continue

                snr = getattr(sig, 'snr', 0)
                if snr == 0: continue # 不显示无效信号

                # 提取伪距和相位
                pr = getattr(sig, 'pseudorange', 0)
                ph = getattr(sig, 'phase', 0)
                
                pr_str = f"{pr:12.3f}" if pr else ""
                ph_str = f"{ph:12.3f}" if ph else ""
                
                # 构建行数据
                row_items = [
                    key,                            # PRN
                    sys_map.get(sys_char, sys_char),# Sys
                    f"{el:.1f}",                    # El
                    f"{az:.1f}",                    # Az
                    code,                           # Freq/Signal
                    f"{snr:.1f}",                   # SNR
                    pr_str,                         # Pseudorange
                    ph_str                          # Phase
                ]

                # 将这一行添加到所有符合条件的表格中
                for tab_name, valid_systems in self.table_groups.items():
                    # 检查当前卫星系统是否属于该 Tab (比如 'G' 属于 'ALL' 和 'GPS')
                    if sys_char in valid_systems:
                        
                        # 只有当用户在顶部 Checkbox 勾选了该系统，才显示
                        if sys_char in self.active_systems:
                            
                            if not added_to_dropdown:
                                active_prns_in_view.append(key)
                                added_to_dropdown = True
                            
                            table = self.tables[tab_name]
                            row_idx = table.rowCount()
                            table.insertRow(row_idx)
                            
                            # 填入单元格并设置背景色
                            for col_idx, val in enumerate(row_items):
                                item = QTableWidgetItem(str(val))
                                item.setTextAlignment(Qt.AlignCenter)
                                item.setBackground(current_bg) # 设置背景色
                                
                                # 给 SNR 加个颜色增强可读性 (可选)
                                if col_idx == 5: # SNR column
                                    if snr > 40: item.setForeground(QColor("green"))
                                    elif snr < 30: item.setForeground(QColor("red"))
                                    item.setFont(QFont("Arial", 9, QFont.Bold))
                                
                                table.setItem(row_idx, col_idx, item)

        # 3. 更新 Analysis 页面的下拉框
        current_sel = self.combo_sat.currentText()
        # 简单去重并排序
        active_prns_in_view = sorted(list(set(active_prns_in_view)))
        
        if active_prns_in_view != self.current_sat_list:
            self.current_sat_list = active_prns_in_view
            self.combo_sat.blockSignals(True)
            self.combo_sat.clear()
            self.combo_sat.addItems(active_prns_in_view)
            if current_sel in active_prns_in_view:
                self.combo_sat.setCurrentText(current_sel)
            self.combo_sat.blockSignals(False)

    def refresh_analysis_plot(self):
        prn = self.combo_sat.currentText()
        mode = self.combo_mode.currentText()
        if prn and mode:
            data = list(self.sat_history[prn])
            # 直接调用封装好的方法，主窗口非常清爽
            self.analysis_plot.update_plot(prn, data, mode)

    # --- Config 与其他辅助函数保持不变 ---
    def open_config_dialog(self):
        dlg = ConfigDialog(self, self.settings)
        if dlg.exec_() == QDialog.Accepted:
            self.settings = dlg.get_settings()
            self.restart_streams()

    def restart_streams(self):
        for t in self.threads: t.stop()
        self.threads.clear()
        self.merged_satellites.clear() # 重连时清空缓存
        self.sat_last_seen.clear()
        self.sat_history.clear()
        self.handler = RTCMHandler()
        
        if self.settings['OBS']['host']:
            t = NtripWorker("OBS", self.settings['OBS'], self.handler, self.signals)
            t.start()
            self.threads.append(t)
        
        if self.settings['EPH_ENABLED'] and self.settings['EPH']['host']:
            t = NtripWorker("EPH", self.settings['EPH'], self.handler, self.signals)
            t.start()
            self.threads.append(t)

    @pyqtSlot(str)
    def append_log(self, text):
        self.log_area.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    @pyqtSlot(str, bool)
    def update_status(self, name, connected):
        lbl = self.lbl_status_obs if name == "OBS" else self.lbl_status_eph
        color = "#4CAF50" if connected else "#F44336"
        lbl.setText(f"{name}: {'ON' if connected else 'OFF'}")
        lbl.setStyleSheet(f"background-color: {color}; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")

    def closeEvent(self, event):
        for t in self.threads: t.stop()
        if hasattr(self, 'cleanup_timer'): self.cleanup_timer.cancel()
        event.accept()
