import os
import sys


def get_ffmpeg_path() -> str:
    """获取ffmpeg路径,支持Nuitka和PyInstaller打包"""
    if getattr(sys, "frozen", False):
        # PyInstaller使用_MEIPASS
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, "ffmpeg.exe")
        # Nuitka standalone模式,可执行文件在同一目录
        exe_dir = os.path.dirname(sys.executable)
        nuitka_path = os.path.join(exe_dir, "ffmpeg.exe")
        if os.path.exists(nuitka_path):
            return nuitka_path
        # 如果不在exe目录,可能在当前工作目录
        return os.path.join(os.getcwd(), "ffmpeg.exe")
    # 开发模式
    return os.path.join(os.path.dirname(__file__), "ffmpeg.exe")


def ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建"""
    if not os.path.exists(path):
        os.makedirs(path)
