import time
from pathlib import Path
from typing import List, Tuple, Any, Optional

import cv2
import numpy as np
import win32gui
import win32ui
from loguru import logger


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def to_project_path(path: str) -> str:
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str(PROJECT_ROOT / p)


def _match_template_nms(matches: List[Tuple[int, int, float]], distance_threshold: float = 10) -> List[Tuple[int, int, float]]:
    """模板匹配结果去重（曼哈顿距离）"""
    if not matches:
        return []
    matches.sort(key=lambda m: m[2], reverse=True)
    unique_points = []
    for x, y, score in matches:
        if any(abs(x - ux) <= distance_threshold and abs(y - uy) <= distance_threshold for ux, uy, _ in unique_points):
            continue
        unique_points.append((x, y, score))
    return unique_points


class ScreenCapture:
    """窗口截图：使用屏幕 DC + BitBlt（对 Unreal/DirectX 硬件加速窗口比 PrintWindow 更可靠）。

    要求：游戏窗口可见（不能最小化、不能被完全遮挡）。
    """

    def __init__(self, hwnd: int):
        self.hwnd = hwnd

    def capture_window_region(self, x0=0, y0=0, x1=99999, y1=99999) -> np.ndarray:
        client_rect = win32gui.GetClientRect(self.hwnd)
        client_width = client_rect[2] - client_rect[0]
        client_height = client_rect[3] - client_rect[1]

        x0 = max(x0, client_rect[0])
        y0 = max(y0, client_rect[1])
        x1 = min(x1, client_width)
        y1 = min(y1, client_height)

        if x0 >= x1 or y0 >= y1:
            raise ValueError(f"无效区域: ({x0}, {y0}) - ({x1}, {y1})")

        try:
            client_origin = win32gui.ClientToScreen(self.hwnd, (0, 0))
        except Exception:
            client_origin = (0, 0)
        screen_x, screen_y = client_origin

        screen_dc_handle = win32gui.GetDC(0)
        mfc_screen_dc = win32ui.CreateDCFromHandle(screen_dc_handle)
        save_dc = mfc_screen_dc.CreateCompatibleDC()
        save_bitmap = win32ui.CreateBitmap()
        save_bitmap.CreateCompatibleBitmap(mfc_screen_dc, client_width, client_height)
        save_dc.SelectObject(save_bitmap)

        save_dc.BitBlt(
            (0, 0), (client_width, client_height),
            mfc_screen_dc, (screen_x, screen_y),
            0x00CC0020,   # SRCCOPY
        )

        bmp_info = save_bitmap.GetInfo()
        bmp_str = save_bitmap.GetBitmapBits(True)
        img = np.frombuffer(bmp_str, dtype='uint8').reshape(
            (bmp_info['bmHeight'], bmp_info['bmWidth'], 4)
        )

        win32gui.DeleteObject(save_bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_screen_dc.DeleteDC()
        win32gui.ReleaseDC(0, screen_dc_handle)

        img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return img_bgr[y0:y1, x0:x1]


class ImageFinder:
    """模板匹配、找图封装。"""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.screenshot_capture = ScreenCapture(hwnd=hwnd)
        self.screenshot_cache: Optional[np.ndarray] = None
        self.scale: float = 1.0   # 模板缩放比例，1.0 = 原始大小
        self.update_screenshot_cache()

    def update_screenshot_cache(self):
        self.screenshot_cache = self.screenshot_capture.capture_window_region()
        return self.screenshot_cache

    def bg_find_pic_by_cache(self, small_picture_path, x0=0, y0=0, x1=99999, y1=99999, similarity=0.8) -> Tuple[int, int]:
        return self.bg_find_pic(self.screenshot_cache, small_picture_path, x0, y0, x1, y1, similarity)

    def bg_find_pic_all_by_cache(self, small_picture_path, x0=0, y0=0, x1=99999, y1=99999, similarity=0.8) -> List[Tuple[int, int, float]]:
        return self.bg_find_pic_all(self.screenshot_cache, small_picture_path, x0, y0, x1, y1, similarity)

    def bg_find_pic_all(self, screenshot: Optional[Any], small_img_path, x0=0, y0=0, x1=99999, y1=99999, similarity=0.8) -> List[Tuple[int, int, float]]:
        """在截图中匹配模板，返回所有大于阈值的结果（灰度+HSV-H 直方图合成相似度，按分降序）。"""
        if screenshot is None:
            return []

        small_img_path = to_project_path(small_img_path)
        small_img = cv2.imdecode(np.fromfile(small_img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if small_img is None:
            return []

        if abs(self.scale - 1.0) > 0.01:
            h, w = small_img.shape[:2]
            new_w = max(1, int(w * self.scale))
            new_h = max(1, int(h * self.scale))
            small_img = cv2.resize(small_img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        big_img = screenshot
        if x0 or y0 or x1 < 99999 or y1 < 99999:
            h_img, w_img = big_img.shape[:2]
            x1 = min(x1, w_img)
            y1 = min(y1, h_img)
            big_img = big_img[y0:y1, x0:x1]

        result = cv2.matchTemplate(big_img, small_img, cv2.TM_CCOEFF_NORMED)
        h, w = small_img.shape[:2]

        # 灰度阈值先用 0.6 粗筛，避免 HSV 直方图算太多次
        loc = np.where(result >= max(0.6, similarity - 0.15))
        matches: List[Tuple[int, int, float]] = []
        for pt in zip(*loc[::-1]):
            x = x0 + pt[0]
            y = y0 + pt[1]
            roi = screenshot[y:y+h, x:x+w]
            if roi.size == 0:
                continue

            tpl_hsv = cv2.cvtColor(small_img, cv2.COLOR_BGR2HSV)
            roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            tpl_hist_h = cv2.calcHist([tpl_hsv], [0], None, [180], [0, 180])
            roi_hist_h = cv2.calcHist([roi_hsv], [0], None, [180], [0, 180])
            cv2.normalize(tpl_hist_h, tpl_hist_h, 0, 1, cv2.NORM_MINMAX)
            cv2.normalize(roi_hist_h, roi_hist_h, 0, 1, cv2.NORM_MINMAX)
            hist_dist = cv2.compareHist(tpl_hist_h, roi_hist_h, cv2.HISTCMP_BHATTACHARYYA)
            color_score = max(0.0, 1.0 - hist_dist)

            gray_score = result[pt[1], pt[0]]
            final_score = 0.7 * gray_score + 0.3 * color_score

            if final_score >= similarity:
                matches.append((x + w // 2, y + h // 2, final_score))

        matches.sort(key=lambda m: m[2], reverse=True)
        return _match_template_nms(matches)

    def bg_find_pic(self, screenshot: Optional[Any], small_img_path, x0=0, y0=0, x1=99999, y1=99999, similarity=0.8) -> Tuple[int, int]:
        matches = self.bg_find_pic_all(screenshot, small_img_path, x0, y0, x1, y1, similarity)
        if not matches:
            return -1, -1
        center_x, center_y, final_score = matches[0]
        logger.debug(f"匹配成功: {Path(small_img_path).stem} | 位置: ({center_x},{center_y}) | 相似度: {final_score:.4f}")
        return center_x, center_y

    def bg_find_pic_with_timeout(self, small_picture_path, timeout=5, x0=0, y0=0, x1=99999, y1=99999, similarity=0.8):
        """带超时轮询的图片查找。"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            self.update_screenshot_cache()
            point = self.bg_find_pic_by_cache(small_picture_path, x0, y0, x1, y1, similarity)
            if point is not None and point[0] != -1 and point[1] != -1:
                return point
            time.sleep(0.2)
        return -1, -1
