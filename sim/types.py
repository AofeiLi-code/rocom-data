"""
NRC_SIM 类型系统 — 枚举定义 + 属性克制表
"""

from enum import Enum
from typing import Dict


# ============================================================
# 属性系别
# ============================================================
class Type(Enum):
    NORMAL = "normal"
    FIRE = "fire"
    WATER = "water"
    ELECTRIC = "electric"
    GRASS = "grass"
    ICE = "ice"
    FIGHTING = "fighting"
    POISON = "poison"
    GROUND = "ground"
    FLYING = "flying"
    PSYCHIC = "psychic"
    BUG = "bug"
    ROCK = "rock"
    GHOST = "ghost"
    DRAGON = "dragon"
    DARK = "dark"
    STEEL = "steel"
    FAIRY = "fairy"


# ============================================================
# 技能分类
# ============================================================
class SkillCategory(Enum):
    PHYSICAL = "物攻"
    MAGICAL = "魔攻"
    DEFENSE = "防御"
    STATUS = "状态"


# ============================================================
# 精灵状态
# ============================================================
class StatusType(Enum):
    NORMAL = "normal"
    POISONED = "poisoned"
    BURNED = "burned"
    PARALYZED = "paralyzed"
    FROZEN = "frozen"
    SLEEP = "sleep"
    CONFUSED = "confused"
    FAINTED = "fainted"


# ============================================================
# 六维属性
# ============================================================
class StatType(Enum):
    HP = "hp"
    ATTACK = "attack"
    DEFENSE = "defense"
    SP_ATTACK = "sp_attack"
    SP_DEFENSE = "sp_defense"
    SPEED = "speed"


# ============================================================
# 天气类型
# ============================================================
class Weather(Enum):
    NONE = "none"
    SNOW = "snow"           # 雪天：场上精灵每回合获得 2 层冻结
    SANDSTORM = "sandstorm" # 沙暴：地系技能能耗减半（向下取整）
    RAIN = "rain"           # 雨天：水系招式威力 +50%

WEATHER_DURATION = 8  # 天气持续回合数


# ============================================================
# 属性克制表 (18x18，只记录非 1.0 的倍率)
# ============================================================
TYPE_CHART: Dict[str, Dict[str, float]] = {
    "normal":   {"rock": 0.5, "ghost": 0, "steel": 0.5},
    "fire":     {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 2,
                 "bug": 2, "rock": 0.5, "dragon": 0.5, "steel": 2},
    "water":    {"fire": 2, "water": 0.5, "grass": 0.5,
                 "ground": 2, "rock": 2, "dragon": 0.5},
    "electric": {"water": 2, "electric": 0.5, "grass": 0.5,
                 "ground": 0, "flying": 2, "dragon": 0.5},
    "grass":    {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5,
                 "ground": 2, "flying": 0.5, "bug": 0.5, "rock": 2,
                 "dragon": 0.5, "steel": 0.5},
    "ice":      {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 0.5,
                 "ground": 2, "flying": 2, "dragon": 2, "steel": 0.5},
    "fighting": {"normal": 2, "ice": 2, "poison": 0.5, "flying": 0.5,
                 "psychic": 0.5, "bug": 0.5, "rock": 2, "ghost": 0,
                 "dark": 2, "steel": 2, "fairy": 0.5},
    "poison":   {"grass": 2, "poison": 0.5, "ground": 0.5,
                 "rock": 0.5, "ghost": 0.5, "steel": 0, "fairy": 2},
    "ground":   {"fire": 2, "electric": 2, "grass": 0.5, "poison": 2,
                 "flying": 0, "bug": 0.5, "rock": 2, "steel": 2},
    "flying":   {"electric": 0.5, "grass": 2, "fighting": 2,
                 "bug": 2, "rock": 0.5, "steel": 0.5},
    "psychic":  {"fighting": 2, "poison": 2, "psychic": 0.5,
                 "dark": 0, "steel": 0.5},
    "bug":      {"fire": 0.5, "grass": 2, "fighting": 0.5, "poison": 0.5,
                 "flying": 0.5, "ghost": 0.5, "psychic": 2, "dark": 2,
                 "steel": 0.5, "fairy": 0.5},
    "rock":     {"fire": 2, "ice": 2, "fighting": 0.5, "ground": 0.5,
                 "flying": 2, "bug": 2, "steel": 0.5},
    "ghost":    {"normal": 0, "psychic": 2, "ghost": 2, "dark": 0.5},
    "dragon":   {"dragon": 2, "steel": 0.5, "fairy": 0},
    "dark":     {"fighting": 0.5, "psychic": 2, "ghost": 2,
                 "dark": 0.5, "fairy": 0.5},
    "steel":    {"fire": 0.5, "water": 0.5, "electric": 0.5,
                 "ice": 2, "rock": 2, "steel": 0.5, "fairy": 2},
    "fairy":    {"fire": 0.5, "fighting": 2, "poison": 0.5,
                 "dragon": 2, "dark": 2, "steel": 0.5},
}


