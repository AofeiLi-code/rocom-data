import time
import random


def random_sleep(base: float) -> None:
    """随机休眠 base ± 0.5s，最小 0.05s，防止固定延迟被检测。"""
    offset = random.uniform(-0.5, 0.5)
    time.sleep(max(0.05, base + offset))
