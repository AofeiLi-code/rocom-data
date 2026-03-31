"""
队伍策略系统 (Strategy)

从 data/strategies/<team_name>.yaml 加载人类编写的策略提示，
转换为 MCTS 动作权重的乘数。

权重计算（最终权重 = 策略权重 × ExperienceDB权重）：
  - 策略推荐的动作：权重 × 3.0（强烈偏好）
  - 策略允许的动作：权重 × 1.0（中性）
  - 策略排斥的动作：权重 × 0.2（降低但不禁止）

YAML 文件格式见 data/strategies/_template.yaml
"""

import os
import yaml
from typing import Dict, List, Optional, Tuple, Any

from sim.battle_state import BattleState
from sim.battle_engine import Action
from sim.types import get_type_effectiveness, SkillCategory

_STRATEGY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "strategies",
)

# 权重系数
W_PREFER  = 3.0   # 策略明确推荐
W_NEUTRAL = 1.0   # 无明确指示
W_AVOID   = 0.2   # 策略明确排斥


# ============================================================
# YAML 加载
# ============================================================

def load_strategy(team_name: str) -> Optional[Dict]:
    """
    加载队伍策略文件，返回解析后的 dict。
    找不到文件时返回 None（无策略，权重全1）。
    """
    path = os.path.join(_STRATEGY_DIR, f"{team_name}.yaml")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================
# 条件评估
# ============================================================

def _hp_pct(pokemon) -> float:
    if pokemon.hp <= 0:
        return 0.0
    return pokemon.current_hp / pokemon.hp * 100.0


def _is_type_disadvantaged(me, opponent) -> bool:
    """对手场上精灵对我方有属性克制（承受 ≥2x 的伤害）"""
    # 检查对手所有技能中，有没有克制我方的
    for skill in opponent.skills:
        eff = get_type_effectiveness(skill.skill_type, me.pokemon_type)
        if me.secondary_type:
            from sim.damage_calc import _dual_type_effectiveness
            eff = _dual_type_effectiveness(skill.skill_type, me.pokemon_type, me.secondary_type)
        if eff >= 2.0:
            return True
    return False


def _is_type_advantaged(me, opponent) -> bool:
    """我方对对手有属性克制（我方技能中有克制对手的）"""
    for skill in me.skills:
        eff = get_type_effectiveness(skill.skill_type, opponent.pokemon_type)
        if eff >= 2.0:
            return True
    return False


def _find_best_counter(team_list, current_idx, opponent) -> Optional[int]:
    """从存活队友中找到能克制对手的最佳换宠目标索引"""
    best_idx   = None
    best_score = -1
    for i, p in enumerate(team_list):
        if i == current_idx or p.is_fainted:
            continue
        score = 0
        # 属性克制对手
        for skill in p.skills:
            eff = get_type_effectiveness(skill.skill_type, opponent.pokemon_type)
            if eff >= 2.0:
                score += 2
            elif eff > 1.0:
                score += 1
        # 对手克制我方（扣分）
        for skill in opponent.skills:
            eff = get_type_effectiveness(skill.skill_type, p.pokemon_type)
            if eff >= 2.0:
                score -= 2
        # HP 越高越好
        score += _hp_pct(p) / 50.0
        if score > best_score:
            best_score = score
            best_idx   = i
    return best_idx


def _find_highest_hp(team_list, current_idx) -> Optional[int]:
    """找存活队友中 HP 最高的"""
    best_idx = None
    best_hp  = -1
    for i, p in enumerate(team_list):
        if i == current_idx or p.is_fainted:
            continue
        if p.current_hp > best_hp:
            best_hp  = p.current_hp
            best_idx = i
    return best_idx


def _eval_condition(cond: str, state: BattleState, team: str) -> bool:
    """
    评估条件字符串，返回 True/False。

    支持的条件：
      hp_pct < N          己方当前精灵HP百分比低于N
      hp_pct > N          己方当前精灵HP百分比高于N
      energy < N          己方能量低于N
      energy > N          己方能量高于N
      type_disadvantaged  己方属性被克制
      type_advantaged     己方有属性克制对手
      enemy_hp_pct < N    对手HP低于N%
      always              无条件触发
    """
    me  = state.get_current(team)
    opp = state.get_current("b" if team == "a" else "a")
    cond = cond.strip()

    if cond == "always":
        return True
    if cond == "type_disadvantaged":
        return _is_type_disadvantaged(me, opp)
    if cond == "type_advantaged":
        return _is_type_advantaged(me, opp)

    # 比较型条件：  "hp_pct < 30"
    for keyword, getter in [
        ("hp_pct",       lambda: _hp_pct(me)),
        ("energy",       lambda: float(me.energy)),
        ("enemy_hp_pct", lambda: _hp_pct(opp)),
    ]:
        if cond.startswith(keyword):
            rest = cond[len(keyword):].strip()
            try:
                op, val = rest.split()
                val = float(val)
                cur = getter()
                if op == "<":  return cur < val
                if op == ">":  return cur > val
                if op == "<=": return cur <= val
                if op == ">=": return cur >= val
                if op == "==": return cur == val
            except Exception:
                pass

    return False


