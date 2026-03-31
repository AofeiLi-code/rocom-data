"""
MCTS Agent — 封装 MCTSSearch + ExperienceDB

提供两种使用方式：
  1. 单步决策：agent.choose_action(engine) → Action
  2. 完整对战：run_mcts_battle(agent_a, agent_b, team_a, team_b)

经验数据库以队伍名为键存储在 data/experience/<name>.json，
每局结束后调用 agent.save() 即可持久化。
"""

import random
import time
from typing import List, Optional, Tuple

from sim.battle_state import BattleState
from sim.battle_engine import BattleEngine, Action
from sim.mcts import MCTSSearch
from sim.experience_db import ExperienceDB


# ============================================================
# MCTS Agent
# ============================================================

class MCTSAgent:
    """
    MCTS 智能体。

    Parameters
    ----------
    team         : "a" 或 "b"
    team_name    : 经验数据库存储键名（建议与队伍名一致）
    iterations   : 每回合 MCTS 迭代次数（越大越强，越慢）
    time_limit   : 每回合最大思考时间（秒）；None = 只看 iterations
    load_exp     : 是否自动从磁盘加载历史经验
    """

    def __init__(
        self,
        team: str,
        team_name: str = "default",
        iterations: int = 100,
        time_limit: Optional[float] = None,
        load_exp: bool = True,
    ):
        self.team      = team
        self.team_name = team_name

        self.experience_db = ExperienceDB.load_or_create(team_name)
        if load_exp and self.experience_db.total_games > 0:
            print(f"  [MCTS] {team_name}（{team}）加载经验："
                  f"{self.experience_db.total_games} 局历史")

        self._search = MCTSSearch(
            team=team,
            iterations=iterations,
            time_limit=time_limit,
            experience_db=self.experience_db,
        )

    # ------------------------------------------------------------------
    # 单步决策
    # ------------------------------------------------------------------

    def choose_action(self, engine: BattleEngine) -> Action:
        """根据当前引擎状态，用 MCTS 选择最优动作。"""
        return self._search.search(engine.state)

    # ------------------------------------------------------------------
    # 保存经验
    # ------------------------------------------------------------------

    def save(self) -> str:
        path = self.experience_db.save(self.team_name)
        return path

    def print_summary(self) -> None:
        print(self.experience_db.summary(self.team))


# ============================================================
# 完整对战（双 MCTS）
# ============================================================

def run_mcts_battle(
    agent_a: MCTSAgent,
    agent_b: MCTSAgent,
    team_a_pokemon: list,
    team_b_pokemon: list,
    verbose: bool = False,
    record: bool = True,
) -> Optional[str]:
    """
    运行一局双 MCTS 对战，自动记录经验。

    Parameters
    ----------
    agent_a / agent_b : MCTSAgent 实例
    team_a_pokemon    : build_team() 返回的 Pokemon 列表（A 队）
    team_b_pokemon    : 同上（B 队）
    verbose           : 是否打印对战日志
    record            : 是否将对战历史写入 ExperienceDB

    Returns
    -------
    "a" / "b" / None（平局/超时）
    """
    state  = BattleState(team_a=team_a_pokemon, team_b=team_b_pokemon)
    engine = BattleEngine(state, verbose=verbose)

    history: List[Tuple[BattleState, Action, Action]] = []
    winner = None

    for _ in range(BattleEngine.MAX_TURNS):
        winner = engine.check_winner()
        if winner:
            break

        # 双方各自决策（互不知晓对方选择）
        t0       = time.time()
        action_a = agent_a._search.search(state)
        action_b = agent_b._search.search(state)
        elapsed  = time.time() - t0

        if verbose:
            pa = state.get_current("a")
            pb = state.get_current("b")
            print(f"  [回合{state.turn}] {pa.name}→{_action_name(action_a, pa)}"
                  f"  vs  {pb.name}→{_action_name(action_b, pb)}"
                  f"  ({elapsed*1000:.0f}ms)")

        if record:
            history.append((state.deep_copy(), action_a, action_b))

        engine.execute_turn(action_a, action_b)

    if not winner:
        winner = engine.check_winner()

    if verbose:
        tag = (f"A队({agent_a.team_name})赢" if winner == "a"
               else (f"B队({agent_b.team_name})赢" if winner == "b" else "平局"))
        print(f"\n  结果：{tag}  共{state.turn}回合")

    # 记录经验
    if record and history:
        agent_a.experience_db.record_game(history, winner)
        agent_b.experience_db.record_game(history, winner)

    return winner


# ============================================================
# 工具
# ============================================================

def _action_name(action: Action, pokemon) -> str:
    """动作的可读名称"""
    if action[0] == -1:
        return "聚能"
    if action[0] == -2:
        return f"换宠[{action[1]}]"
    idx = action[0]
    if 0 <= idx < len(pokemon.skills):
        return pokemon.skills[idx].name
    return f"技能{idx}"
