"""
NRC_SIM 精灵数据库 — 从 data/sprites.json 加载精灵属性

六维计算公式（洛克王国）:
  HP   = [1.7 × 种族值 + 个体值 × 0.85 + 70] × (1 + 性格修正) + 100
  其他 = [1.1 × 种族值 + 个体值 × 0.55 + 10] × (1 + 性格修正) + 50

个体值规则（简化）:
  - 3 项各获得 10 点，其余为 0
  - 速度种族值 > 中位数: 速度 + max(物攻,魔攻) + 生命
  - 速度种族值 ≤ 中位数: max(物攻,魔攻) + 生命 + max(物防,魔防)

性格修正:
  - 六维中种族值最高的一项: +0.2
  - 六维中种族值最低的一项: -0.1
  - 并列则随机选一个（seed=42 固定）
"""

import json
import os
import random
from typing import Dict, List, Optional


_db: Dict[str, dict] = {}

# 速度种族值中位数（从原 461 只精灵统计）
_SPEED_MEDIAN: int = 84


# ============================================================
# 六维计算
# ============================================================
def _calc_hp(base_race: int, iv: int, nature_mod: float) -> int:
    return int((1.7 * base_race + iv * 0.85 + 70) * (1 + nature_mod) + 100)


def _calc_stat(base_race: int, iv: int, nature_mod: float) -> int:
    return int((1.1 * base_race + iv * 0.55 + 10) * (1 + nature_mod) + 50)


def _compute_battle_stats(race_values: Dict[str, int]) -> Dict[str, int]:
    rv = race_values
    stat_names = ["hp", "atk", "spatk", "def", "spdef", "speed"]

    iv = {s: 0 for s in stat_names}
    iv["hp"] = 10

    if rv["atk"] >= rv["spatk"]:
        iv["atk"] = 10
    else:
        iv["spatk"] = 10

    if rv["speed"] > _SPEED_MEDIAN:
        iv["speed"] = 10
    else:
        if rv["def"] >= rv["spdef"]:
            iv["def"] = 10
        else:
            iv["spdef"] = 10

    # 性格只作用于战斗属性（不含 HP），从 5 个战斗属性中选最高/最低
    combat_stats = ["atk", "spatk", "def", "spdef", "speed"]
    combat_list  = [(s, rv[s]) for s in combat_stats]
    max_val = max(v for _, v in combat_list)
    min_val = min(v for _, v in combat_list)
    max_cs  = [s for s, v in combat_list if v == max_val]
    min_cs  = [s for s, v in combat_list if v == min_val]

    boost_stat = random.choice(max_cs)
    reduce_cands = [s for s in min_cs if s != boost_stat]
    if not reduce_cands:
        reduce_cands = [s for s in combat_stats if s != boost_stat]
    reduce_stat = random.choice(reduce_cands)

    # 查命名性格（找不到时用"认真"中性兜底）
    nature_name = NATURE_BY_STATS.get((boost_stat, reduce_stat), "认真")

    nature = {s: 0.0 for s in stat_names}
    pair = NATURES[nature_name]
    if pair[0]:
        nature[pair[0]] = 0.1    # 真实游戏 +10%
        nature[pair[1]] = -0.1   # 真实游戏 -10%
    # HP 不受性格影响

    return {
        "生命值": _calc_hp(rv["hp"],    iv["hp"],    nature["hp"]),
        "物攻":   _calc_stat(rv["atk"],   iv["atk"],   nature["atk"]),
        "魔攻":   _calc_stat(rv["spatk"], iv["spatk"], nature["spatk"]),
        "物防":   _calc_stat(rv["def"],   iv["def"],   nature["def"]),
        "魔防":   _calc_stat(rv["spdef"], iv["spdef"], nature["spdef"]),
        "速度":   _calc_stat(rv["speed"], iv["speed"], nature["speed"]),
        "性格":   nature_name,   # 命名性格，如 "胆小"
    }


