"""
NRC_SIM 战斗状态容器
"""

from dataclasses import dataclass
from typing import List, Optional

from sim.pokemon import Pokemon
from sim.types import Weather


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
    # 击倒对方一只精灵 → 对方 -1 格、己方 +1 格（上限 4）
    # 生命格归 0 判负
    lives_a: int = 4
    lives_b: int = 4

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
        )
