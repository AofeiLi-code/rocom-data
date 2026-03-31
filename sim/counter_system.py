"""
NRC_SIM 应对系统 — 洛克王国核心特色

双方同时选择技能后，根据技能类别的组合产生额外效果：
- 攻击 vs 防御 → 减伤 + 反弹 + 应对攻击效果
- 攻击 vs 状态 → 应对状态效果（威力倍率、扣能、加毒）
- 防御 vs 状态 → 防御方应对效果
- 其他组合     → 无额外效果
"""

from dataclasses import dataclass, field
from typing import List, Tuple

from sim.types import SkillCategory
from sim.skill import Skill
from sim.pokemon import Pokemon


# ============================================================
# 应对结果
# ============================================================
@dataclass
class CounterResult:
    """应对解析的结构化结果"""
    final_damage: int = 0           # 经过减伤后的最终伤害
    reflect_damage: int = 0         # 反弹给攻击方的伤害
    power_mult: float = 1.0         # 威力倍率（应对状态/防御时放大技能威力）


# ============================================================
# 应对解析
# ============================================================
def resolve_counter(
    attacker: Pokemon,
    defender: Pokemon,
    atk_skill: Skill,
    def_skill: Skill,
    base_damage: int,
) -> CounterResult:
    """
    解析双方技能的应对交互。

    Parameters
    ----------
    attacker  : 本回合的攻击方（正在执行技能的一方）
    defender  : 对方（对方选择的技能作为"被应对"的依据）
    atk_skill : 攻击方使用的技能
    def_skill : 防御方（对方）选择的技能
    base_damage : 攻击方技能的基础伤害（应对前）

    Returns
    -------
    CounterResult
    """
    result = CounterResult(final_damage=base_damage)

    # ---- 攻击 vs 防御 ----
    if atk_skill.is_attack and def_skill.is_defense:
        _resolve_attack_vs_defense(attacker, defender, atk_skill, def_skill, result)

    # ---- 攻击 vs 状态 ----
    elif atk_skill.is_attack and def_skill.is_status:
        _resolve_attack_vs_status(attacker, defender, atk_skill, def_skill, result)

    # ---- 防御 vs 状态 ----
    elif atk_skill.is_defense and def_skill.is_status:
        _resolve_defense_vs_status(attacker, defender, atk_skill, def_skill, result)

    # ---- 防御 vs 攻击 (从防御方视角，这里 attacker 实际是防御技能使用者) ----
    # 这个情况在 battle_engine 中由攻击方触发，这里不需要额外处理

    return result


# ------------------------------------------------------------------
# 攻击 vs 防御：减伤 + 反弹 + 应对攻击效果
# ------------------------------------------------------------------
def _resolve_attack_vs_defense(
    attacker: Pokemon,
    defender: Pokemon,
    atk_skill: Skill,
    def_skill: Skill,
    result: CounterResult,
) -> None:
    """攻击方攻击 → 防御方使用防御技能"""

    # 1. 减伤
    if def_skill.damage_reduction > 0:
        result.final_damage = int(result.final_damage * (1.0 - def_skill.damage_reduction))

    # 2. 应对攻击 — 防御方的额外效果
    if def_skill.counter_physical_drain > 0:
        heal = int(result.final_damage * def_skill.counter_physical_drain)
        defender.heal(heal)

    if def_skill.counter_physical_energy_drain > 0:
        attacker.lose_energy(def_skill.counter_physical_energy_drain)

    if def_skill.counter_physical_self_atk > 0:
        defender.atk_boost += def_skill.counter_physical_self_atk

    if def_skill.counter_physical_enemy_def > 0:
        attacker.def_reduce += def_skill.counter_physical_enemy_def

    if def_skill.counter_physical_enemy_atk > 0:
        attacker.atk_reduce += def_skill.counter_physical_enemy_atk

    # 3. 反弹伤害
    if def_skill.counter_damage_reflect > 0:
        result.reflect_damage = int(result.final_damage * def_skill.counter_damage_reflect)


# ------------------------------------------------------------------
# 攻击 vs 状态：攻击方的应对状态效果
# ------------------------------------------------------------------
def _resolve_attack_vs_status(
    attacker: Pokemon,
    defender: Pokemon,
    atk_skill: Skill,
    def_skill: Skill,
    result: CounterResult,
) -> None:
    """攻击方攻击 → 对方使用状态技能"""

    # 应对状态 — 威力倍率
    if atk_skill.counter_status_power_mult > 1:
        result.power_mult = atk_skill.counter_status_power_mult

    # 应对状态 — 扣对方能量
    if atk_skill.counter_status_enemy_lose_energy > 0:
        defender.lose_energy(atk_skill.counter_status_enemy_lose_energy)

    # 应对状态 — 攻击方攻击+
    if atk_skill.counter_physical_self_atk > 0:
        attacker.atk_boost += atk_skill.counter_physical_self_atk

    # 应对状态 — 给对方上毒
    if atk_skill.counter_status_poison_stacks > 0:
        defender.poison_stacks += atk_skill.counter_status_poison_stacks

    # 应对状态 — 给对方灼烧
    if atk_skill.counter_status_burn_stacks > 0:
        defender.burn_stacks += atk_skill.counter_status_burn_stacks

    # 应对状态 — 给对方冻结
    if atk_skill.counter_status_freeze_stacks > 0:
        defender.freeze_stacks += atk_skill.counter_status_freeze_stacks


# ------------------------------------------------------------------
# 防御 vs 状态：防御方的应对效果
# ------------------------------------------------------------------
def _resolve_defense_vs_status(
    attacker: Pokemon,
    defender: Pokemon,
    atk_skill: Skill,
    def_skill: Skill,
    result: CounterResult,
) -> None:
    """防御方使用防御技能 → 对方使用状态技能"""

    # 这里 attacker 实际是防御技能使用者（此时执行防御动作）
    # defender 是状态技能使用者

    if atk_skill.counter_defense_self_atk > 0:
        attacker.atk_boost += atk_skill.counter_defense_self_atk

    if atk_skill.counter_defense_self_def > 0:
        attacker.def_boost += atk_skill.counter_defense_self_def

    if atk_skill.counter_defense_enemy_def > 0:
        defender.def_reduce += atk_skill.counter_defense_enemy_def

    if atk_skill.counter_defense_enemy_atk > 0:
        defender.atk_reduce += atk_skill.counter_defense_enemy_atk

    if atk_skill.counter_defense_enemy_energy_cost > 0:
        # 增加对方全技能能耗（这个效果在能量检查时生效）
        # 暂时直接扣能量作为简化处理
        defender.lose_energy(atk_skill.counter_defense_enemy_energy_cost)