# ============================================================
# 数据加载
# ============================================================
def load_pokemon_db(filepath: Optional[str] = None) -> None:
    """从 sprites.json 加载精灵种族值，并用公式计算进战六维"""
    global _db
    if _db:
        return

    if not filepath:
        filepath = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "sprites.json"
        )

    if not os.path.exists(filepath):
        print(f"[WARN] 精灵数据库不存在: {filepath}")
        return

    with open(filepath, encoding="utf-8") as f:
        sprites = json.load(f)

    # 预先确定每个 no 下是否存在 form=None 的精灵（即"最终形态"）
    final_nos: set = set()
    for sprite in sprites:
        if sprite.get("form") is None:
            final_nos.add(str(sprite["no"]))

    rng_state = random.getstate()
    random.seed(42)

    for sprite in sprites:
        name = sprite.get("name")
        if not name:
            continue

        no_str = str(sprite["no"])
        form = sprite.get("form")

        # 进化阶段：同一 no 下 form 为 null 的视为最终形态，其余为非最终
        if form is None:
            stage = "最终形态"
        else:
            stage = "非最终"

        # 同名冲突时优先保留最终形态
        existing = _db.get(name)
        if existing and existing.get("进化阶段") == "最终形态" and stage != "最终形态":
            continue

        stats = sprite.get("stats", {})
        race = {
            "hp":    int(stats.get("hp",     0)),
            "atk":   int(stats.get("atk",    0)),
            "spatk": int(stats.get("sp_atk", 0)),
            "def":   int(stats.get("def",    0)),
            "spdef": int(stats.get("sp_def", 0)),
            "speed": int(stats.get("spd",    0)),
        }

        battle_stats = _compute_battle_stats(race)

        ability = sprite.get("ability", {})
        ability_str = f"{ability.get('name', '')}:{ability.get('description', '')}"

        attributes = sprite.get("attributes", [])
        attr_str = attributes[0] if attributes else "普通"

        _db[name] = {
            "编号":       no_str,
            "名称":       name,
            "属性":       attr_str,
            "属性列表":   attributes,
            "进化阶段":   stage,
            "特性":       ability_str,
            "生命种族值": race["hp"],
            "物攻种族值": race["atk"],
            "魔攻种族值": race["spatk"],
            "物防种族值": race["def"],
            "魔防种族值": race["spdef"],
            "速度种族值": race["speed"],
            "种族值总和": sum(race.values()),
            "生命值":     battle_stats["生命值"],
            "物攻":       battle_stats["物攻"],
            "魔攻":       battle_stats["魔攻"],
            "物防":       battle_stats["物防"],
            "魔防":       battle_stats["魔防"],
            "速度":       battle_stats["速度"],
            "性格":       battle_stats["性格"],    # 命名性格
        }

    random.setstate(rng_state)
    print(f"[OK] 精灵数据库已加载: {len(_db)} 只精灵 (来源: sprites.json)")


# ============================================================
# 查询
# ============================================================
def get_pokemon(name: str) -> Optional[dict]:
    """
    根据名称获取精灵数据。
    支持：精确匹配 → 模糊包含 → 忽略括号匹配。
    优先选择"最终形态"。
    """
    load_pokemon_db()

    if name in _db:
        return _db[name]

    candidates = []
    for key, data in _db.items():
        if name in key or key in name:
            candidates.append((key, data))

    if not candidates:
        base_name = name.split("\uff08")[0]
        for key, data in _db.items():
            key_base = key.split("\uff08")[0]
            if base_name == key_base:
                candidates.append((key, data))

    if candidates:
        for key, data in candidates:
            if data.get("进化阶段") == "最终形态":
                return data
        return candidates[0][1]

    return None


def search_pokemon(keyword: str) -> List[dict]:
    """搜索精灵"""
    load_pokemon_db()
    results = []
    for key, data in _db.items():
        if keyword in key or keyword in str(data.get("特性", "")):
            results.append(data)
    return results[:20]


# ============================================================
# 性格系统（25 种，来自 roco-world 数据）
# ============================================================
# 内部键 → 中文显示名（HP 不参与性格）
_STAT_KEY_DISPLAY = {
    "atk": "物攻", "def": "物防", "spatk": "魔攻",
    "spdef": "魔防", "speed": "速度",
}

# 旧版中文名 → 内部键（用于 teams.json 旧数据迁移）
_STAT_CN_TO_KEY = {
    "生命": "hp", "物攻": "atk", "魔攻": "spatk",
    "物防": "def", "魔防": "spdef", "速度": "speed",
}

