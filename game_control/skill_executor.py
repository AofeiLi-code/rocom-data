"""技能执行器 — 改编自 roco-kingdom-world-script"""
from loguru import logger
from game_control.controller import GameController
from game_control.utils import random_sleep


class SkillExecutor:
    def __init__(self, controller: GameController):
        self.ctrl = controller

    def escape_battle(self) -> bool:
        """逃跑：按 ESC 键 → 点 popup/yes.png 确认，找不到则用固定坐标兜底。"""
        self.ctrl.press_key("ESC")
        logger.info("按 ESC 逃跑")

        random_sleep(1)

        if not self.ctrl.find_and_click_with_timeout("popup/yes.png", timeout=2, similarity=0.8):
            logger.warning("确认按钮未找到，点击固定坐标")
            self.ctrl.click_at(1486, 1185)

        logger.info("逃跑执行完成")
        return True
