"""
NRC_SIM 队伍构建器 — 从数据库自动构建精灵和队伍

交互式组队见 sim/team_builder_interactive.py 中的 build_team_interactive()。
"""

from typing import List, Optional

from sim.types import Type, normalize_type
from sim.pokemon import Pokemon
from sim.skill_db import get_skill
from sim.pokemon_db import get_pokemon, compute_stats_with_nature, NATURES
from sim.team_builder_interactive import build_team_interactive  # noqa: F401


def build_pokemon(
    name: str,
    skill_names: List[str],
    nature: Optional[str] = None,   # 命名性格，如 "开朗"
) -> Pokemon:
    """
    根据精灵名称从数据库获取六维数据，构造 Pokemon 对象。

    nature 为性格名（来自 NATURES 表，如 "开朗"）。
    提供时用对应性格重新计算六维，否则使用数据库的自动性格。
    """
    data = get_pokemon(name)
    if data:
        attrs: list = data.get("属性列表", [data.get("属性", "普通")])
        ability = data["特性"]

        # 若指定了命名性格且合法，重新计算六维
        if nature and nature in NATURES:
            custom = compute_stats_with_nature(name, nature)
            if custom:
                hp    = int(custom["生命值"])
                atk   = int(custom["物攻"])
                dfn   = int(custom["物防"])
                spatk = int(custom["魔攻"])
                spdef = int(custom["魔防"])
                spd   = int(custom["速度"])
            else:
                nature = None   # 回退到自动

        if not (nature and nature in NATURES):
            hp    = int(data["生命值"])
            atk   = int(data["物攻"])
            dfn   = int(data["物防"])
            spatk = int(data["魔攻"])
            spdef = int(data["魔防"])
            spd   = int(data["速度"])
    else:
        print(f"[WARN] 精灵 '{name}' 未在数据库中找到，使用默认属性")
        attrs = ["普通"]
        ability = "未知"
        hp, atk, dfn, spatk, spdef, spd = 500, 350, 350, 350, 350, 350

    primary_type = normalize_type(attrs[0]) if attrs else Type.NORMAL
    secondary_type: Optional[Type] = normalize_type(attrs[1]) if len(attrs) > 1 else None

    skills = [get_skill(n) for n in skill_names]
    return Pokemon(
        name=name, pokemon_type=primary_type, secondary_type=secondary_type,
        hp=hp, attack=atk, defense=dfn,
        sp_attack=spatk, sp_defense=spdef,
        speed=spd, ability=ability, skills=skills,
    )


# ============================================================
# 预设队伍
# ============================================================
def create_toxic_team() -> List[Pokemon]:
    """毒队"""
    return [
        build_pokemon("千棘盔", ["毒雾", "泡沫幻影", "疫病吐息", "打湿"]),
        build_pokemon("影狸", ["嘲弄", "恶意逃离", "毒液渗透", "感染病"]),
        build_pokemon("裘卡", ["阻断", "崩拳", "毒囊", "防御"]),
        build_pokemon("琉璃水母", ["甩水", "天洪", "泡沫幻影", "以毒攻毒"]),
        build_pokemon("迷迷箱怪", ["风墙", "啮合传递", "双星", "偷袭"]),
        build_pokemon("海豹船长", ["力量增效", "水刃", "斩断", "听桥"]),
    ]


def create_wing_team() -> List[Pokemon]:
    """翼王队"""
    return [
        build_pokemon("燃薪虫", ["火焰护盾", "引燃", "倾泻", "抽枝"]),
        build_pokemon("圣羽翼王", ["水刃", "力量增效", "疾风连袭", "扇风"]),
        build_pokemon("翠顶夫人", ["力量增效", "水刃", "水环", "泡沫幻影"]),
        build_pokemon("迷迷箱怪", ["双星", "啮合传递", "偷袭", "吓退"]),
        build_pokemon("秩序鱿墨", ["风墙", "能量刃", "力量增效", "倾泻"]),
        build_pokemon("声波缇塔", ["轴承支撑", "齿轮扭矩", "地刺", "啮合传递"]),
    ]
