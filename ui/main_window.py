# ui/main_window.py
import time
import threading
from datetime import datetime
from collections import deque, defaultdict
import numpy as np

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTableWidget, QTableWidgetItem, QLabel, QTextEdit, 
                             QSplitter, QHeaderView, QTabWidget, QComboBox,
                             QCheckBox, QPushButton, QFrame, QApplication, QDialog, QStyle)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPalette
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from ui.color_def import get_sys_color, get_signal_color
from ui.workers import IOThread, DataProcessingThread, StreamSignals
from core.rtcm_handler import RTCMHandler
from core.ring_buffer import RingBuffer
from core.data_store import GnssIrStore
from ui.widgets import SkyplotWidget, MultiSignalBarWidget, PlotSNRWidget
from ui.dialogs import ConfigDialog
import config


class GNSSMonitorWindow(QMainWindow):
    """
    Main GUI: owns threads, caches, widgets, and refresh throttling.

    - Receives parsed epochs via Qt signal.
    - Maintains merged satellite snapshot + history for plots.
    - Stores filtered GNSS-IR samples for downstream spectral analysis.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GNSS RT Monitor V0.1")
        self.resize(1600, 900)
        
        self.merged_satellites = {}
        self.sat_last_seen = {}

        self.sat_history = defaultdict(lambda: deque(maxlen=500))
        self.current_sat_list = []

        keep_seconds = getattr(config, "GNSS_IR", {}).get("KEEP_SECONDS", 900)
        self.ir_store = GnssIrStore(keep_seconds=keep_seconds)
        
        # 性能优化：GUI更新节流机制
        self.last_gui_update_time = 0
        self.gui_update_interval = 0.3  # 300ms
        self.pending_update = False
        self.current_tab_index = 0  # 跟踪当前tab，只更新可见的widget
        self.last_table_data_hash = None  # 用于检测表格数据是否变化
        
        # 从config.py读取启用的系统，如果没有定义则使用默认值
        try:
            if hasattr(config, 'TARGET_SYSTEMS') and config.TARGET_SYSTEMS:
                self.active_systems = set(config.TARGET_SYSTEMS)
            else:
                self.active_systems = {'G', 'R', 'E', 'C', 'J', 'S'}
        except:
            self.active_systems = {'G', 'R', 'E', 'C', 'J', 'S'} 

        # 信号连接
        self.signals = StreamSignals()
        self.signals.log_signal.connect(self.append_log)
        self.signals.epoch_signal.connect(self.process_gui_epoch)
        self.signals.status_signal.connect(self.update_status)
        # 多线程管线架构：存储所有线程（IO线程和数据处理线程）
        self.io_threads = []
        self.processing_threads = []
        self.ring_buffers = {}  # 存储每个流的环形缓冲区

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
        
        # 性能优化：定期检查并执行待处理的GUI更新（防止数据丢失）
        self.gui_update_timer = QTimer()
        self.gui_update_timer.timeout.connect(self._check_pending_update)
        self.gui_update_timer.start(50)  # 每50ms检查一次

        # Initial log
        self.signals.log_signal.emit("=== GNSS RT Monitor Started ===")
        self.signals.log_signal.emit("Ready. Please configure streams via Config button.")

        # self.open_config_dialog()

    def setup_ui(self):
        self.apply_stylesheet()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- 1. 顶部控制栏  ---
        top_bar = QHBoxLayout()
        btn_cfg = QPushButton("Config")
        # 使用设置图标
        try:
            # 尝试使用文件对话框信息视图图标作为设置图标
            settings_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView)
            if settings_icon.isNull():
                # 如果不可用，尝试其他图标
                settings_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
            if not settings_icon.isNull():
                btn_cfg.setIcon(settings_icon)
            else:
                btn_cfg.setText("⚙ Config")
        except:
            # 如果图标不可用，使用Unicode符号作为后备
            btn_cfg.setText("⚙ Config")
        btn_cfg.clicked.connect(self.open_config_dialog)
        top_bar.addWidget(btn_cfg)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
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
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
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
        vbox_over.addWidget(QLabel("<b>Detailed</b>"))
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
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # PRN
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) # Sys
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Freq
            header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch) # Pseudo
            header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch) # Phase
            
            t_widget.verticalHeader().setVisible(False)
            # 注意：我们这里不开启 setAlternatingRowColors，因为我们要手动根据卫星分组染色
            
            self.sub_tabs.addTab(t_widget, tab_name)
            self.tables[tab_name] = t_widget

        vbox_over.addWidget(self.sub_tabs)
        self.main_tabs.addTab(tab_over, "Dashboard")
        
        # 监听tab切换，只更新可见的widget
        self.main_tabs.currentChanged.connect(self.on_tab_changed)
        
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
        self.log_area.setStyleSheet("background: #ffffff; color: #000000; font-family: Monospace; border: 1px solid #ccc;")
        # 性能优化：限制日志行数，防止无限增长导致内存泄漏
        self.max_log_lines = 500
        layout.addWidget(self.log_area)

    def apply_stylesheet(self):
        # 主色：深色/亮色自适应
        palette = QApplication.palette()
        base_color = palette.color(QPalette.ColorRole.Window)
        is_dark = base_color.lightness() < 128
        
        if is_dark:
            accent = "#4CC2FF"
            border = "#3C3F41"
            bg = "#1E1F22"
            fg = "#E6E6E6"
            hover = "#2A2C2F"
            card = "#232528"
            subtle = "#2F3135"
            log_bg = "#111"
            log_fg = "#9CF5C3"
        else:
            accent = "#006CBE"
            border = "#C7CCD1"
            bg = "#F7F9FC"
            fg = "#111111"
            hover = "#E4E9F0"
            card = "#FFFFFF"
            subtle = "#EDF1F7"
            log_bg = "#111"
            log_fg = "#00ff90"

        stylesheet = f"""
        QWidget {{
            background: {bg};
            color: {fg};
            font-size: 14px;
        }}

        /* --- Panels / Cards --- */
        QWidget#Panel, QFrame {{
            background: {card};
            border: 1px solid {border};
            border-radius: 8px;
        }}

        /* --- Titles / labels --- */
        QLabel {{
            border: none;
            background: transparent;
        }}

        /* --- Buttons --- */
        QPushButton {{
            background: {hover};
            border: 1px solid {border};
            padding: 7px 14px;
            border-radius: 8px;
            font-weight: 600;
            letter-spacing: 0.2px;
        }}
        QPushButton:hover {{
            background: {subtle};
            border-color: {accent};
            color: {accent};
            box-shadow: 0 0 0 2px {accent}33;
        }}

        QPushButton:pressed {{
            background: {accent}33;
            border-color: {accent};
        }}
        

        /* --- Checkboxes --- */
        QCheckBox {{
            spacing: 8px;
            font-weight: 600;
        }}

        /* --- Combobox --- */
        QComboBox {{
            background: {card};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 4px 8px;
        }}
        QComboBox:hover {{
            border-color: {accent};
        }}
        QComboBox QAbstractItemView {{
            background: {card};
            selection-background-color: {accent}22;
            selection-color: {fg};
            border: 1px solid {border};
        }}

        /* --- Tabs --- */
        QTabBar::tab {{
            background: {hover};
            padding: 8px 18px;
            margin-right: 6px;
            border-bottom: 2px solid transparent;
            font-weight: bold;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }}
        QTabBar::tab:selected {{
            color: {accent};
            border-bottom: 2px solid {accent};
            background: {card};
        }}
        QTabBar::tab:hover {{
            background: {subtle};
        }}

        /* --- Tables --- */
        QTableWidget {{
            background: {card};
            gridline-color: {border};
            selection-background-color: {accent}33;
            selection-color: {fg};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        QHeaderView::section {{
            background: {subtle};
            padding: 6px;
            font-weight: 700;
            border: none;
            border-right: 1px solid {border};
        }}

        /* --- Scrollbars --- */
        QScrollBar:vertical {{
            width: 10px;
            background: transparent;
        }}
        QScrollBar::handle:vertical {{
            background: {subtle};
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {accent}99;
        }}

        /* --- Text / Inputs --- */
        QLineEdit, QTextEdit {{
            background: {card};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 6px;
        }}

        /* --- Log area --- */
        QTextEdit {{
            background: {log_bg};
            color: {log_fg};
            border-radius: 6px;
            padding: 6px;
            font-family: Consolas, Monospace;
            font-size: 13px;
        }}
        """

        self.setStyleSheet(stylesheet)

    # --- 逻辑处理 ---

    def on_filter_changed(self):
        self.active_systems = {k for k, chk in self.chk_sys.items() if chk.isChecked()}
        # 过滤器改变时，使用缓存的 merged_satellites 立即重绘
        self.refresh_all_widgets()

    def cleanup_stale_satellites(self):
        """定期清理超过5秒没更新的卫星，同时清理历史数据"""
        now = time.time()
        to_remove = []
        for prn, last_time in self.sat_last_seen.items():
            if now - last_time > 5.0: # 5秒超时
                to_remove.append(prn)
        
        if to_remove:
            for prn in to_remove:
                del self.merged_satellites[prn]
                del self.sat_last_seen[prn]
                # 性能优化：清理过期卫星的历史数据，释放内存
                if prn in self.sat_history:
                    del self.sat_history[prn]
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
        接收新数据，更新到 merged_satellites 字典，刷新界面显示
        """
        now = time.time()
        current_dt = datetime.now()
        n_sats = len(epoch_data.satellites)
        n_signals = sum(len(sat.signals) for sat in epoch_data.satellites.values())

        # --- 步骤1：合并数据 ---
        for prn, sat in epoch_data.satellites.items():
            self.merged_satellites[prn] = sat
            self.sat_last_seen[prn] = now
            
            # 同时更新历史记录 (用于折线图)
            el = getattr(sat, "el", getattr(sat, "elevation", 0)) or None
            snr_map = {c: s.snr for c, s in sat.signals.items() if s and getattr(s, 'snr', 0)}
            self.sat_history[prn].append({'time': current_dt, 'el': el, 'snr': snr_map})

        # 额外：将满足GNSS-IR掩膜的数据写入内存存储，便于后续LSP分析
        try:
            self.ir_store.add_epoch(epoch_data.gps_time, epoch_data.satellites, config.GNSS_IR, self.active_systems)
        except Exception:
            pass

        # --- 步骤2：统一刷新界面（带节流机制）---
        if now - self.last_gui_update_time >= self.gui_update_interval:
            self.refresh_all_widgets()
            self.last_gui_update_time = now
            self.pending_update = False
            
            # 每5秒输出一次数据统计
            if not hasattr(self, '_last_stats_log_time'):
                self._last_stats_log_time = now
            if now - self._last_stats_log_time >= 5.0:
                total_sats = len(self.merged_satellites)
                ir_samples = len(self.ir_store._data) if hasattr(self.ir_store, '_data') else 0
                self.signals.log_signal.emit(
                    f"Status: {total_sats} satellites tracked, "
                    f"{n_sats} in epoch, {n_signals} signals, "
                    f"{ir_samples} IR samples stored"
                )
                self._last_stats_log_time = now
        else:
            # 标记有待更新，但不在这个epoch立即更新
            self.pending_update = True

    def _check_pending_update(self):
        """检查是否有待处理的更新，如果有则执行更新"""
        if self.pending_update:
            now = time.time()
            if now - self.last_gui_update_time >= self.gui_update_interval:
                self.refresh_all_widgets()
                self.last_gui_update_time = now
                self.pending_update = False
    
    def on_tab_changed(self, index):
        """Tab切换时更新当前tab索引"""
        self.current_tab_index = index
    
    def refresh_all_widgets(self):
        # 性能优化：只更新当前可见的tab，减少不必要的绘制
        # 线程安全：创建字典副本，避免在遍历时字典被其他线程修改
        satellites_snapshot = dict(self.merged_satellites)
        
        # Tab 0: Dashboard - 总是更新（因为skyplot和bar chart在左侧，总是可见）
        if self.current_tab_index == 0 or True:  # 暂时总是更新，因为左侧widget总是可见
            # 1. Update Skyplot (左侧，总是可见)
            self.skyplot.update_satellites(satellites_snapshot, self.active_systems)
            
            # 2. Update Bar Chart (Dashboard tab，总是可见)
            self.bar_chart.update_data(satellites_snapshot, self.active_systems)
            
            # 3. Update Table (只在Dashboard tab时更新)
            if self.current_tab_index == 0:
                self.update_table()
        
        # Tab 1: Analysis - 只在Analysis tab时更新
        if self.current_tab_index == 1 and self.combo_sat.currentText():
            self.refresh_analysis_plot()

    def update_table(self):
        # 性能优化：检测数据是否真的变化了，避免不必要的更新
        import hashlib
        satellites_snapshot = dict(self.merged_satellites)
        # 创建数据哈希，快速检测变化（包含SNR/伪距/相位，确保实时刷新而不重复重绘）
        flat_rows = []
        for key, sat in sorted(satellites_snapshot.items()):
            el = getattr(sat, "el", getattr(sat, "elevation", 0)) or 0
            az = getattr(sat, "az", getattr(sat, "azimuth", 0)) or 0
            for code, sig in sorted(sat.signals.items()):
                if not sig: 
                    continue
                flat_rows.append((
                    key,
                    round(el, 1),
                    round(az, 1),
                    code,
                    round(getattr(sig, "snr", 0.0) or 0.0, 1),
                    round(getattr(sig, "pseudorange", 0.0) or 0.0, 3),
                    round(getattr(sig, "phase", 0.0) or 0.0, 3),
                ))
        data_hash = hashlib.md5(str(flat_rows).encode()).hexdigest()
        
        # 如果数据没有变化，跳过更新（但第一次总是更新）
        if data_hash == self.last_table_data_hash and self.last_table_data_hash is not None:
            return
        
        self.last_table_data_hash = data_hash
        
        # 性能优化：使用setUpdatesEnabled减少重绘开销
        for t in self.tables.values():
            t.setUpdatesEnabled(False)  # 禁用更新，批量操作
        
        try:
            # 1. 准备数据
            active_prns_in_view = [] # 用于更新下拉框
            sys_map = {'G': 'GPS', 'R': 'GLO', 'E': 'GAL', 'C': 'BDS', 'J': 'QZS', 'S': 'SBS'}
            
            # 定义两种背景色，用于区分不同卫星 (浅白 / 浅灰)
            bg_colors = [QColor("#ffffff"), QColor("#b9b9b9")]

            # 清空所有子表格
            for t in self.tables.values():
                t.setRowCount(0)

            # 排序
            sorted_sats = sorted(satellites_snapshot.items())

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
                                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                                    item.setBackground(current_bg) # 设置背景色
                                    
                                    # 给 SNR 加个颜色增强可读性 (可选)
                                    if col_idx == 5: # SNR column
                                        if snr > 40: item.setForeground(QColor("green"))
                                        elif snr < 30: item.setForeground(QColor("red"))
                                        item.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                                    
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
        finally:
            # 重新启用更新
            for t in self.tables.values():
                t.setUpdatesEnabled(True)

    def refresh_analysis_plot(self):
        prn = self.combo_sat.currentText()
        mode = self.combo_mode.currentText()
        if prn and mode:
            data = list(self.sat_history[prn])
            # 直接调用封装好的方法，主窗口非常清爽
            self.analysis_plot.update_plot(prn, data, mode)

    # ---- GNSS-IR ----
    def get_ir_series(self, prn: str = None, signal_id: str = None):
        """
        Return the historical samples that meet the mask, which can be used for GNSS-IR analysis.
        """
        sys_id = prn[0] if prn else None
        return self.ir_store.get_series(prn=prn, sys=sys_id, signal_id=signal_id)

    # --- Config  ---
    def open_config_dialog(self):
        dlg = ConfigDialog(self, self.settings)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.get_settings()
            self.restart_streams()

    def restart_streams(self):
        """重启数据流：使用多线程并行管线架构"""
        self.signals.log_signal.emit("=== Restarting streams ===")
        
        # 停止所有现有线程
        if self.io_threads or self.processing_threads:
            self.signals.log_signal.emit("Stopping existing threads...")
            for t in self.io_threads: 
                t.stop()
            for t in self.processing_threads: 
                t.stop()
            # 等待线程结束
            for t in self.io_threads + self.processing_threads:
                t.join(timeout=1.0)
        
        # 关闭所有环形缓冲区
        for rb in self.ring_buffers.values():
            rb.close()
        
        self.io_threads.clear()
        self.processing_threads.clear()
        self.ring_buffers.clear()
        
        # 清空数据缓存
        self.merged_satellites.clear()
        self.sat_last_seen.clear()
        self.sat_history.clear()
        self.signals.log_signal.emit("Cleared data cache")
        
        # 创建共享的RTCM处理器
        self.handler = RTCMHandler()
        
        # 为OBS流创建多线程管线
        if self.settings['OBS']['host']:
            self.signals.log_signal.emit("Initializing OBS stream...")
            obs_buffer = RingBuffer(maxsize=1000)
            self.ring_buffers['OBS'] = obs_buffer
            
            io_thread = IOThread("OBS", self.settings['OBS'], obs_buffer, self.signals)
            io_thread.start()
            self.io_threads.append(io_thread)
            
            proc_thread = DataProcessingThread("OBS", obs_buffer, self.handler, self.signals)
            proc_thread.start()
            self.processing_threads.append(proc_thread)
            self.signals.log_signal.emit("OBS stream threads started")
        else:
            self.signals.log_signal.emit("OBS stream not configured")
        
        # 为EPH流创建多线程管线
        if self.settings['EPH_ENABLED'] and self.settings['EPH']['host']:
            self.signals.log_signal.emit("Initializing EPH stream...")
            eph_buffer = RingBuffer(maxsize=1000)
            self.ring_buffers['EPH'] = eph_buffer
            
            io_thread = IOThread("EPH", self.settings['EPH'], eph_buffer, self.signals)
            io_thread.start()
            self.io_threads.append(io_thread)
            
            proc_thread = DataProcessingThread("EPH", eph_buffer, self.handler, self.signals)
            proc_thread.start()
            self.processing_threads.append(proc_thread)
            self.signals.log_signal.emit("EPH stream threads started")
        elif self.settings['EPH_ENABLED']:
            self.signals.log_signal.emit("EPH stream enabled but not configured")
        
        active_systems = ', '.join(sorted(self.active_systems))
        self.signals.log_signal.emit(f"Active GNSS systems: {active_systems}")
        self.signals.log_signal.emit("=== Stream initialization complete ===")

    @pyqtSlot(str)
    def append_log(self, text):
        """添加日志，并限制日志行数防止无限增长"""
        log_text = f"[{datetime.now().strftime('%H:%M:%S')}] {text}"
        self.log_area.append(log_text)
        
        # 性能优化：限制日志行数，防止内存无限增长
        # 当超过最大行数时，删除最旧的行
        doc = self.log_area.document()
        if doc.blockCount() > self.max_log_lines:
            cursor = self.log_area.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            # 删除前100行（批量删除以提高效率）
            for _ in range(100):
                cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()

    @pyqtSlot(str, bool)
    def update_status(self, name, connected):
        lbl = self.lbl_status_obs if name == "OBS" else self.lbl_status_eph
        color = "#4CAF50" if connected else "#F44336"
        lbl.setText(f"{name}: {'ON' if connected else 'OFF'}")
        lbl.setStyleSheet(f"background-color: {color}; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")

    def closeEvent(self, event):
        """关闭窗口时停止所有线程"""
        for t in self.io_threads: 
            t.stop()
        for t in self.processing_threads: 
            t.stop()
        # 关闭所有环形缓冲区
        for rb in self.ring_buffers.values():
            rb.close()
        if hasattr(self, 'cleanup_timer'): 
            self.cleanup_timer.cancel()
        if hasattr(self, 'gui_update_timer'): 
            self.gui_update_timer.stop()
        event.accept()
