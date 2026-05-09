import win32gui
from loguru import logger
from game_control.exceptions import GameWindowNotFoundError


def find_window(class_name: str = "UnrealWindow", title: str = "洛克王国：世界") -> int:
    """查找游戏窗口，返回 hwnd。"""
    hwnd = win32gui.FindWindow(class_name, title)
    if hwnd:
        logger.info(f"找到游戏窗口: hwnd={hwnd}")
        return hwnd

    result = []

    def _cb(hwnd, _):
        if title in win32gui.GetWindowText(hwnd):
            result.append(hwnd)

    win32gui.EnumWindows(_cb, None)

    if result:
        logger.info(f"部分匹配找到窗口: hwnd={result[0]}")
        return result[0]

    raise GameWindowNotFoundError(f"未找到窗口: {title}")
