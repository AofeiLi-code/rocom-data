"""
经验数据库 (ExperienceDB)

记录历史对战中各「状态−动作」对的胜负统计。
在 MCTS rollout 阶段对高胜率动作给予更高采样权重，
使 AI 随对战场数增加逐步"学聪明"。

状态指纹（轻量，不存完整状态）：
  己方精灵名 | HP段 | 能量段 | 敌方精灵名 | 敌方HP段 | 己方生命格 | 敌方生命格

HP 段：0=低危(≤25%), 1=中低(≤50%), 2=中高(≤75%), 3=满(>75%)
能量段：0=低(0-3), 1=中(4-6), 2=高(7-10)
"""

import json
import os
from typing import Dict, List, Optional, Tuple, Any

# 经验数据库默认存储目录
_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "experience",
)


# ============================================================
# 工具函数
# ============================================================

def _hp_bucket(hp: int, max_hp: int) -> int:
    if max_hp <= 0:
        return 0
    pct = hp / max_hp
    if pct <= 0.25:
        return 0
    if pct <= 0.50:
        return 1
    if pct <= 0.75:
        return 2
    return 3


def _energy_bucket(energy: int) -> int:
    if energy <= 3:
        return 0
    if energy <= 6:
        return 1
    return 2


def _action_key(action: tuple, pokemon) -> str:
    """Action → 可序列化字符串键"""
    if action[0] == -1:
        return "gather"
    if action[0] == -2:
        return f"switch_{action[1]}"
    idx = action[0]
    if 0 <= idx < len(pokemon.skills):
        return pokemon.skills[idx].name
    return f"skill_{idx}"


def state_key(state, team: str) -> str:
    """生成轻量级状态指纹"""
    opp = "b" if team == "a" else "a"
    me  = state.get_current(team)
    en  = state.get_current(opp)
    my_lives  = state.lives_a if team == "a" else state.lives_b
    opp_lives = state.lives_b if team == "a" else state.lives_a
    return (
        f"{me.name}|{_hp_bucket(me.current_hp, me.hp)}"
        f"|{_energy_bucket(me.energy)}"
        f"|{en.name}|{_hp_bucket(en.current_hp, en.hp)}"
        f"|{my_lives}|{opp_lives}"
    )


# ============================================================
# 单条统计
# ============================================================

class ActionStats:
    __slots__ = ("wins", "total")

    def __init__(self, wins: float = 0.0, total: int = 0):
        self.wins  = wins
        self.total = total

    def win_rate(self) -> float:
        return self.wins / self.total if self.total > 0 else 0.5

    def to_dict(self) -> dict:
        return {"w": self.wins, "n": self.total}

    @classmethod
    def from_dict(cls, d: dict) -> "ActionStats":
        return cls(wins=d["w"], total=d["n"])


# ============================================================
# 经验数据库
# ============================================================

class ExperienceDB:
    """
    记录 (team, state_key, action_key) → ActionStats

    使用示例
    --------
    db = ExperienceDB.load_or_create("毒队")

    # 一局结束后记录
    db.record_game(history, winner)   # history: [(state, action_a, action_b), ...]

    # 查询动作权重（给 MCTS rollout 用）
    weights = db.get_weights(state, "a", actions)

    # 保存
    db.save("毒队")
    """

    def __init__(self):
        # db[team][state_key][action_key] = ActionStats
        self._db: Dict[str, Dict[str, Dict[str, ActionStats]]] = {
            "a": {}, "b": {}
        }
        self.total_games: int = 0

    # ------------------------------------------------------------------
    # 记录一局游戏
    # ------------------------------------------------------------------
    def record_game(
        self,
        history: List[Tuple[Any, tuple, tuple]],
        winner: Optional[str],
    ) -> None:
        """
        记录一局游戏。

        Parameters
        ----------
        history : [(state_before_turn, action_a, action_b), ...]
        winner  : "a" / "b" / None（平局）
        """
        self.total_games += 1
        for battle_state, action_a, action_b in history:
            for team, action in (("a", action_a), ("b", action_b)):
                won = 1.0 if winner == team else (0.5 if winner is None else 0.0)
                sk  = state_key(battle_state, team)
                ak  = _action_key(action, battle_state.get_current(team))
                self._get_or_create(team, sk, ak).wins  += won
                self._get_or_create(team, sk, ak).total += 1

    def _get_or_create(self, team: str, sk: str, ak: str) -> ActionStats:
        team_db = self._db[team]
        if sk not in team_db:
            team_db[sk] = {}
        if ak not in team_db[sk]:
            team_db[sk][ak] = ActionStats()
        return team_db[sk][ak]

    # ------------------------------------------------------------------
    # 查询权重
    # ------------------------------------------------------------------
    def get_weights(self, state, team: str, actions: list) -> List[float]:
        """
        返回各动作的采样权重（基于历史胜率，无数据时权重相等）。
        胜率映射：[0,1] → [0.1, 2.0]，避免权重为 0。
        """
        if not actions:
            return []
        sk       = state_key(state, team)
        current  = state.get_current(team)
        team_db  = self._db[team]

        weights = []
        for action in actions:
            ak = _action_key(action, current)
            stats = team_db.get(sk, {}).get(ak)
            if stats and stats.total > 0:
                weights.append(0.1 + 1.9 * stats.win_rate())
            else:
                weights.append(1.0)
        return weights

    # ------------------------------------------------------------------
    # 调试摘要
    # ------------------------------------------------------------------
    def summary(self, team: str = "a", top_n: int = 8) -> str:
        team_db = self._db[team]
        lines = [f"ExperienceDB — {team} 队  共 {self.total_games} 局"]
        ranked = sorted(
            team_db.items(),
            key=lambda kv: sum(s.total for s in kv[1].values()),
            reverse=True,
        )
        for sk, actions in ranked[:top_n]:
            total_in_state = sum(s.total for s in actions.values())
            lines.append(f"  [{total_in_state:4}] {sk}")
            for ak, stats in sorted(actions.items(), key=lambda x: -x[1].total)[:5]:
                lines.append(
                    f"       {ak:<18} {stats.wins:.0f}/{stats.total}"
                    f"  ({stats.win_rate()*100:.0f}%)"
                )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def save(self, name: str = "default", directory: str = None) -> str:
        save_dir = directory or _DEFAULT_DIR
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, f"{name}.json")

        serialized: dict = {"total_games": self.total_games, "db": {}}
        for team, state_dict in self._db.items():
            serialized["db"][team] = {
                sk: {ak: stats.to_dict() for ak, stats in actions.items()}
                for sk, actions in state_dict.items()
            }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(serialized, f, ensure_ascii=False, separators=(",", ":"))
        return filepath

    def load(self, name: str = "default", directory: str = None) -> bool:
        load_dir = directory or _DEFAULT_DIR
        filepath = os.path.join(load_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return False

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.total_games = data.get("total_games", 0)
        self._db = {"a": {}, "b": {}}
        for team, state_dict in data.get("db", {}).items():
            if team not in self._db:
                continue
            for sk, actions in state_dict.items():
                self._db[team][sk] = {
                    ak: ActionStats.from_dict(sd) for ak, sd in actions.items()
                }
        return True

    @classmethod
    def load_or_create(cls, name: str = "default", directory: str = None) -> "ExperienceDB":
        db = cls()
        db.load(name, directory)
        return db