# ============================================================
# 动作权重计算
# ============================================================

def get_strategy_weights(
    state: BattleState,
    team: str,
    actions: List[Action],
    strategy: Optional[Dict],
) -> List[float]:
    """
    根据策略配置返回各动作的权重乘数。
    无策略时全部返回 1.0。
    """
    if not strategy or not actions:
        return [W_NEUTRAL] * len(actions)

    me      = state.get_current(team)
    opp     = state.get_current("b" if team == "a" else "a")
    team_list = state.get_team(team)
    cur_idx = state.get_current_idx(team)

    weights = [W_NEUTRAL] * len(actions)

    # ---- 1. 技能优先级（skill_priority）----
    skill_priority: Dict[str, List[str]] = strategy.get("skill_priority", {})
    priority_list: List[str] = skill_priority.get(me.name, [])

    for i, action in enumerate(actions):
        if action[0] >= 0:   # 是技能动作
            skill = me.skills[action[0]]
            if skill.name in priority_list:
                rank = priority_list.index(skill.name)
                # 排名越靠前权重越高：1st→3.0, 2nd→2.0, 3rd→1.5, 4th→1.2
                rank_weights = [3.0, 2.0, 1.5, 1.2]
                weights[i] = rank_weights[min(rank, len(rank_weights) - 1)]

    # ---- 2. 换宠规则（switch_rules）----
    switch_rules: List[Dict] = strategy.get("switch_rules", [])
    for rule in switch_rules:
        when   = rule.get("when", "")
        action = rule.get("action", "switch")
        to     = rule.get("to", "highest_hp")

        if not _eval_condition(when, state, team):
            continue

        if action == "gather":
            # 触发聚能规则
            for i, act in enumerate(actions):
                if act[0] == -1:
                    weights[i] = max(weights[i], W_PREFER)
            break

        if action == "switch":
            # 找目标换宠索引
            target_idx = None
            if to == "highest_hp":
                target_idx = _find_highest_hp(team_list, cur_idx)
            elif to == "type_counter":
                target_idx = _find_best_counter(team_list, cur_idx, opp)
                if target_idx is None:
                    target_idx = _find_highest_hp(team_list, cur_idx)
            elif isinstance(to, str):
                # 具体精灵名
                for j, p in enumerate(team_list):
                    if p.name == to and not p.is_fainted and j != cur_idx:
                        target_idx = j
                        break

            if target_idx is not None:
                for i, act in enumerate(actions):
                    if act[0] == -2 and act[1] == target_idx:
                        weights[i] = max(weights[i], W_PREFER)
                    elif act[0] == -2:
                        # 其他换宠降权（已触发了规则，倾向目标）
                        weights[i] = min(weights[i], W_AVOID)
            break   # 只用第一个匹配的换宠规则

    # ---- 3. 通用规则（general）----
    general: Dict = strategy.get("general", {})

    # 能量低于阈值时偏好聚能
    gather_below = general.get("prefer_gather_below_energy", 0)
    if gather_below and me.energy < gather_below:
        for i, act in enumerate(actions):
            if act[0] == -1:
                weights[i] = max(weights[i], W_PREFER)

    # 属性克制时偏好攻击
    if general.get("prefer_attack_when_type_advantage") and _is_type_advantaged(me, opp):
        for i, act in enumerate(actions):
            if act[0] >= 0:
                skill = me.skills[act[0]]
                eff = get_type_effectiveness(skill.skill_type, opp.pokemon_type)
                if eff >= 2.0:
                    weights[i] = max(weights[i], W_PREFER)

    # HP较高时避免换宠
    avoid_switch_above = general.get("avoid_switch_when_hp_above", 0)
    if avoid_switch_above and _hp_pct(me) > avoid_switch_above:
        for i, act in enumerate(actions):
            if act[0] == -2:
                weights[i] = min(weights[i], W_AVOID)

    return weights


# ============================================================
# 获取首发精灵索引
# ============================================================

def get_starter_idx(strategy: Optional[Dict], team_list) -> Optional[int]:
    """
    返回策略指定的首发精灵在队伍中的索引。
    找不到或无策略时返回 None（使用默认的第0位）。
    """
    if not strategy:
        return None
    starter_name = strategy.get("starter")
    if not starter_name:
        return None
    for i, p in enumerate(team_list):
        if p.name == starter_name:
            return i
    return None
