"""
NRC_SIM 精灵数据模型

异常状态系统（均不随换人消失，只能技能清除）:
  烧伤: 每回合 -2% × 层数 HP，然后层数减半（向下取整），到 0 消失
  中毒: 每回合 -3% × 层数 HP，层数不衰减
  寄生: 每回合被寄生者 -8% HP，若寄生者在场则回复等量 HP
  冻结: 冻结条 = maxHP × 层数/12，回合结束时 currentHP < 冻结条 则立即死亡

属性修正采用「提升/降低」双向记录:
  能力等级 = (1 + 我方攻击提升 + 敌方防御降低) / (1 + 我方攻击降低 + 敌方防御提升)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, TYPE_CHECKING

from sim.types import Type, StatusType, SkillCategory
from sim.skill import Skill

if TYPE_CHECKING:
    pass  # 避免循环导入

ENERGY_MAX = 10
ENERGY_INIT = 10


@dataclass
class Pokemon:
    """精灵 — 包含基础属性和运行时状态"""

    # === 基础属性（创建后不变） ===
    name: str
    pokemon_type: Type
    hp: int
    attack: int
    defense: int
    sp_attack: int
    sp_defense: int
    speed: int
    secondary_type: Optional[Type] = None  # 副属性（双属性精灵，None 表示单属性）
    ability: str = ""
    skills: List[Skill] = field(default_factory=list)

    # === 运行时状态 ===
    current_hp: int = 0
    energy: int = ENERGY_INIT
    status: StatusType = StatusType.NORMAL

    # --- 属性修正：提升（正值，自身 buff 累加） ---
    atk_boost: float = 0.0
    def_boost: float = 0.0
    spatk_boost: float = 0.0
    spdef_boost: float = 0.0
    speed_boost: float = 0.0

    # --- 属性修正：降低（正值，被对方 debuff 累加） ---
    atk_reduce: float = 0.0
    def_reduce: float = 0.0
    spatk_reduce: float = 0.0
    spdef_reduce: float = 0.0
    speed_reduce: float = 0.0

    # --- 异常状态层数 ---
    burn_stacks: int = 0       # 烧伤层数（每回合 -2%×层数，层数减半）
    poison_stacks: int = 0     # 中毒层数（每回合 -3%×层数，不衰减）
    freeze_stacks: int = 0     # 冻结层数（冻结条 = maxHP × 层数/12）

    # --- 寄生状态 ---
    # parasited_by: 寄生者的名字（用于在战斗引擎中找到寄生者实体）
    # 为 None 表示未被寄生
    parasited_by: Optional[str] = None

    # 威力加成（技能描述里的 "获得技能威力+X" 累积值）
    power_bonus: int = 0

    # 技能冷却 (技能索引 -> 剩余回合数)
    cooldowns: Dict[int, int] = field(default_factory=dict)

    def __post_init__(self):
        if self.current_hp == 0:
            self.current_hp = self.hp

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    @property
    def is_fainted(self) -> bool:
        return self.current_hp <= 0 or self.status == StatusType.FAINTED

    @property
    def can_attack(self) -> bool:
        if self.is_fainted:
            return False
        if self.status in (StatusType.SLEEP, StatusType.FROZEN):
            return False
        return True

    @property
    def freeze_threshold(self) -> int:
        """冻结条：currentHP 低于此值则回合结束时死亡"""
        if self.freeze_stacks <= 0:
            return 0
        return int(self.hp * self.freeze_stacks / 12)

    @property
    def is_poisoned(self) -> bool:
        return self.poison_stacks > 0

    @property
    def is_burned(self) -> bool:
        return self.burn_stacks > 0

    @property
    def is_frozen(self) -> bool:
        return self.freeze_stacks > 0

    @property
    def is_parasited(self) -> bool:
        return self.parasited_by is not None

    # ------------------------------------------------------------------
    # 有效速度
    # ------------------------------------------------------------------
    def effective_speed(self) -> float:
        return self.speed * max(0.1, 1.0 + self.speed_boost - self.speed_reduce)

    # ------------------------------------------------------------------
    # 攻防 boost / reduce 查询
    # ------------------------------------------------------------------
    def get_atk_boost(self, skill: Skill) -> float:
        if skill.category == SkillCategory.PHYSICAL:
            return self.atk_boost
        return self.spatk_boost

    def get_atk_reduce(self, skill: Skill) -> float:
        if skill.category == SkillCategory.PHYSICAL:
            return self.atk_reduce
        return self.spatk_reduce

    def get_def_boost(self, skill: Skill) -> float:
        if skill.category == SkillCategory.PHYSICAL:
            return self.def_boost
        return self.spdef_boost

    def get_def_reduce(self, skill: Skill) -> float:
        if skill.category == SkillCategory.PHYSICAL:
            return self.def_reduce
        return self.spdef_reduce

    # ------------------------------------------------------------------
    # Buff / Debuff
    # ------------------------------------------------------------------
    def apply_self_buff(self, skill: Skill) -> None:
        self.atk_boost += skill.self_atk + skill.self_all_atk
        self.def_boost += skill.self_def + skill.self_all_def
        self.spatk_boost += skill.self_spatk + skill.self_all_atk
        self.spdef_boost += skill.self_spdef + skill.self_all_def
        self.speed_boost += max(0, skill.self_speed)
        if skill.self_speed < 0:
            self.speed_reduce += abs(skill.self_speed)
        self.power_bonus += getattr(skill, '_power_bonus', 0)

    def apply_enemy_debuff(self, skill: Skill) -> None:
        self.atk_reduce += skill.enemy_atk + skill.enemy_all_atk
        self.def_reduce += skill.enemy_def + skill.enemy_all_def
        self.spatk_reduce += skill.enemy_spatk + skill.enemy_all_atk
        self.spdef_reduce += skill.enemy_spdef + skill.enemy_all_def
        if skill.enemy_speed > 0:
            self.speed_reduce += skill.enemy_speed

    def reset_mods(self) -> None:
        self.atk_boost = self.def_boost = self.spatk_boost = 0.0
        self.spdef_boost = self.speed_boost = 0.0
        self.atk_reduce = self.def_reduce = self.spatk_reduce = 0.0
        self.spdef_reduce = self.speed_reduce = 0.0
        self.power_bonus = 0

    # ------------------------------------------------------------------
    # 异常状态清除
    # ------------------------------------------------------------------
    def clear_debuffs(self) -> None:
        """清除所有负面异常状态（技能清除负面时调用）"""
        self.burn_stacks = 0
        self.poison_stacks = 0
        self.freeze_stacks = 0
        self.parasited_by = None

    # ------------------------------------------------------------------
    # 能量
    # ------------------------------------------------------------------
    def gain_energy(self, amount: int) -> None:
        self.energy = min(ENERGY_MAX, self.energy + amount)

    def lose_energy(self, amount: int) -> None:
        self.energy = max(0, self.energy - amount)

    # ------------------------------------------------------------------
    # 生命值
    # ------------------------------------------------------------------
    def heal(self, amount: int) -> int:
        before = self.current_hp
        self.current_hp = min(self.hp, self.current_hp + amount)
        return self.current_hp - before

    def take_damage(self, amount: int) -> int:
        actual = min(self.current_hp, amount)
        self.current_hp -= actual
        if self.current_hp <= 0:
            self.current_hp = 0
            self.status = StatusType.FAINTED
        return actual

    # ------------------------------------------------------------------
    # 深复制
    # ------------------------------------------------------------------
    def copy_state(self) -> "Pokemon":
        p = Pokemon(
            name=self.name, pokemon_type=self.pokemon_type,
            hp=self.hp, attack=self.attack, defense=self.defense,
            sp_attack=self.sp_attack, sp_defense=self.sp_defense,
            speed=self.speed, secondary_type=self.secondary_type,
            ability=self.ability,
            skills=[s.copy() for s in self.skills],
            current_hp=self.current_hp, energy=self.energy,
            status=self.status,
        )
        p.atk_boost = self.atk_boost
        p.def_boost = self.def_boost
        p.spatk_boost = self.spatk_boost
        p.spdef_boost = self.spdef_boost
        p.speed_boost = self.speed_boost
        p.atk_reduce = self.atk_reduce
        p.def_reduce = self.def_reduce
        p.spatk_reduce = self.spatk_reduce
        p.spdef_reduce = self.spdef_reduce
        p.speed_reduce = self.speed_reduce
        p.burn_stacks = self.burn_stacks
        p.poison_stacks = self.poison_stacks
        p.freeze_stacks = self.freeze_stacks
        p.parasited_by = self.parasited_by
        p.power_bonus = self.power_bonus
        p.cooldowns = dict(self.cooldowns)
        return p
