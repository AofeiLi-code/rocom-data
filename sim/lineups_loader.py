"""
BWIKI 玩家配队加载器 — 把 data/lineups.json 转成 teams.json 兼容格式

来源：PR #6 抓取的 169 个玩家配队（pvp / pve）。
转换时保留 pokemon / skills / nature；丢弃 bloodline、talents（sim 引擎未实现）。
"""

import json
import os
from typing import List, Dict

from sim.pokemon_db import NATURES


_LINEUPS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "lineups.json",
)


def load_lineups() -> List[Dict]:
    """读取 data/lineups.json，返回原始 lineup 列表。文件缺失时返回 []。"""
    if not os.path.exists(_LINEUPS_PATH):
        return []
    with open(_LINEUPS_PATH, encoding="utf-8") as f:
        return json.load(f)


def lineup_to_members(lineup: Dict) -> List[Dict]:
    """
    把一条 lineup 的 members 转成 teams.json 兼容的成员列表。
    每条成员保留 pokemon / skills（去空）/ nature（仅当合法时）。
    """
    out: List[Dict] = []
    for m in lineup.get("members", []):
        name = (m.get("pokemon") or "").strip()
        if not name:
            continue
        skills = [s for s in (m.get("skills") or []) if s]
        member: Dict = {"pokemon": name, "skills": skills}
        nature = (m.get("nature") or "").strip()
        if nature and nature in NATURES:
            member["nature"] = nature
        out.append(member)
    return out
