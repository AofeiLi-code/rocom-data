"""
NRC_SIM 技能数据模型
"""

from dataclasses import dataclass
from sim.types import Type, SkillCategory


@dataclass
class Skill:
    """技能 — 完整数据模型"""

    # === 基础属性 ===
    name: str
    skill_type: Type
    category: SkillCategory
    power: int
    energy_cost: int
    hit_count: int = 1

    # === 效果标记 ===
    life_drain: float = 0           # 吸血比例 (0.5 = 50% 伤害转化为回复)
    damage_reduction: float = 0     # 减伤比例 (0.7 = 减 70%)
    self_heal_hp: float = 0         # 回复HP比例 (基于最大HP)
    self_heal_energy: int = 0       # 回复能量
    steal_energy: int = 0           # 偷取敌方能量 (自己+X, 敌方-X)
    enemy_lose_energy: int = 0      # 敌方失去能量
    enemy_energy_cost_up: int = 0   # 敌方全技能能耗 +X
    priority_mod: int = 0           # 先手修正值
    force_switch: bool = False      # 脱离
    agility: bool = False           # 迅捷
    charge: bool = False            # 蓄力

    # === 自身属性修正 (加法叠加，1.0 = +100%) ===
    self_atk: float = 0
    self_def: float = 0
    self_spatk: float = 0
    self_spdef: float = 0
    self_speed: float = 0
    self_all_atk: float = 0         # 双攻
    self_all_def: float = 0         # 双防

    # === 敌方属性修正 ===
    enemy_atk: float = 0
    enemy_def: float = 0
    enemy_spatk: float = 0
    enemy_spdef: float = 0
    enemy_speed: float = 0
    enemy_all_atk: float = 0
    enemy_all_def: float = 0

    # === 状态层数附加 ===
    poison_stacks: int = 0
    burn_stacks: int = 0
    freeze_stacks: int = 0

    # === 应对效果 — 应对攻击 ===
    counter_physical_drain: float = 0       # 应对攻击时吸血
    counter_physical_energy_drain: int = 0  # 应对攻击时扣敌方能量
    counter_physical_self_atk: float = 0    # 应对攻击时自身攻击+
    counter_physical_enemy_def: float = 0   # 应对攻击时敌方防御-
    counter_physical_enemy_atk: float = 0   # 应对攻击时敌方攻击-
    counter_physical_power_mult: float = 0  # 应对攻击时威力倍率

    # === 应对效果 — 应对防御 ===
    counter_defense_self_atk: float = 0
    counter_defense_self_def: float = 0
    counter_defense_enemy_def: float = 0
    counter_defense_enemy_atk: float = 0
    counter_defense_enemy_energy_cost: int = 0
    counter_defense_power_mult: float = 0

    # === 应对效果 — 应对状态 ===
    counter_status_power_mult: float = 0
    counter_status_enemy_lose_energy: int = 0
    counter_status_poison_stacks: int = 0
    counter_status_burn_stacks: int = 0
    counter_status_freeze_stacks: int = 0

    # === 其他应对 ===
    counter_skill_cooldown: int = 0         # 被应对技能进入冷却
    counter_damage_reflect: float = 0       # 反弹伤害比例

    def copy(self) -> "Skill":
        """返回完整副本"""
        return Skill(
            name=self.name, skill_type=self.skill_type, category=self.category,
            power=self.power, energy_cost=self.energy_cost, hit_count=self.hit_count,
            life_drain=self.life_drain, damage_reduction=self.damage_reduction,
            self_heal_hp=self.self_heal_hp, self_heal_energy=self.self_heal_energy,
            steal_energy=self.steal_energy, enemy_lose_energy=self.enemy_lose_energy,
            enemy_energy_cost_up=self.enemy_energy_cost_up,
            priority_mod=self.priority_mod,
            force_switch=self.force_switch, agility=self.agility, charge=self.charge,
            self_atk=self.self_atk, self_def=self.self_def,
            self_spatk=self.self_spatk, self_spdef=self.self_spdef,
            self_speed=self.self_speed,
            self_all_atk=self.self_all_atk, self_all_def=self.self_all_def,
            enemy_atk=self.enemy_atk, enemy_def=self.enemy_def,
            enemy_spatk=self.enemy_spatk, enemy_spdef=self.enemy_spdef,
            enemy_speed=self.enemy_speed,
            enemy_all_atk=self.enemy_all_atk, enemy_all_def=self.enemy_all_def,
            poison_stacks=self.poison_stacks, burn_stacks=self.burn_stacks,
            freeze_stacks=self.freeze_stacks,
            counter_physical_drain=self.counter_physical_drain,
            counter_physical_energy_drain=self.counter_physical_energy_drain,
            counter_physical_self_atk=self.counter_physical_self_atk,
            counter_physical_enemy_def=self.counter_physical_enemy_def,
            counter_physical_enemy_atk=self.counter_physical_enemy_atk,
            counter_physical_power_mult=self.counter_physical_power_mult,
            counter_defense_self_atk=self.counter_defense_self_atk,
            counter_defense_self_def=self.counter_defense_self_def,
            counter_defense_enemy_def=self.counter_defense_enemy_def,
            counter_defense_enemy_atk=self.counter_defense_enemy_atk,
            counter_defense_enemy_energy_cost=self.counter_defense_enemy_energy_cost,
            counter_defense_power_mult=self.counter_defense_power_mult,
            counter_status_power_mult=self.counter_status_power_mult,
            counter_status_enemy_lose_energy=self.counter_status_enemy_lose_energy,
            counter_status_poison_stacks=self.counter_status_poison_stacks,
            counter_status_burn_stacks=self.counter_status_burn_stacks,
            counter_status_freeze_stacks=self.counter_status_freeze_stacks,
            counter_skill_cooldown=self.counter_skill_cooldown,
            counter_damage_reflect=self.counter_damage_reflect,
        )

    @property
    def is_attack(self) -> bool:
        return self.category in (SkillCategory.PHYSICAL, SkillCategory.MAGICAL)

    @property
    def is_defense(self) -> bool:
        return self.category == SkillCategory.DEFENSE

    @property
    def is_status(self) -> bool:
        return self.category == SkillCategory.STATUS
