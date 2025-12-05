# ui/widgets.py
import numpy as np
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from collections import defaultdict
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar


from ui.color_def import get_sys_color, get_signal_color

class SkyplotWidget(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(4, 4), dpi=100, facecolor='#f0f0f0')
        self.ax = self.fig.add_subplot(111, projection='polar')
        super().__init__(self.fig)
        self.setParent(parent)
        self.init_plot()

    def init_plot(self):
        self.ax.clear()
        self.ax.set_theta_zero_location('N')
        self.ax.set_theta_direction(-1)
        self.ax.set_rlim(90, 0)
        self.ax.set_yticks([0, 30, 60, 90])
        self.ax.set_yticklabels(['90', '60', '30', '0'])
        self.ax.grid(True, alpha=0.3)
        self.ax.set_title("Skyplot", pad=10, fontsize=9, fontweight='bold')

    def update_satellites(self, satellites, active_systems):
        self.ax.clear()
        self.init_plot()
        
        # 过滤并绘制
        for key, sat in satellites.items():
            if key[0] not in active_systems: continue # 过滤系统

            el = getattr(sat, "el", getattr(sat, "elevation", None))
            az = getattr(sat, "az", getattr(sat, "azimuth", None))
            
            if el is not None and az is not None:
                color = get_sys_color(key[0])
                self.ax.scatter(np.radians(az), el, c=color, s=100, alpha=0.8, edgecolors='white')
                self.ax.text(np.radians(az), el, key, fontsize=8, ha='center', va='bottom', fontweight='bold')
        
        self.draw()

class MultiSignalBarWidget(FigureCanvas):
    """分组柱状图：显示每颗卫星的所有频点 SNR"""
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 4), dpi=100, facecolor='#ffffff')
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.fig.subplots_adjust(bottom=0.25, top=0.9, left=0.08, right=0.98)

    def update_data(self, satellites, active_systems):
        self.ax.clear()
        
        # 1. 过滤卫星
        valid_sats = {k: v for k, v in satellites.items() if k[0] in active_systems}
        sorted_keys = sorted(valid_sats.keys())
        
        if not sorted_keys:
            self.ax.text(0.5, 0.5, "No Satellites for selected systems", ha='center', va='center')
            self.draw()
            return

        # 2. 收集所有出现的信号名称以便做 Legend
        all_signals_set = set()
        
        # 3. 准备绘图数据结构
        x_indices = np.arange(len(sorted_keys))
        sat_map = {k: i for i, k in enumerate(sorted_keys)}
        
        bar_width = 0.15 
        sig_plot_data = defaultdict(list)
        max_sigs_per_sat = 1
        
        for k in sorted_keys:
            sat = valid_sats[k]
            valid_sigs = {code: sig for code, sig in sat.signals.items() if sig and getattr(sig, 'snr', 0) > 0}
            
            if not valid_sigs: continue
            
            # 对信号名排序
            sorted_sig_codes = sorted(valid_sigs.keys())
            max_sigs_per_sat = max(max_sigs_per_sat, len(sorted_sig_codes))
            
            # 计算起始偏移量
            n_sigs = len(sorted_sig_codes)
            start_offset = - (n_sigs * bar_width) / 2 + (bar_width / 2)
            
            for i, code in enumerate(sorted_sig_codes):
                all_signals_set.add(code)
                offset = start_offset + i * bar_width
                snr = valid_sigs[code].snr
                
                # 保存: (x坐标索引, 偏移量, SNR值)
                sig_plot_data[code].append((sat_map[k], offset, snr))

        # 4. 绘制
        legend_handles = {} 
        
        # 按频段排序 Legend (让 1C, 1W 在一起，2C, 2W 在一起)
        sorted_all_signals = sorted(list(all_signals_set))
        
        for code in sorted_all_signals:
            data_points = sig_plot_data[code]
            if not data_points: continue
            
            x_vals = [d[0] + d[1] for d in data_points] # Base X + Offset
            y_vals = [d[2] for d in data_points]
            
            # === 修改点：调用新的颜色函数 ===
            color = get_signal_color(code)
            # ==============================
            
            bars = self.ax.bar(x_vals, y_vals, width=bar_width, color=color, alpha=0.9, label=code, edgecolor='none')
            legend_handles[code] = bars[0]

        # 5. 设置坐标轴
        self.ax.set_xticks(x_indices)
        self.ax.set_xticklabels(sorted_keys, rotation=90, fontsize=9, fontweight='bold')
        self.ax.set_ylim(0, 60)
        self.ax.set_ylabel("SNR (dB-Hz)")
        self.ax.grid(True, axis='y', linestyle='--', alpha=0.5)
        
        # 6. 自定义图例
        if legend_handles:
            # 动态调整图例列数，避免太长
            ncol = min(len(legend_handles), 8)
            self.ax.legend(handles=legend_handles.values(), labels=legend_handles.keys(), 
                           loc='upper center', bbox_to_anchor=(0.5, 1.15),
                           ncol=ncol, fontsize='small', frameon=False)
            
        self.draw()


