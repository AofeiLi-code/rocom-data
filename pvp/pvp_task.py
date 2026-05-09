"""PVP 自动战斗 — 咔咔鸟脚本

开局序列：暴风眼 → 追打 → 音波弹 → 聚盐（各一次）
主循环：优先音波弹，变暗则用聚盐，超时全黑则按X聚能
死亡：换宠面板出现 → 按键选精灵 → ESC逃跑
"""
import time
from typing import Optional, Tuple
from loguru import logger

from game_control.controller import GameController
from game_control.skill_executor import SkillExecutor
from game_control.utils import random_sleep
from game_control.exceptions import PvpAbortError
from pvp.config import (
    LEFT_HALF,
    OPEN_SEQUENCE, MAIN_SKILLS,
    SWITCH_PANEL_TEMPLATE, SWITCH_ELF_KEY,
    START_CHALLENGE_TEMPLATE, START_CHALLENGE_SIMILARITY,
    SKILL_SIMILARITY, PANEL_SIMILARITY,
    DARK_TIMEOUT, POST_SKILL_DELAY, POLL_INTERVAL, SWITCH_DELAY,
)

_PHASE_IDLE = "idle"   # 等待"开始挑战"按钮出现并点击
_PHASE_WAIT = "wait"   # 已点击，等待技能出现（战斗加载中）
_PHASE_OPEN = "open"   # 开局固定序列
_PHASE_MAIN = "main"   # 主循环
_IDLE_TIMEOUT = 300.0  # 等待按钮超时（5分钟，含排队时间）
_WAIT_TIMEOUT = 60.0   # 点击后等待技能出现超时
_MAX_CONSEC_CHARGES = 3  # 战斗中连续 N 次只能聚能（找不到任何技能）→ 中止脚本


