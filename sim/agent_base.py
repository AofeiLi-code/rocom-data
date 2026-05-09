"""
Agent Protocol — 所有战斗智能体的统一接口

定义了 choose_action / on_game_end 两个核心方法，
以及 show_team_status 标记（用于区分人类玩家和 AI）。
"""

from typing import List, Optional, Tuple, Protocol

# Action = (技能索引,) | (-1,)汇合聚能 | (-2, 精灵索引)换人
Action = Tuple[int, ...]
GameHistory = List[Tuple]   # (BattleState深拷贝, Action_a, Action_b)


class AgentProtocol(Protocol):
    """
    战斗智能体协议。

    Attributes
    ----------
    team : str
        "a" 或 "b"，标识所属队伍。
    show_team_status : bool
        True = 人类玩家（自行打印状态）；False = AI（由引擎统一打印）。
    """

    team: str
    show_team_status: bool

    def choose_action(self, engine) -> Action:
        """根据当前引擎状态选择本回合动作。"""
        ...

    def on_game_end(self, history: GameHistory, winner: Optional[str]) -> None:
        """战斗结束回调 — 记录经验或打印结果等。"""
        ...