def get_type_effectiveness(attack_type: Type, defense_type: Type) -> float:
    """查询属性克制倍率，未记录的组合默认 1.0"""
    chart = TYPE_CHART.get(attack_type.value)
    if chart is None:
        return 1.0
    return chart.get(defense_type.value, 1.0)


# ============================================================
# 中文 → Type 枚举映射
# ============================================================
TYPE_NAME_MAP: Dict[str, Type] = {
    # 带"系"后缀（skills_all.csv 格式）
    "普通系": Type.NORMAL, "火系": Type.FIRE, "水系": Type.WATER,
    "电系": Type.ELECTRIC, "草系": Type.GRASS, "冰系": Type.ICE,
    "武系": Type.FIGHTING, "毒系": Type.POISON, "地系": Type.GROUND,
    "翼系": Type.FLYING, "幻系": Type.PSYCHIC, "虫系": Type.BUG,
    "机械系": Type.STEEL, "幽系": Type.GHOST, "龙系": Type.DRAGON,
    "恶系": Type.DARK, "萌系": Type.FAIRY, "光系": Type.PSYCHIC,
    "岩系": Type.ROCK,
    # 单字简写（sprites.json 格式）
    "普通": Type.NORMAL, "火": Type.FIRE, "水": Type.WATER,
    "电": Type.ELECTRIC, "草": Type.GRASS, "冰": Type.ICE,
    "武": Type.FIGHTING, "毒": Type.POISON, "地": Type.GROUND,
    "翼": Type.FLYING, "幻": Type.PSYCHIC, "虫": Type.BUG,
    "机械": Type.STEEL, "幽": Type.GHOST, "龙": Type.DRAGON,
    "恶": Type.DARK, "萌": Type.FAIRY, "光": Type.PSYCHIC,
    "岩": Type.ROCK,
}


def normalize_type(s: str) -> Type:
    """
    将中文属性字符串统一转换为 Type 枚举。
    同时兼容 sprites.json 的单字格式（'光'/'火'）
    和 skills_all.csv 的带系格式（'光系'/'火系'）。
    未识别时返回 Type.NORMAL。
    """
    if not s:
        return Type.NORMAL
    # 直接查找（含两种格式）
    t = TYPE_NAME_MAP.get(s)
    if t is not None:
        return t
    # 尝试去掉末尾"系"后再查
    if s.endswith("系"):
        t = TYPE_NAME_MAP.get(s[:-1])
        if t is not None:
            return t
    return Type.NORMAL

CATEGORY_NAME_MAP: Dict[str, SkillCategory] = {
    "物攻": SkillCategory.PHYSICAL,
    "魔攻": SkillCategory.MAGICAL,
    "防御": SkillCategory.DEFENSE,
    "变化": SkillCategory.STATUS,
    "状态": SkillCategory.STATUS,
}