class PvpTask:

    def __init__(self, controller: GameController, skill_executor: SkillExecutor):
        self.ctrl = controller
        self.executor = skill_executor

    def run(self) -> str:
        phase = _PHASE_IDLE
        open_idx = 0
        last_cast = time.time()
        phase_start = time.time()
        consec_charges = 0   # 连续聚能次数（无任何技能识别），跨过阈值即中止

        logger.info("等待「开始挑战」按钮出现…")

        while True:
            self.ctrl.capture()

            # 死亡检测优先（进入战斗后才开启）
            if phase in (_PHASE_OPEN, _PHASE_MAIN) and self._switch_panel_visible():
                logger.info("换宠面板出现 → 咔咔鸟死亡，选精灵后逃跑")
                self._switch_and_escape()
                return "escaped"

            # ── 等待并点击「开始挑战」按钮 ────────────────────────────
            if phase == _PHASE_IDLE:
                pos = self._find_start_challenge()
                if pos is not None:
                    self.ctrl.click_at(*pos)
                    logger.info(f"点击「开始挑战」@ {pos}，等待匹配…")
                    phase = _PHASE_WAIT
                    phase_start = time.time()
                elif time.time() - phase_start > _IDLE_TIMEOUT:
                    logger.warning("超时未找到「开始挑战」按钮")
                    return "timeout"
                else:
                    random_sleep(POLL_INTERVAL)

            # ── 已点击，等待技能出现（排队+加载阶段） ─────────────────
            elif phase == _PHASE_WAIT:
                if self._find_any_skill() is not None:
                    logger.info("检测到技能，挑战开始")
                    phase = _PHASE_OPEN
                    last_cast = time.time()
                elif self._find_start_challenge() is not None:
                    # 按钮重新出现 = 匹配取消，重新点击
                    logger.info("「开始挑战」按钮重新出现，重新点击")
                    phase = _PHASE_IDLE
                    phase_start = time.time()
                elif time.time() - phase_start > _WAIT_TIMEOUT:
                    logger.warning("点击后超时未进入战斗")
                    return "timeout"
                else:
                    random_sleep(POLL_INTERVAL)

            # ── 开局序列 ──────────────────────────────────────────────
            elif phase == _PHASE_OPEN:
                template = OPEN_SEQUENCE[open_idx]
                pos = self._find_skill(template)
                if pos is not None:
                    self._click_skill(pos, template)
                    last_cast = time.time()
                    consec_charges = 0
                    open_idx += 1
                    if open_idx >= len(OPEN_SEQUENCE):
                        phase = _PHASE_MAIN
                        logger.info("开局序列完成，进入主循环")
                elif time.time() - last_cast > DARK_TIMEOUT:
                    self._press_charge()
                    last_cast = time.time()
                    consec_charges += 1
                    self._abort_if_stuck(consec_charges)
                else:
                    random_sleep(POLL_INTERVAL)

            # ── 主循环 ────────────────────────────────────────────────
            elif phase == _PHASE_MAIN:
                used = False
                for template in MAIN_SKILLS:
                    pos = self._find_skill(template)
                    if pos is not None:
                        self._click_skill(pos, template)
                        last_cast = time.time()
                        consec_charges = 0
                        used = True
                        break

                if not used:
                    if time.time() - last_cast > DARK_TIMEOUT:
                        self._press_charge()
                        last_cast = time.time()
                        consec_charges += 1
                        self._abort_if_stuck(consec_charges)
                    else:
                        random_sleep(POLL_INTERVAL)

    # ── 检测 ──────────────────────────────────────────────────────────

    def _find_start_challenge(self) -> Optional[Tuple[int, int]]:
        """多尺度搜索「开始挑战」按钮，每 10 秒输出一次诊断日志。"""
        # 减少日志刷屏，只在每秒首次搜索时 verbose
        now = time.time()
        verbose = (now - getattr(self, "_last_verbose", 0)) > 10.0
        if verbose:
            self._last_verbose = now

        pos = self.ctrl.find_image_multiscale(
            START_CHALLENGE_TEMPLATE,
            similarity=START_CHALLENGE_SIMILARITY,
            verbose=verbose,
        )
        return pos if pos != (-1, -1) else None

    def _find_skill(self, template: str) -> Optional[Tuple[int, int]]:
        x0, y0, x1, y1 = LEFT_HALF
        pos = self.ctrl.find_image(
            template, similarity=SKILL_SIMILARITY,
            x0=x0, y0=y0, x1=x1, y1=y1,
            _capture=False,
        )
        return pos if pos != (-1, -1) else None

    def _find_any_skill(self) -> Optional[Tuple[int, int]]:
        for template in OPEN_SEQUENCE:
            pos = self._find_skill(template)
            if pos is not None:
                return pos
        return None

    def _switch_panel_visible(self) -> bool:
        x0, y0, x1, y1 = LEFT_HALF
        pos = self.ctrl.find_image(
            SWITCH_PANEL_TEMPLATE, similarity=PANEL_SIMILARITY,
            x0=x0, y0=y0, x1=x1, y1=y1,
            _capture=False,
        )
        return pos != (-1, -1)

    # ── 操作 ──────────────────────────────────────────────────────────

    def _click_skill(self, pos: Tuple[int, int], template: str) -> None:
        self.ctrl.click_at(*pos)
        logger.info(f"释放 {template.split('/')[-1]} @ {pos}")
        random_sleep(POST_SKILL_DELAY)

    def _press_charge(self) -> None:
        self.ctrl.press_key("X")
        logger.info("技能全黑，按X聚能")
        random_sleep(POST_SKILL_DELAY)

    def _abort_if_stuck(self, consec_charges: int) -> None:
        """战斗中连续 _MAX_CONSEC_CHARGES 次都识别不到任何技能 → 存图 + 抛错。"""
        if consec_charges < _MAX_CONSEC_CHARGES:
            return
        path = self.ctrl.save_debug_screenshot("pvp_skill_match_failed")
        msg = (
            f"连续 {consec_charges} 次未识别到任何技能（疑似模板尺寸/对齐问题）。"
            f"调试截图已存：{path}"
        )
        logger.error(msg)
        raise PvpAbortError(msg)

    def _switch_and_escape(self) -> None:
        """按键选精灵 → ESC逃跑。"""
        random_sleep(0.5)
        self.ctrl.press_key(SWITCH_ELF_KEY)
        logger.info(f"按键 [{SWITCH_ELF_KEY}] 换宠")
        random_sleep(SWITCH_DELAY)
        self.executor.escape_battle()
