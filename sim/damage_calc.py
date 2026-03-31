"""
NRC_SIM 伤害计算器 — 纯函数，不修改任何状态

洛克王国伤害公式:
  单次伤害 = (攻击裸值 / 防御裸值) × 0.9
             × (技能威力 × 应对倍率 + 威力加成)
             × 能力等级
             × 本系加成
             × 克制关系
             × 天气影响
             × 减伤系数
  最终伤害 = 单次伤害 × 连击次数

  能力等级 = (1 + 我方攻击提升 + 敌方防御降低)
           / (1 + 我方攻击降低 + 敌方防御提升)

  减伤系数 = (1 - 减伤1) × (1 - 减伤2) × ... （多个减伤乘算）

物攻/魔攻判定：根据技能自身的 category (物攻/魔攻)，不是按属性系别。
"""

from typing import List, Optional

from sim.types import Type, SkillCategory, Weather, get_type_effectiveness
from sim.skill import Skill
from sim.pokemon import Pokemon


def calculate_damage(
    attacker: Pokemon,
    defender: Pokemon,
    skill: Skill,
    counter_power_mult: float = 1.0,
    damage_reductions: Optional[List[float]] = None,
    weather: Optional[Weather] = None,
) -> int:
    """
    计算技能伤害（纯函数，不修改任何状态）。

    Parameters
    ----------
    attacker          : 攻击方精灵
    defender          : 防御方精灵
    skill             : 使用的技能
    counter_power_mult: 应对倍率（应对成功时由 counter_system 提供，默认 1.0）
    damage_reductions : 减伤列表（每个值 0~1，如 [0.7, 0.3]，乘算）
    weather           : 当前天气

    Returns
    -------
    最终伤害值（>= 1，若有效威力 <= 0 则返回 0）
    """
    # ------ 1. 攻防裸值 ------
    # 根据技能的 category 判定物攻/魔攻
    if skill.category == SkillCategory.PHYSICAL:
        atk_base = attacker.attack
        def_base = defender.defense
    else:
        # MAGICAL (以及其他攻击类技能)
        atk_base = attacker.sp_attack
        def_base = defender.sp_defense

    if def_base < 1:
        def_base = 1

    # ------ 2. 有效威力 = 技能威力 × 应对倍率 + 威力加成 ------
    effective_power = skill.power * counter_power_mult + attacker.power_bonus
    if effective_power <= 0:
        return 0

    # ------ 3. 基础值 ------
    base = (atk_base / def_base) * 0.9 * effective_power

    # ------ 4. 能力等级 ------
    my_atk_boost = attacker.get_atk_boost(skill)
    my_atk_reduce = attacker.get_atk_reduce(skill)
    enemy_def_boost = defender.get_def_boost(skill)
    enemy_def_reduce = defender.get_def_reduce(skill)

    numerator = 1.0 + my_atk_boost + enemy_def_reduce
    denominator = 1.0 + my_atk_reduce + enemy_def_boost

    if denominator < 0.1:
        denominator = 0.1  # 防止除零

    ability_level = numerator / denominator

    # ------ 5. 本系加成 (STAB) ------
    # 技能属性与攻击方主属性或副属性任一相同时触发
    stab = 1.5 if skill.skill_type in (attacker.pokemon_type, attacker.secondary_type) else 1.0

    # ------ 6. 属性克制 ------
    # 双属性精灵：对主属性和副属性分别查表，两个倍率相乘
    effectiveness = get_type_effectiveness(skill.skill_type, defender.pokemon_type)
    if defender.secondary_type is not None:
        effectiveness *= get_type_effectiveness(skill.skill_type, defender.secondary_type)

    # ------ 7. 天气影响 ------
    weather_mult = 1.0
    if weather == Weather.RAIN and skill.skill_type == Type.WATER:
        weather_mult = 1.5

    # ------ 8. 减伤系数 (多个减伤乘算) ------
    reduction_mult = 1.0
    if damage_reductions:
        for r in damage_reductions:
            reduction_mult *= (1.0 - r)

    # ------ 9. 汇总 ------
    single_hit = base * ability_level * stab * effectiveness * weather_mult * reduction_mult

    # ------ 10. 连击 ------
    total = single_hit * skill.hit_count

    return max(1, int(total))
