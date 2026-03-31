"""
队伍名册 — 持久化队伍列表，存储于 data/teams.json

数据格式（每条记录）:
  {
    "name":    "毒队",
    "preset":  true,          # true = 内置预设，不可删除
    "members": [
      {"pokemon": "千棘盔", "skills": ["毒雾", "泡沫幻影", "疫病吐息", "打湿"]},
      ...                     # 共 6 条
    ]
  }
"""

import json
import os
from typing import List, Dict, Optional

from sim.pokemon import Pokemon


# ============================================================
# 路径
# ============================================================
_ROSTER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "teams.json",
)

# 内置预设队伍定义（首次启动时写入 JSON）
_BUILTIN_PRESETS = [
    {
        "name": "预设毒队",
        "preset": True,
        "members": [
            {"pokemon": "千棘盔",  "skills": ["毒雾", "泡沫幻影", "疫病吐息", "打湿"]},
            {"pokemon": "影狸",    "skills": ["嘲弄", "恶意逃离", "毒液渗透", "感染病"]},
            {"pokemon": "裘卡",    "skills": ["阻断", "崩拳", "毒囊", "防御"]},
            {"pokemon": "琉璃水母","skills": ["甩水", "天洪", "泡沫幻影", "以毒攻毒"]},
            {"pokemon": "迷迷箱怪","skills": ["风墙", "啮合传递", "双星", "偷袭"]},
            {"pokemon": "海豹船长","skills": ["力量增效", "水刃", "斩断", "听桥"]},
        ],
    },
    {
        "name": "预设翼王队",
        "preset": True,
        "members": [
            {"pokemon": "燃薪虫",  "skills": ["火焰护盾", "引燃", "倾泻", "抽枝"]},
            {"pokemon": "圣羽翼王","skills": ["水刃", "力量增效", "疾风连袭", "扇风"]},
            {"pokemon": "翠顶夫人","skills": ["力量增效", "水刃", "水环", "泡沫幻影"]},
            {"pokemon": "迷迷箱怪","skills": ["双星", "啮合传递", "偷袭", "吓退"]},
            {"pokemon": "秩序鱿墨","skills": ["风墙", "能量刃", "力量增效", "倾泻"]},
            {"pokemon": "声波缇塔","skills": ["轴承支撑", "齿轮扭矩", "地刺", "啮合传递"]},
        ],
    },
]


# ============================================================
# 内部状态
# ============================================================
_roster: List[Dict] = []
_loaded: bool = False


# ============================================================
# 加载 / 保存
# ============================================================
def _load() -> None:
    global _roster, _loaded
    if _loaded:
        return

    if os.path.exists(_ROSTER_PATH):
        with open(_ROSTER_PATH, encoding="utf-8") as f:
            _roster = json.load(f)
        # 确保内置预设始终存在（升级兼容）
        existing_names = {t["name"] for t in _roster}
        for preset in _BUILTIN_PRESETS:
            if preset["name"] not in existing_names:
                _roster.insert(0, dict(preset))
    else:
        _roster = [dict(p) for p in _BUILTIN_PRESETS]
        _save()

    _loaded = True


def _save() -> None:
    with open(_ROSTER_PATH, "w", encoding="utf-8") as f:
        json.dump(_roster, f, ensure_ascii=False, indent=2)


# ============================================================
# 公开 API
# ============================================================
def list_teams() -> List[Dict]:
    """
    返回队伍名册，每条包含:
      name, preset, members (list of {pokemon, skills})
    """
    _load()
    return list(_roster)


def get_team_def(name: str) -> Optional[Dict]:
    """按名称查找队伍定义，未找到返回 None"""
    _load()
    for t in _roster:
        if t["name"] == name:
            return t
    return None


def build_team(name: str) -> List[Pokemon]:
    """
    按名称从名册中构建 Pokemon 列表。
    未找到时抛出 KeyError。
    """
    from sim.team_builder import build_pokemon  # 延迟导入，避免循环
    team_def = get_team_def(name)
    if team_def is None:
        raise KeyError(f"队伍「{name}」不存在")
    return [
        build_pokemon(
            m["pokemon"], m["skills"],
            nature_boost=m.get("nature_boost"),
            nature_reduce=m.get("nature_reduce"),
        )
        for m in team_def["members"]
    ]


def add_team(name: str, members: List[Dict]) -> str:
    """
    添加新队伍到名册并持久化。
    若同名队伍已存在则覆盖（预设不可覆盖）。

    Parameters
    ----------
    name    : 队伍名称
    members : [{"pokemon": "名字", "skills": ["技能1", ...]}, ...]

    Returns
    -------
    "added" | "replaced"
    """
    _load()
    for t in _roster:
        if t["name"] == name:
            if t.get("preset"):
                raise ValueError(f"「{name}」是内置预设，不可覆盖")
            t["members"] = members
            _save()
            return "replaced"
    _roster.append({"name": name, "preset": False, "members": members})
    _save()
    return "added"


def delete_team(name: str) -> None:
    """
    删除队伍。预设不可删除，未找到时抛出 KeyError。
    """
    _load()
    for i, t in enumerate(_roster):
        if t["name"] == name:
            if t.get("preset"):
                raise ValueError(f"「{name}」是内置预设，不可删除")
            _roster.pop(i)
            _save()
            return
    raise KeyError(f"队伍「{name}」不存在")


def rename_team(old_name: str, new_name: str) -> None:
    """重命名自定义队伍"""
    _load()
    team_def = get_team_def(old_name)
    if team_def is None:
        raise KeyError(f"队伍「{old_name}」不存在")
    if team_def.get("preset"):
        raise ValueError(f"「{old_name}」是内置预设，不可重命名")
    if get_team_def(new_name) is not None:
        raise ValueError(f"「{new_name}」已存在")
    team_def["name"] = new_name
    _save()
