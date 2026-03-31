"""
蒙特卡洛树搜索 (MCTS) — UCB1 + ExperienceDB 加权 rollout

对局特性：双方同时选择动作（非交替决策）。
处理方式：树只展开"己方"的动作；对手动作在每次展开/模拟时
由 ExperienceDB 加权采样（无数据则均匀随机），相当于把对手
当作随机环境处理。

四步循环
--------
Selection    — 沿 UCB1 最优路径向下，直至未完全展开节点
Expansion    — 取一个未尝试动作，执行 (己方, 对手) 联合回合，生成子节点
Simulation   — 从子节点随机 rollout 至终局
Backpropagation — 沿路径反向更新 visits / wins
"""

import math
import random
import time
from typing import List, Optional, Tuple

from sim.battle_state import BattleState
from sim.battle_engine import BattleEngine, Action
from sim.strategy import get_strategy_weights


def _combine_weights(state, team, actions, experience_db, strategy) -> List[float]:
    """策略权重 × 经验权重，两者都没有则均等。"""
    n = len(actions)
    if not actions:
        return []

    strat_w = get_strategy_weights(state, team, actions, strategy)
    exp_w   = (experience_db.get_weights(state, team, actions)
               if experience_db else [1.0] * n)

    combined = [s * e for s, e in zip(strat_w, exp_w)]
    # 保证至少有一个正权重
    if max(combined) <= 0:
        return [1.0] * n
    return combined

# UCB1 探索常数（√2 为理论最优，可调整）
C_UCB1 = math.sqrt(2)

# rollout 最大回合数（超过即视为平局）
MAX_ROLLOUT_TURNS = 60


# ============================================================
# MCTS 节点
# ============================================================

class MCTSNode:
    """
    MCTS 树节点。

    Attributes
    ----------
    state        : 到达本节点时的战斗状态（深拷贝）
    team         : 本搜索树代表哪方（"a"/"b"）
    action       : 己方采取的动作（到达本节点），根节点为 None
    parent       : 父节点
    children     : 已展开的子节点列表
    visits       : 本节点被访问次数
    wins         : 本节点累计胜利值（己方胜 +1，平局 +0.5）
    untried      : 尚未展开的己方合法动作（懒初始化）
    """

    __slots__ = ("state", "team", "action", "parent", "children",
                 "visits", "wins", "untried")

    def __init__(
        self,
        state: BattleState,
        team: str,
        action: Optional[Action] = None,
        parent: Optional["MCTSNode"] = None,
    ):
        self.state   = state
        self.team    = team
        self.action  = action
        self.parent  = parent
        self.children: List["MCTSNode"] = []
        self.visits:   int   = 0
        self.wins:     float = 0.0
        self.untried:  Optional[List[Action]] = None   # 懒初始化

    # ------------------------------------------------------------------

    def init_untried(self, engine: BattleEngine) -> None:
        """初始化未尝试动作列表（仅调用一次）"""
        if self.untried is None:
            self.untried = list(engine.get_actions(self.team))

    @property
    def is_fully_expanded(self) -> bool:
        return self.untried is not None and len(self.untried) == 0

    def ucb1(self, parent_visits: int, c: float = C_UCB1) -> float:
        if self.visits == 0:
            return float("inf")
        return (self.wins / self.visits
                + c * math.sqrt(math.log(parent_visits) / self.visits))

    def best_child_ucb1(self, c: float = C_UCB1) -> "MCTSNode":
        return max(self.children, key=lambda ch: ch.ucb1(self.visits, c))

    def best_action(self) -> Action:
        """返回访问次数最多的子节点对应的动作（决策时用，不含探索）"""
        return max(self.children, key=lambda ch: ch.visits).action


# ============================================================
# 辅助：采样对手动作
# ============================================================

def _sample_opponent(
    state: BattleState,
    engine: BattleEngine,
    opp_team: str,
    experience_db=None,
) -> Action:
    """从合法动作中采样对手动作（ExperienceDB 加权或均匀随机）"""
    actions = engine.get_actions(opp_team)
    if not actions:
        return (-1,)
    if experience_db is not None:
        weights = experience_db.get_weights(state, opp_team, actions)
        return random.choices(actions, weights=weights, k=1)[0]
    return random.choice(actions)


# ============================================================
# MCTS 搜索
# ============================================================

