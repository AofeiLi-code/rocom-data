"""
NRC_SIM 战斗状态容器
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sim.pokemon import Pokemon
from sim.types import Weather
from sim.mark_system import TeamMark, MarkCategory, MarkType


@dataclass
class BattleState:
    """战斗状态 — 包含双方队伍和当前出战索引"""

    team_a: List[Pokemon]
    team_b: List[Pokemon]
    current_a: int = 0
    current_b: int = 0
    turn: int = 1
    weather: Weather = Weather.NONE
    weather_turns: int = 0  # 天气剩余回合数（0 = 无天气）
    # roco-world 胜利条件：每方 4 格生命值
    # 己方精灵倒下 → 己方 -1 格（对方不变）
    # 生命格归 0 判负
    lives_a: int = 4
    lives_b: int = 4

    # 特性计数器 (精灵名 -> 整数计数)，用于需要积累效果的特性
    ability_counters: Dict[str, int] = field(default_factory=dict)

    # 队伍印记（每队分正面/负面各一槽）
    # 正面印记：湿润/龙噬/蓄势/风起/蓄电/光合/攻击
    # 负面印记：减速/降灵/星陨/中毒/棘刺
    pos_mark_a: Optional[TeamMark] = None   # A队正面印记
    neg_mark_a: Optional[TeamMark] = None   # A队负面印记
    pos_mark_b: Optional[TeamMark] = None   # B队正面印记
    neg_mark_b: Optional[TeamMark] = None   # B队负面印记

    # ------------------------------------------------------------------
    # 便捷访问
    # ------------------------------------------------------------------
    def get_current(self, team: str) -> Pokemon:
        """获取指定队伍的当前出战精灵"""
        if team == "a":
            return self.team_a[self.current_a]
        return self.team_b[self.current_b]

    def get_team(self, team: str) -> List[Pokemon]:
        if team == "a":
            return self.team_a
        return self.team_b

    def get_current_idx(self, team: str) -> int:
        return self.current_a if team == "a" else self.current_b

    def set_current_idx(self, team: str, idx: int) -> None:
        if team == "a":
            self.current_a = idx
        else:
            self.current_b = idx

    def enemy_team_id(self, team: str) -> str:
        return "b" if team == "a" else "a"

    # ------------------------------------------------------------------
    # 印记访问与操作
    # ------------------------------------------------------------------
    def get_mark(self, team: str, category: MarkCategory) -> Optional[TeamMark]:
        """获取指定队伍指定类别的印记"""
        if category == MarkCategory.POSITIVE:
            return self.pos_mark_a if team == "a" else self.pos_mark_b
        else:
            return self.neg_mark_a if team == "a" else self.neg_mark_b

    def set_mark(self, team: str, mark: TeamMark) -> None:
        """
        为指定队伍设置印记。
        同类别的旧印记直接被覆盖（异种顶替），
        同种印记则叠加层数。
        """
        cat = mark.category
        existing = self.get_mark(team, cat)
        if existing is not None and existing.mark_type == mark.mark_type:
            # 同种印记 → 叠层
            existing.stacks += mark.stacks
            return
        # 不同种或无旧印记 → 覆盖/新建
        if cat == MarkCategory.POSITIVE:
            if team == "a":
                self.pos_mark_a = mark
            else:
                self.pos_mark_b = mark
        else:
            if team == "a":
                self.neg_mark_a = mark
            else:
                self.neg_mark_b = mark

    def clear_mark(self, team: str, category: MarkCategory) -> None:
        """清除指定队伍指定类别的印记"""
        if category == MarkCategory.POSITIVE:
            if team == "a":
                self.pos_mark_a = None
            else:
                self.pos_mark_b = None
        else:
            if team == "a":
                self.neg_mark_a = None
            else:
                self.neg_mark_b = None

    def get_positive_mark(self, team: str) -> Optional[TeamMark]:
        return self.pos_mark_a if team == "a" else self.pos_mark_b

    def get_negative_mark(self, team: str) -> Optional[TeamMark]:
        return self.neg_mark_a if team == "a" else self.neg_mark_b

    # ------------------------------------------------------------------
    # 深复制（MCTS 专用，比 copy.deepcopy 快 3-5x）
    # ------------------------------------------------------------------
    def deep_copy(self) -> "BattleState":
        return BattleState(
            team_a=[p.copy_state() for p in self.team_a],
            team_b=[p.copy_state() for p in self.team_b],
            current_a=self.current_a,
            current_b=self.current_b,
            turn=self.turn,
            weather=self.weather,
            weather_turns=self.weather_turns,
            lives_a=self.lives_a,
            lives_b=self.lives_b,
            ability_counters=dict(self.ability_counters),
            pos_mark_a=self.pos_mark_a.copy() if self.pos_mark_a else None,
            neg_mark_a=self.neg_mark_a.copy() if self.neg_mark_a else None,
            pos_mark_b=self.pos_mark_b.copy() if self.pos_mark_b else None,
            neg_mark_b=self.neg_mark_b.copy() if self.neg_mark_b else None,
        )
