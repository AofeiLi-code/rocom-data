from win_util.image import ImageFinder
from win_util.keyboard import KeyboardController
from win_util.mouse import MouseController


class WinController:
    """Windows 控制器：聚合图像查找、键盘、鼠标。OCR 因 easyocr 重依赖且 PVP 无需，已剥离。"""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.image_finder: ImageFinder = ImageFinder(hwnd=hwnd)
        self.keyboard: KeyboardController = KeyboardController(hwnd)
        self.mouse: MouseController = MouseController(hwnd=hwnd)

    # 图像
    def find_image(self, small_picture_path: str, x0=0, y0=0, x1=99999, y1=99999, similarity=0.8):
        return self.image_finder.bg_find_pic_by_cache(small_picture_path, x0, y0, x1, y1, similarity)

    def update_screenshot_cache(self):
        return self.image_finder.update_screenshot_cache()

    # 键盘
    def press_key(self, key_code):
        self.keyboard.bg_press_key(key_code)

    def key_down(self, key_code):
        self.keyboard.bg_key_down(key_code)

    def key_up(self, key_code):
        self.keyboard.bg_key_up(key_code)