class PlotSNRWidget(QWidget):
    """
    修改后的绘图组件：
    1. 继承自 QWidget 而不是 FigureCanvas，以便同时容纳工具栏(Toolbar)和画布(Canvas)。
    2. 支持 sin(Elevation) 模式。
    3. 解决了 Title 和 Legend 重叠问题。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 1. 创建垂直布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 2. 初始化 Matplotlib 画布
        self.fig = Figure(figsize=(5, 4), dpi=100, facecolor='#ffffff')
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        
        # 设置布局调整，预留顶部空间给 Legend 和 Title
        # top=0.85 留出 15% 的顶部空间
        self.fig.subplots_adjust(bottom=0.15, top=0.85, left=0.12, right=0.95)

        # 3. 初始化导航工具栏 (实现缩放、平移的关键)
        self.toolbar = NavigationToolbar(self.canvas, self)

        # 4. 添加到布局：工具栏在上，画布在下
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        # 设置策略，让画布尽可能扩展
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def update_plot(self, prn, data, mode):
        """
        mode: "Time Sequence", "Elevation", "sin(Elevation)"
        """
        self.ax.clear()
        if not data:
            self.canvas.draw()
            return

        # --- 数据预处理：过滤高度角 <= 0 的数据 ---
        # 如果是高度角相关模式，我们通常不看地平线以下的数据
        valid_data = []
        for d in data:
            # 如果模式是高度角相关，且高度角为0或负，则跳过
            if ("Elevation" in mode or "sin" in mode) and d['el'] <= 0:
                continue
            valid_data.append(d)
        
        # 如果过滤完没数据了，直接返回
        if not valid_data:
            self.canvas.draw()
            return

        # 提取所有出现的信号
        all_sigs = set()
        for d in valid_data: all_sigs.update(d['snr'].keys())
        sorted_sigs = sorted(all_sigs)

        # 提取基础列表
        times = [d['time'] for d in valid_data]
        els = [d['el'] for d in valid_data] # 角度制

        # --- 绘图逻辑 ---
        for sig in sorted_sigs:
            vals = [d['snr'].get(sig, np.nan) for d in valid_data]
            color = get_signal_color(sig) # 确保你有引入这个函数

            if "Time" in mode:
                self.ax.plot(times, vals, '.-', markersize=3, label=sig, color=color, linewidth=1)
            
            elif "sin" in mode:
                # sin(Elevation) 模式
                # 将角度转为弧度，再求 sin
                x_vals = np.sin(np.radians(els))
                self.ax.scatter(x_vals, vals, s=10, label=sig, color=color, alpha=0.6)
            
            else:
                # 普通 Elevation 模式
                self.ax.scatter(els, vals, s=10, label=sig, color=color, alpha=0.6)

        # --- 设置 X 轴格式 ---
        if "Time" in mode:
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            self.ax.set_xlabel("Time")
            
        elif "sin" in mode:
            self.ax.set_xlabel("sin(Elevation)")
            
        else:
            self.ax.set_xlabel("Elevation (°)")

        # --- 设置通用属性 ---
        self.ax.set_ylabel("SNR (dB-Hz)")
        self.ax.set_ylim(0, 60)
        self.ax.set_title(f"Satellite: {prn}", y=1.12, fontsize=10, fontweight='bold')
        
        self.ax.grid(True, linestyle=':', alpha=0.6)

        self.ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.02), 
                       ncol=6, fontsize='small', frameon=False)
        
        self.canvas.draw()