"""MyTools Launcher 載入入口。

launcher 解壓 zip 後會找根目錄的 main_frame.py，呼叫
create_frame(parent) -> ttk.Frame，把工具嵌進右側內容區。

實際 UI 在 pack_gui.py（PackApp），這裡只做轉接。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pack_gui import create_frame as _create_frame


def create_frame(parent: tk.Widget) -> ttk.Frame:
    return _create_frame(parent)