class MCTSSearch:
    """
    MCTS 搜索器（从己方视角构建决策树）。

    Parameters
    ----------
    team         : 己方队伍 "a" 或 "b"
    iterations   : 每次 search() 的 MCTS 迭代次数
    time_limit   : 每次 search() 的最长耗时（秒），None = 仅用 iterations
    experience_db: ExperienceDB 实例，None = 纯随机 rollout
    c            : UCB1 探索常数
    """

    def __init__(
        self,
        team: str,
        iterations: int = 100,
        time_limit: Optional[float] = None,
        experience_db=None,
        strategy=None,
        c: float = C_UCB1,
    ):
        self.team          = team
        self.iterations    = iterations
        self.time_limit    = time_limit
        self.experience_db = experience_db
        self.strategy      = strategy   # 策略配置 dict 或 None
        self.c             = c
        self._opp_team     = "b" if team == "a" else "a"

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def search(self, state: BattleState) -> Action:
        """
        从给定战斗状态出发，搜索己方最优动作并返回。
        若只有一个合法动作，直接返回（不浪费时间搜索）。
        """
        # 快速检查合法动作
        tmp_engine = BattleEngine(state, verbose=False)
        actions = tmp_engine.get_actions(self.team)
        if len(actions) == 1:
            return actions[0]

        # 建立根节点
        root = MCTSNode(state.deep_copy(), self.team)
        root.init_untried(BattleEngine(root.state, verbose=False))

        deadline = time.time() + self.time_limit if self.time_limit else None

        for _ in range(self.iterations):
            if deadline and time.time() > deadline:
                break

            # 1. Selection
            node = self._select(root)

            # 2. Expansion（终局节点不展开）
            if not self._is_terminal(node.state):
                node = self._expand(node)

            # 3. Simulation
            result = self._simulate(node.state)

            # 4. Backpropagation
            self._backpropagate(node, result)

        if not root.children:
            return random.choice(actions)

        return root.best_action()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _is_terminal(self, state: BattleState) -> bool:
        return BattleEngine(state, verbose=False).check_winner() is not None

    def _select(self, node: MCTSNode) -> MCTSNode:
        """沿 UCB1 最优路径向下，直至未完全展开节点或叶节点"""
        while not self._is_terminal(node.state):
            eng = BattleEngine(node.state, verbose=False)
            node.init_untried(eng)

            if not node.is_fully_expanded:
                return node   # 有未尝试动作 → 准备展开

            if not node.children:
                return node   # 叶节点（所有动作展开后无子节点？理论上不会）

            node = node.best_child_ucb1(self.c)

        return node

    # ------------------------------------------------------------------
    # Expansion
    # ------------------------------------------------------------------

    def _expand(self, node: MCTSNode) -> MCTSNode:
        """取一个未尝试己方动作，与对手采样动作一起执行，生成子节点"""
        eng = BattleEngine(node.state, verbose=False)
        node.init_untried(eng)

        if not node.untried:
            return node

        # 选择要展开的己方动作（策略权重 × 经验权重）
        weights = _combine_weights(
            node.state, self.team, node.untried,
            self.experience_db, self.strategy,
        )
        my_action = random.choices(node.untried, weights=weights, k=1)[0]
        node.untried.remove(my_action)

        # 采样对手动作
        opp_action = _sample_opponent(
            node.state, eng, self._opp_team, self.experience_db
        )

        # 执行联合动作，得到新状态
        new_state = node.state.deep_copy()
        new_eng   = BattleEngine(new_state, verbose=False)
        action_a  = my_action  if self.team == "a" else opp_action
        action_b  = opp_action if self.team == "a" else my_action
        new_eng.execute_turn(action_a, action_b)

        child = MCTSNode(new_state, self.team, action=my_action, parent=node)
        node.children.append(child)
        return child

    # ------------------------------------------------------------------
    # Simulation (rollout)
    # ------------------------------------------------------------------

    def _simulate(self, state: BattleState) -> float:
        """
        从当前状态随机/加权模拟到终局。
        返回值：己方胜 1.0 / 负 0.0 / 平局 0.5
        """
        sim_state = state.deep_copy()
        engine    = BattleEngine(sim_state, verbose=False)

        for _ in range(MAX_ROLLOUT_TURNS):
            winner = engine.check_winner()
            if winner is not None:
                return 1.0 if winner == self.team else 0.0

            my_actions  = engine.get_actions(self.team)
            opp_actions = engine.get_actions(self._opp_team)

            # 己方：策略权重 × 经验权重
            w  = _combine_weights(sim_state, self.team, my_actions,
                                  self.experience_db, self.strategy)
            ma = random.choices(my_actions, weights=w, k=1)[0] if my_actions else (-1,)

            # 对手：仅经验权重（对手无策略文件）
            if self.experience_db and opp_actions:
                w  = self.experience_db.get_weights(sim_state, self._opp_team, opp_actions)
                oa = random.choices(opp_actions, weights=w, k=1)[0]
            else:
                oa = random.choice(opp_actions) if opp_actions else (-1,)

            action_a = ma if self.team == "a" else oa
            action_b = oa if self.team == "a" else ma
            engine.execute_turn(action_a, action_b)

        # 超时：按当前生命格差判断
        winner = engine.check_winner()
        if winner == self.team:
            return 1.0
        if winner is not None:
            return 0.0
        # 按生命格差给部分分
        lives_me  = sim_state.lives_a if self.team == "a" else sim_state.lives_b
        lives_opp = sim_state.lives_b if self.team == "a" else sim_state.lives_a
        if lives_me > lives_opp:
            return 0.75
        if lives_me < lives_opp:
            return 0.25
        return 0.5

    # ------------------------------------------------------------------
    # Backpropagation
    # ------------------------------------------------------------------

    def _backpropagate(self, node: MCTSNode, result: float) -> None:
        """沿路径向上更新 visits 和 wins"""
        cur = node
        while cur is not None:
            cur.visits += 1
            cur.wins   += result
            cur = cur.parent
