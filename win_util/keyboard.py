import win32api
import win32con

KEY_MAP = {
    "0": 48, "1": 49, "2": 50, "3": 51, "4": 52, "5": 53, "6": 54, "7": 55, "8": 56, "9": 57,
    'F1': 112, 'F2': 113, 'F3': 114, 'F4': 115, 'F5': 116, 'F6': 117, 'F7': 118, 'F8': 119,
    'F9': 120, 'F10': 121, 'F11': 122, 'F12': 123, 'F13': 124, 'F14': 125, 'F15': 126, 'F16': 127,
    "A": 65, "B": 66, "C": 67, "D": 68, "E": 69, "F": 70, "G": 71, "H": 72, "I": 73, "J": 74,
    "K": 75, "L": 76, "M": 77, "N": 78, "O": 79, "P": 80, "Q": 81, "R": 82, "S": 83, "T": 84,
    "U": 85, "V": 86, "W": 87, "X": 88, "Y": 89, "Z": 90,
    'BACKSPACE': 8, 'TAB': 9, 'TABLE': 9, 'CLEAR': 12,
    'ENTER': 13, 'SHIFT': 16, 'CTRL': 17,
    'CONTROL': 17, 'ALT': 18, 'ALTER': 18, 'PAUSE': 19, 'BREAK': 19, 'CAPSLK': 20, 'CAPSLOCK': 20, 'ESC': 27,
    'SPACE': 32, 'SPACEBAR': 32, 'PGUP': 33, 'PAGEUP': 33, 'PGDN': 34, 'PAGEDOWN': 34, 'END': 35, 'HOME': 36,
    'LEFT': 37, 'UP': 38, 'RIGHT': 39, 'DOWN': 40, 'SELECT': 41, 'PRTSC': 42, 'PRINTSCREEN': 42, 'SYSRQ': 42,
    'SYSTEMREQUEST': 42, 'EXECUTE': 43, 'SNAPSHOT': 44, 'INSERT': 45, 'DELETE': 46, 'HELP': 47, 'WIN': 91,
    'WINDOWS': 91, 'NMLK': 144,
    'NUMLK': 144, 'NUMLOCK': 144, 'SCRLK': 145}


class KeyboardController:
    """键盘操作封装类，支持前台按键、后台按键及各种按键操作"""

    def __init__(self, hwnd: int):
        """
        :param hwnd: 可选，目标窗口句柄，用于后台按键
        """
        self.hwnd = hwnd

    def bg_key_down(self, key_code):
        if self.hwnd is None:
            raise ValueError("请在初始化时传入目标窗口句柄用于后台按键")
        if isinstance(key_code, str):
            key_code = KEY_MAP[key_code.upper()]
        win32api.SendMessage(self.hwnd, win32con.WM_KEYDOWN, key_code, 0)

    def bg_key_up(self, key_code):
        if self.hwnd is None:
            raise ValueError("请在初始化时传入目标窗口句柄用于后台按键")
        if isinstance(key_code, str):
            key_code = KEY_MAP[key_code.upper()]
        win32api.SendMessage(self.hwnd, win32con.WM_KEYUP, key_code, 0)

    def bg_press_key(self, key_code):
        """
        按一下按键
        :param key_code: 按键值，如91,代表WIN windows系统的系统按键，弹出开始菜单
        :return:
        """
        if isinstance(key_code, str):
            key_code = KEY_MAP[key_code.upper()]
        self.bg_key_down(key_code)
        self.bg_key_up(key_code)


# 保持原有函数接口以实现向后兼容
def key_up(key_code):
    """
    函数功能：抬起按键
    参   数：key:按键值
    """
    if isinstance(key_code, str):
        key_code = KEY_MAP[key_code.upper()]
    win32api.keybd_event(key_code, win32api.MapVirtualKey(key_code, 0), win32con.KEYEVENTF_KEYUP, 0)


def key_down(key_code):
    """
    函数功能：按下按键
    参   数：key:按键值
    """
    if isinstance(key_code, str):
        key_code = KEY_MAP[key_code.upper()]
    win32api.keybd_event(key_code, win32api.MapVirtualKey(key_code, 0), 0, 0)


def press_key(key_code):
    """
    按一下按键
    :param key_code: 按键值，如91,代表WIN windows系统的系统按键，弹出开始菜单
    :return:
    """
    if isinstance(key_code, str):
        key_code = KEY_MAP[key_code.upper()]
    key_down(key_code)
    key_up(key_code)


if __name__ == '__main__':
    # pressKey('WIN')  # 按下windows系统的系统按键，弹出开始菜单
    keyboard = KeyboardController(788824)
    # 模拟组合按键 9：tap键，18：alt键
    key_down(18)  # 按下alt键
    key_down(9)  # 按下tab键

    key_up('ALT')  # 松开alt键
    key_up('TAB')  # 松开tap键

    keyboard.bg_press_key("ESC")