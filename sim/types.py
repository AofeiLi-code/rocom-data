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
# 属性克制表 — 来源：roco-world skill 数据（仅记录非 1.0 的倍率）
#
# 数据格式：TYPE_CHART[攻击属性][防御属性] = 倍率
# 倍率说明：
#   2.0 = 克制（普通克制），3.0 由 damage_calc.py 在双弱时动态计算
#   0.5 = 被抵抗
#   roco-world 无免疫（0x），已移除原标准 Pokémon 的免疫条目
#
# 注意：光系（PSYCHIC）同时承载了游戏内 "光" 和 "幻" 两种属性的近似
# （两种属性克制关系不同，此处以 "光" 系数据为准，"幻" 属性会有偏差）
# ============================================================
TYPE_CHART: Dict[str, Dict[str, float]] = {
    # 普通系：对地/幽/机械 0.5x
    "normal":   {"ground": 0.5, "ghost": 0.5, "steel": 0.5},

    # 草系：克制水/幻(psychic)/地；被火/龙/毒/虫/翼/机械 0.5x
    "grass":    {"water": 2, "psychic": 2, "ground": 2,
                 "fire": 0.5, "dragon": 0.5, "poison": 0.5,
                 "bug": 0.5, "flying": 0.5, "steel": 0.5},

    # 火系：克制草/冰/虫/机械；被水/地/龙 0.5x
    "fire":     {"grass": 2, "ice": 2, "bug": 2, "steel": 2,
                 "water": 0.5, "ground": 0.5, "dragon": 0.5},

    # 水系：克制火/地/机械；被草/冰/龙 0.5x
    "water":    {"fire": 2, "ground": 2, "steel": 2,
                 "grass": 0.5, "ice": 0.5, "dragon": 0.5},

    # 光系（代理 "光" 属性）：克制幽/恶；被草/冰 0.5x
    "psychic":  {"ghost": 2, "dark": 2,
                 "grass": 0.5, "ice": 0.5},

    # 地系：克制火/冰/电/毒；被草/武 0.5x
    "ground":   {"fire": 2, "ice": 2, "electric": 2, "poison": 2,
                 "grass": 0.5, "fighting": 0.5},

    # 冰系：克制草/地/龙/翼；被火/冰/机械 0.5x
    "ice":      {"grass": 2, "ground": 2, "dragon": 2, "flying": 2,
                 "fire": 0.5, "ice": 0.5, "steel": 0.5},

    # 龙系：克制龙；被机械 0.5x
    "dragon":   {"dragon": 2,
                 "steel": 0.5},

    # 电系：克制水/翼；被草/地/龙/电 0.5x
    "electric": {"water": 2, "flying": 2,
                 "grass": 0.5, "ground": 0.5, "dragon": 0.5, "electric": 0.5},

    # 毒系：克制草/萌；被地/毒/幽/机械 0.5x
    "poison":   {"grass": 2, "fairy": 2,
                 "ground": 0.5, "poison": 0.5, "ghost": 0.5, "steel": 0.5},

    # 虫系：克制草/恶/幻(psychic)；被火/毒/武/翼/萌/幽/机械 0.5x
    "bug":      {"grass": 2, "dark": 2, "psychic": 2,
                 "fire": 0.5, "poison": 0.5, "fighting": 0.5,
                 "flying": 0.5, "fairy": 0.5, "ghost": 0.5, "steel": 0.5},

    # 武系：克制普通/地/冰/恶/机械；被毒/虫/翼/萌/幽/幻(psychic) 0.5x
    "fighting": {"normal": 2, "ground": 2, "ice": 2, "dark": 2, "steel": 2,
                 "poison": 0.5, "bug": 0.5, "flying": 0.5,
                 "fairy": 0.5, "ghost": 0.5, "psychic": 0.5},

    # 翼系：克制草/虫/武；被地/龙/电/机械 0.5x
    "flying":   {"grass": 2, "bug": 2, "fighting": 2,
                 "ground": 0.5, "dragon": 0.5, "electric": 0.5, "steel": 0.5},

    # 萌系：克制龙/武/恶；被火/毒/机械 0.5x
    "fairy":    {"dragon": 2, "fighting": 2, "dark": 2,
                 "fire": 0.5, "poison": 0.5, "steel": 0.5},

    # 幽系：克制光(psychic)/幽/幻(psychic)；被普通/恶 0.5x
    "ghost":    {"psychic": 2, "ghost": 2,
                 "normal": 0.5, "dark": 0.5},

    # 恶系：克制毒/萌/幽；被光(psychic)/武/恶 0.5x
    "dark":     {"poison": 2, "fairy": 2, "ghost": 2,
                 "psychic": 0.5, "fighting": 0.5, "dark": 0.5},

    # 机械系：克制地/冰/萌；被火/水/电/机械 0.5x
    "steel":    {"ground": 2, "ice": 2, "fairy": 2,
                 "fire": 0.5, "water": 0.5, "electric": 0.5, "steel": 0.5},

    # 岩系：roco-world 未收录此属性，保留空表（全 1.0x 兜底）
    "rock":     {},
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
