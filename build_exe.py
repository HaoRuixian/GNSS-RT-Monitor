#!/usr/bin/env python3
"""
打包脚本：将 gui_main.py 打包为 exe 文件
使用 PyInstaller 进行打包
"""
import os
import sys
import subprocess
import shutil

def main():
    # 检查 PyInstaller 是否安装
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller 未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller 安装完成")
    
    # 创建 bin 文件夹
    bin_dir = "bin"
    if not os.path.exists(bin_dir):
        os.makedirs(bin_dir)
        print(f"创建文件夹: {bin_dir}")
    
    # 清理之前的构建文件
    if os.path.exists("build"):
        shutil.rmtree("build")
        print("清理 build 文件夹")
    if os.path.exists("dist"):
        shutil.rmtree("dist")
        print("清理 dist 文件夹")
    
    # 确定路径分隔符（Windows 使用分号，Linux/Mac 使用冒号）
    if sys.platform == "win32":
        sep = ";"
    else:
        sep = ":"
    
    # 获取当前工作目录作为路径
    current_dir = os.getcwd()
    
    # PyInstaller 命令
    cmd = [
        "pyinstaller",
        "--name=GNSS-RT-Monitor",
        "--onefile",  # 打包为单个 exe 文件
        "--windowed",  # 不显示控制台窗口（GUI应用）
        f"--add-data=config.py{sep}.",  # 包含 config.py
        # 添加路径，确保能找到 ui 和 core 包
        f"--paths={current_dir}",
        # 隐藏导入 - PyQt6
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtWidgets",
        # 隐藏导入 - matplotlib
        "--hidden-import=matplotlib.backends.backend_qtagg",
        "--hidden-import=matplotlib.figure",
        "--hidden-import=matplotlib.dates",
        # 隐藏导入 - 第三方库
        "--hidden-import=numpy",
        "--hidden-import=pyrtcm",
        "--hidden-import=pynmeagps",
        # 隐藏导入 - ui 包及其所有模块
        "--hidden-import=ui",
        "--hidden-import=ui.main_window",
        "--hidden-import=ui.widgets",
        "--hidden-import=ui.dialogs",
        "--hidden-import=ui.workers",
        "--hidden-import=ui.color_def",
        # 隐藏导入 - core 包及其所有模块
        "--hidden-import=core",
        "--hidden-import=core.rtcm_handler",
        "--hidden-import=core.ntrip_client",
        "--hidden-import=core.data_models",
        "--hidden-import=core.geo_utils",
        "--hidden-import=core.display_info",
        "--hidden-import=core.BE2pos",
        "--hidden-import=core.process",
        # 隐藏导入 - config
        "--hidden-import=config",
        # 收集所有相关数据
        "--collect-all=matplotlib",
        "--collect-all=PyQt6",
        "--collect-submodules=matplotlib",
        "--collect-submodules=ui",
        "--collect-submodules=core",
        # 排除不需要的模块以减小体积
        "--exclude-module=tkinter",
        "--exclude-module=PyQt5",
        "gui_main.py"
    ]
    
    print("开始打包...")
    print(f"执行命令: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("打包成功！")
        
        # 将生成的 exe 文件移动到 bin 文件夹
        exe_source = os.path.join("dist", "GNSS-RT-Monitor.exe")
        exe_target = os.path.join(bin_dir, "GNSS-RT-Monitor.exe")
        
        if os.path.exists(exe_source):
            if os.path.exists(exe_target):
                os.remove(exe_target)
            shutil.move(exe_source, exe_target)
            print(f"EXE 文件已移动到: {exe_target}")
        else:
            print(f"警告: 未找到生成的 exe 文件: {exe_source}")
            
    except subprocess.CalledProcessError as e:
        print(f"打包失败: {e}")
        print(f"错误输出: {e.stderr}")
        sys.exit(1)
    
    print("\n打包完成！")
    print(f"EXE 文件位置: {os.path.abspath(exe_target)}")

if __name__ == "__main__":
    main()

