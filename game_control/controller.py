"""游戏控制器 — 封装 win_util，改编自 roco-kingdom-world-script"""
from pathlib import Path
from typing import Optional, Tuple, List, Union
import ctypes
import random
import time

from loguru import logger
from win_util import WinController

from game_control.utils import random_sleep
from game_control.exceptions import ImageNotFoundError

# 启动时声明 DPI-aware，避免 Windows 给缩放后的逻辑坐标导致 SetCursorPos 失败
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _screen_click(x: int, y: int) -> bool:
    """mouse_event ABSOLUTE 模式：一步搞定光标移动+点击，不依赖 SetCursorPos。"""
    user32 = ctypes.windll.user32
    MOUSEEVENTF_MOVE     = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP   = 0x0004
    MOUSEEVENTF_ABSOLUTE = 0x8000
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79

    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    nx = int((int(x) - vx) * 65535 / max(1, vw - 1))
    ny = int((int(y) - vy) * 65535 / max(1, vh - 1))

    # 移动到目标位置 → 等游戏注册 hover → 按下 → 保持 → 抬起
    user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE, nx, ny, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE, nx, ny, 0, 0)
    return True


class GameController:
    TEMPLATE_BASE = Path(__file__).parent.parent / "assets" / "templates"

    def __init__(self, hwnd: int, settings: dict):
        self.hwnd = hwnd
        self.settings = settings
        self.win = WinController(hwnd=hwnd)
        self._similarity = settings.get("similarity", 0.8)

    def set_scale(self, reference_height: int) -> None:
        """按参考高度与当前窗口高度计算模板缩放比，让模板在任意窗口尺寸下都能匹配。"""
        import win32gui
        _, _, _, win_h = win32gui.GetClientRect(self.hwnd)
        scale = win_h / reference_height if reference_height > 0 else 1.0
        self.win.image_finder.scale = scale
        logger.info(f"模板缩放比: {scale:.3f}（参考高度={reference_height}，当前窗口高度={win_h}）")

    def capture(self) -> None:
        self.win.update_screenshot_cache()

    def get_screenshot(self):
        return self.win.image_finder.screenshot_cache

    def _find_single(
        self,
        template_path: str,
        similarity: float,
        x0: int, y0: int, x1: int, y1: int,
    ) -> Tuple[int, int]:
        full_path = self.TEMPLATE_BASE / template_path
        result = self.win.image_finder.bg_find_pic_by_cache(
            str(full_path), x0, y0, x1, y1, similarity=similarity
        )
        if result != (-1, -1):
            logger.debug(f"找到: {template_path} @ {result}")
        return result

    def find_image(
        self,
        template: Union[str, List[str]],
        similarity: float = None,
        x0: int = 0, y0: int = 0, x1: int = 99999, y1: int = 99999,
        _capture: bool = True,
    ) -> Tuple[int, int]:
        if _capture:
            self.capture()
        sim = similarity or self._similarity
        templates = [template] if isinstance(template, str) else template
        for t in templates:
            pos = self._find_single(t, sim, x0, y0, x1, y1)
            if pos != (-1, -1):
                return pos
        return -1, -1

    def find_image_with_timeout(
        self,
        template: Union[str, List[str]],
        timeout: float = 5,
        similarity: float = None,
        x0: int = 0, y0: int = 0, x1: int = 99999, y1: int = 99999,
    ) -> Optional[Tuple[int, int]]:
        start = time.time()
        while time.time() - start < timeout:
            pos = self.find_image(template, similarity, x0, y0, x1, y1)
            if pos != (-1, -1):
                return pos
            random_sleep(0.3)
        return None

    def find_and_click_with_timeout(
        self,
        template: Union[str, List[str]],
        timeout: float = 5,
        similarity: float = None,
    ) -> bool:
        pos = self.find_image_with_timeout(template, timeout=timeout, similarity=similarity)
        if pos is None:
            return False
        return self.click_at(*pos)

    def find_image_multiscale(
        self,
        template: str,
        similarity: float = 0.65,
        x0: int = 0, y0: int = 0, x1: int = 99999, y1: int = 99999,
        verbose: bool = False,
    ) -> tuple:
        """多尺度模板搜索。每次只缩放模板，取最高分；verbose=True 时打印每个 scale 的最高分。

        注意：失败时不再自动写调试截图（防止磁盘爆满）。需要诊断请显式调
        `save_debug_screenshot()`。
        """
        import cv2, numpy as np

        self.capture()
        screenshot = self.get_screenshot()
        if screenshot is None:
            logger.warning(f"[{template}] 截图为空，BitBlt 可能失败")
            return (-1, -1)

        full_path = self.TEMPLATE_BASE / template
        orig_template = cv2.imdecode(np.fromfile(str(full_path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if orig_template is None:
            logger.warning(f"[{template}] 模板加载失败：{full_path}")
            return (-1, -1)

        th, tw = orig_template.shape[:2]
        sh, sw = screenshot.shape[:2]
        t_channels = orig_template.shape[2] if len(orig_template.shape) > 2 else 1
        s_channels = screenshot.shape[2] if len(screenshot.shape) > 2 else 1

        if verbose:
            t_mean, t_std = float(orig_template.mean()), float(orig_template.std())
            s_mean, s_std = float(screenshot.mean()), float(screenshot.std())
            logger.info(
                f"[{template}] 模板={tw}x{th}x{t_channels} (均值={t_mean:.1f} 标准差={t_std:.1f})，"
                f"截图={sw}x{sh}x{s_channels} (均值={s_mean:.1f} 标准差={s_std:.1f})"
            )
            if s_std < 1.0:
                logger.error(f"[{template}] ⚠️ 截图几乎是纯色（标准差={s_std:.2f}），BitBlt 可能返回黑屏")

        if t_channels != s_channels:
            if t_channels == 4:
                orig_template = cv2.cvtColor(orig_template, cv2.COLOR_BGRA2BGR)
            elif s_channels == 4:
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

        x1 = min(x1, sw)
        y1 = min(y1, sh)
        big_img = screenshot[y0:y1, x0:x1] if (x0 or y0 or x1 < sw or y1 < sh) else screenshot

        scales = [round(s * 0.05, 2) for s in range(6, 33)]  # 0.30 ~ 1.60
        best_pos = (-1, -1)
        best_score = 0.0
        best_scale = 0.0
        score_log = []

        for scale in scales:
            new_w, new_h = max(1, int(tw * scale)), max(1, int(th * scale))
            if new_w > big_img.shape[1] or new_h > big_img.shape[0]:
                continue
            scaled = cv2.resize(orig_template, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            result = cv2.matchTemplate(big_img, scaled, cv2.TM_CCOEFF_NORMED)
            _, max_score, _, max_loc = cv2.minMaxLoc(result)
            score_log.append((scale, max_score))
            if max_score > best_score:
                best_score = max_score
                best_scale = scale
                best_pos = (max_loc[0] + x0 + new_w // 2, max_loc[1] + y0 + new_h // 2)

        if verbose:
            top5 = sorted(score_log, key=lambda x: -x[1])[:5]
            logger.info(f"[{template}] 最高5个分数: " + ", ".join(f"{s:.2f}@{sc}" for sc, s in top5))

        if best_score >= similarity:
            logger.info(f"[{template}] 匹配成功 scale={best_scale} score={best_score:.3f} @ {best_pos}")
            return best_pos
        if verbose:
            logger.warning(f"[{template}] 匹配失败，最高分 {best_score:.3f}（阈值 {similarity}）@ scale={best_scale}")
        return (-1, -1)

    def click_at(self, x: int, y: int, x_range: int = 10, y_range: int = 10) -> bool:
        """在游戏窗口客户区坐标 (x,y) 点击，自动转换为屏幕坐标后用 SendInput 模拟。"""
        import win32gui
        ox = random.randint(-x_range, x_range) if x_range else 0
        oy = random.randint(-y_range, y_range) if y_range else 0
        client_x, client_y = x + ox, y + oy
        screen_x, screen_y = win32gui.ClientToScreen(self.hwnd, (client_x, client_y))
        logger.debug(f"点击 客户区({client_x},{client_y}) → 屏幕({screen_x},{screen_y})")
        return _screen_click(screen_x, screen_y)

    def save_debug_screenshot(self, name: str) -> Optional[Path]:
        import cv2
        img = self.get_screenshot()
        if img is None:
            return None
        debug_dir = Path(__file__).parent.parent / "logs" / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = debug_dir / f"{name}_{int(time.time())}.png"
        cv2.imwrite(str(path), img)
        logger.debug(f"调试截图: {path}")
        return path