# 25 种命名性格：name → (boost_key, reduce_key)，None = 无变化
NATURES: Dict[str, tuple] = {
    "胆小": ("speed",  "atk"),   "急躁": ("speed",  "def"),
    "天真": ("speed",  "spdef"), "开朗": ("speed",  "spatk"),
    "固执": ("atk",    "spatk"), "勇敢": ("atk",    "speed"),
    "调皮": ("atk",    "spdef"), "孤独": ("atk",    "def"),
    "保守": ("spatk",  "atk"),   "冷静": ("spatk",  "speed"),
    "马虎": ("spatk",  "spdef"), "稳重": ("spatk",  "def"),
    "淘气": ("def",    "spatk"), "大胆": ("def",    "atk"),
    "悠闲": ("def",    "speed"),
    "沉着": ("spdef",  "atk"),   "慎重": ("spdef",  "spatk"),
    "温顺": ("spdef",  "def"),   "狂妄": ("spdef",  "speed"),
    "认真": (None, None), "实干": (None, None), "坦率": (None, None),
    "害羞": (None, None), "浮躁": (None, None),
}

# 反查：(boost_key, reduce_key) → 性格名
NATURE_BY_STATS: Dict[tuple, str] = {
    v: k for k, v in NATURES.items() if v[0] is not None
}

# 供 battle.py 列出可选性格（战斗属性，不含生命）
NATURE_STATS = list(_STAT_KEY_DISPLAY.values())   # ["物攻","物防","魔攻","魔防","速度"]


def nature_display(nature_name: str) -> str:
    """返回性格的完整显示，如 '胆小（速度↑物攻↓）'"""
    pair = NATURES.get(nature_name, (None, None))
    if pair[0] is None:
        return f"{nature_name}（无变化）"
    return (f"{nature_name}（{_STAT_KEY_DISPLAY[pair[0]]}↑"
            f"{_STAT_KEY_DISPLAY[pair[1]]}↓）")


def compute_stats_with_nature(name: str, nature_name: str) -> Optional[dict]:
    """
    用指定命名性格重新计算精灵的进战六维。

    Parameters
    ----------
    name         : 精灵名
    nature_name  : 性格名，如 "开朗" / "胆小"（须在 NATURES 中）

    Returns
    -------
    {"生命值": int, "物攻": int, ...} 或 None（精灵不存在）
    """
    load_pokemon_db()
    data = _db.get(name) or get_pokemon(name)
    if not data:
        return None

    race = {
        "hp":    data["生命种族值"], "atk":   data["物攻种族值"],
        "spatk": data["魔攻种族值"], "def":   data["物防种族值"],
        "spdef": data["魔防种族值"], "speed": data["速度种族值"],
    }
    stat_names = ["hp", "atk", "spatk", "def", "spdef", "speed"]

    iv = {s: 0 for s in stat_names}
    iv["hp"] = 10
    iv["atk" if race["atk"] >= race["spatk"] else "spatk"] = 10
    if race["speed"] > _SPEED_MEDIAN:
        iv["speed"] = 10
    else:
        iv["def" if race["def"] >= race["spdef"] else "spdef"] = 10

    nature = {s: 0.0 for s in stat_names}
    pair = NATURES.get(nature_name, (None, None))
    if pair[0]:
        nature[pair[0]] = 0.1
        nature[pair[1]] = -0.1

    return {
        "生命值": _calc_hp(race["hp"],    iv["hp"],    nature["hp"]),
        "物攻":   _calc_stat(race["atk"],   iv["atk"],   nature["atk"]),
        "魔攻":   _calc_stat(race["spatk"], iv["spatk"], nature["spatk"]),
        "物防":   _calc_stat(race["def"],   iv["def"],   nature["def"]),
        "魔防":   _calc_stat(race["spdef"], iv["spdef"], nature["spdef"]),
        "速度":   _calc_stat(race["speed"], iv["speed"], nature["speed"]),
    }


def get_nature(name: str) -> Optional[str]:
    """
    返回精灵的命名性格，如 "胆小"。未找到时返回 None。
    """
    load_pokemon_db()
    data = get_pokemon(name)
    return data.get("性格") if data else None


def get_all_pokemon_names() -> List[str]:
    """返回数据库中所有精灵名列表"""
    load_pokemon_db()
    return list(_db.keys())
