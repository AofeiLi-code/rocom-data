import random
import time

import win32api
import win32con
from loguru import logger


class MouseController:
    """鼠标后台点击 / 贝塞尔滑动封装。基于 SendMessage，目标窗口可在后台。"""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd

    def bg_left_click(self, *point, x_range=0, y_range=0) -> bool:
        if point is None or (len(point) == 1 and point[0] is None):
            return False

        x, y = -1, -1
        if len(point) == 1 and isinstance(point[0], (tuple, list)):
            x, y = point[0][0], point[0][1]
        elif len(point) == 2:
            x, y = point

        if x < 0 or y < 0:
            return False

        x_pos = max(0, random.randint(x - x_range, x + x_range))
        y_pos = max(0, random.randint(y - y_range, y + y_range))

        if x_range or y_range:
            logger.debug(f"在基准点 {point} 周围随机点击: x={x_pos}, y={y_pos}")

        long_position = win32api.MAKELONG(x_pos, y_pos)
        win32api.SendMessage(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, long_position)
        win32api.SendMessage(self.hwnd, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON, long_position)
        return True

    def bg_swipe(self, start_x: int, start_y: int, end_x: int, end_y: int,
                 steps: int = 20, duration: float = 0.5,
                 curve_factor: float = 0.3) -> bool:
        """贝塞尔曲线滑动。"""
        points = self._generate_bezier_points(start_x, start_y, end_x, end_y, steps, curve_factor)

        long_start = win32api.MAKELONG(int(points[0][0]), int(points[0][1]))
        win32api.SendMessage(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, long_start)

        for i in range(1, len(points) - 1):
            x, y = points[i]
            long_current = win32api.MAKELONG(int(x), int(y))
            win32api.SendMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, long_current)
            t = i / (len(points) - 1)
            if t < 0.2:
                delay = duration * 0.08
            elif t > 0.8:
                delay = duration * 0.06
            else:
                delay = duration * 0.03
            delay *= random.uniform(0.8, 1.2)
            time.sleep(delay)

        end_x_final, end_y_final = points[-1]
        long_end = win32api.MAKELONG(int(end_x_final), int(end_y_final))
        win32api.SendMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, long_end)
        return True

    def _generate_bezier_points(self, start_x: int, start_y: int,
                                 end_x: int, end_y: int,
                                 steps: int, curve_factor: float):
        dx = end_x - start_x
        dy = end_y - start_y
        offset_range = max(30, int((abs(dx) + abs(dy)) * curve_factor * 0.3))
        ctrl1_x = start_x + dx * curve_factor + random.randint(-offset_range, offset_range)
        ctrl1_y = start_y + dy * curve_factor * random.uniform(-0.5, 0.5) + random.randint(-offset_range, offset_range)
        ctrl2_x = end_x - dx * curve_factor + random.randint(-offset_range, offset_range)
        ctrl2_y = end_y - dy * curve_factor * random.uniform(-0.5, 0.5) + random.randint(-offset_range, offset_range)

        points = []
        for i in range(steps):
            t = i / (steps - 1) if steps > 1 else 1
            one_minus_t = 1 - t
            one_minus_t_sq = one_minus_t * one_minus_t
            one_minus_t_cube = one_minus_t_sq * one_minus_t
            t_sq = t * t
            t_cube = t_sq * t

            x = (one_minus_t_cube * start_x +
                 3 * one_minus_t_sq * t * ctrl1_x +
                 3 * one_minus_t * t_sq * ctrl2_x +
                 t_cube * end_x)
            y = (one_minus_t_cube * start_y +
                 3 * one_minus_t_sq * t * ctrl1_y +
                 3 * one_minus_t * t_sq * ctrl2_y +
                 t_cube * end_y)
            points.append((x, y))
        return points
