"""
NRC_SIM 技能数据库 — 从 CSV 加载并解析效果描述

威力数据来源：data/skills_all.csv（唯一含威力数值的文件）
技能归属数据：data/sprites.json（每只精灵的可学技能列表）
"""

import csv
import json
import os
import re
from typing import Dict, List, Optional

from sim.types import Type, SkillCategory, TYPE_NAME_MAP, CATEGORY_NAME_MAP
from sim.skill import Skill


_skill_db: Dict[str, Skill] = {}

# 精灵名 -> 可学技能名列表，按需延迟加载
_learnable: Dict[str, List[str]] = {}
_learnable_loaded: bool = False


# ============================================================
# 效果描述解析器（与原版完全一致）
# ============================================================
def parse_effect(skill: Skill, desc: str) -> Skill:
    """从中文效果描述文本中用正则提取所有效果参数"""
    d = desc.replace("\uff0c", ",").replace("\u3002", "").replace("\uff1a", ":")

    m = re.search(r'(\d+)连击', d)
    if m:
        skill.hit_count = int(m.group(1))

    m = re.search(r'吸血(\d+)%', d)
    if m:
        skill.life_drain = int(m.group(1)) / 100.0

    m = re.search(r'减伤(\d+)%', d)
    if m:
        skill.damage_reduction = int(m.group(1)) / 100.0

    for pattern in [r'回复(\d+)%生命', r'自己回复(\d+)%生命']:
        m = re.search(pattern, d)
        if m:
            skill.self_heal_hp = int(m.group(1)) / 100.0

    m = re.search(r'回复(\d+)能量', d)
    if m:
        skill.self_heal_energy = int(m.group(1))

    m = re.search(r'偷取敌方?(\d+)能量', d)
    if m:
        skill.steal_energy = int(m.group(1))

    m = re.search(r'敌方失去(\d+)能量', d)
    if m:
        skill.enemy_lose_energy = int(m.group(1))

    m = re.search(r'先手\+(\d+)', d)
    if m:
        skill.priority_mod = int(m.group(1))
    m = re.search(r'先手-(\d+)', d)
    if m:
        skill.priority_mod = -int(m.group(1))

    if '脱离' in d:
        skill.force_switch = True
    if '迅捷' in d:
        skill.agility = True
    if '蓄力' in d:
        skill.charge = True

    def parse_self_stat(pattern, fld):
        m = re.search(pattern, d)
        if m:
            setattr(skill, fld, int(m.group(1)) / 100.0)

    parse_self_stat(r'获得物攻\+(\d+)%', 'self_atk')
    parse_self_stat(r'获得魔攻\+(\d+)%', 'self_spatk')
    parse_self_stat(r'获得物防\+(\d+)%', 'self_def')
    parse_self_stat(r'获得魔防\+(\d+)%', 'self_spdef')

    m = re.search(r'获得速度\+(\d+)', d)
    if m:
        skill.self_speed = int(m.group(1)) / 100.0
    m = re.search(r'获得速度-(\d+)', d)
    if m:
        skill.self_speed = -int(m.group(1)) / 100.0

    m = re.search(r'双攻\+(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_atk += v
        skill.self_spatk += v
    m = re.search(r'双攻-(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_atk -= v
        skill.self_spatk -= v
    m = re.search(r'双防\+(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_def += v
        skill.self_spdef += v
    m = re.search(r'双防-(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_def -= v
        skill.self_spdef -= v

    m = re.search(r'获得技能威力\+(\d+)', d)
    if m:
        skill.power += int(m.group(1))
    m = re.search(r'全技能威力\+(\d+)', d)
    if m:
        skill.power += int(m.group(1))

    def parse_enemy_stat(pattern, fld):
        m = re.search(pattern, d)
        if m:
            setattr(skill, fld, int(m.group(1)) / 100.0)

    parse_enemy_stat(r'敌方获得物攻-(\d+)%', 'enemy_atk')
    parse_enemy_stat(r'敌方获得魔攻-(\d+)%', 'enemy_spatk')
    parse_enemy_stat(r'敌方获得物防-(\d+)%', 'enemy_def')
    parse_enemy_stat(r'敌方获得魔防-(\d+)%', 'enemy_spdef')
    parse_enemy_stat(r'敌方获得双攻-(\d+)%', 'enemy_all_atk')
    parse_enemy_stat(r'敌方获得双防-(\d+)%', 'enemy_all_def')

    m = re.search(r'(\d+)层中毒', d)
    if m:
        skill.poison_stacks = int(m.group(1))
    m = re.search(r'(\d+)层灼烧', d)
    if m:
        skill.burn_stacks = int(m.group(1))
    m = re.search(r'(\d+)层冻结', d)
    if m:
        skill.freeze_stacks = int(m.group(1))

    m = re.search(r'敌方获得全技能能耗\+(\d+)', d)
    if m:
        skill.enemy_energy_cost_up = int(m.group(1))

    if '应对攻击' in d:
        m = re.search(r'应对攻击.*?吸血(\d+)%', d)
        if m:
            skill.counter_physical_drain = int(m.group(1)) / 100.0
        m = re.search(r'应对攻击.*?失去(\d+)能量', d)
        if m:
            skill.counter_physical_energy_drain = int(m.group(1))
        m = re.search(r'应对攻击.*?物攻\+(\d+)%', d)
        if m:
            skill.counter_physical_self_atk = int(m.group(1)) / 100.0
        m = re.search(r'应对攻击.*?物防-(\d+)%', d)
        if m:
            skill.counter_physical_enemy_def = int(m.group(1)) / 100.0
        m = re.search(r'应对攻击.*?物攻-(\d+)%', d)
        if m:
            skill.counter_physical_enemy_atk = int(m.group(1)) / 100.0

    if '应对状态' in d:
        m = re.search(r'应对状态.*?威力.*?(\d+)倍', d)
        if m:
            skill.counter_status_power_mult = int(m.group(1))
        m = re.search(r'应对状态.*?翻倍', d)
        if m and skill.counter_status_power_mult == 0:
            skill.counter_status_power_mult = 2
        m = re.search(r'应对状态.*?失去(\d+)能量', d)
        if m:
            skill.counter_status_enemy_lose_energy = int(m.group(1))
        m = re.search(r'应对状态.*?物攻\+(\d+)%', d)
        if m:
            skill.counter_physical_self_atk = int(m.group(1)) / 100.0
        m = re.search(r'应对状态.*?吸血(\d+)%', d)
        if m:
            skill.counter_physical_drain = int(m.group(1)) / 100.0

    if '应对防御' in d:
        m = re.search(r'应对防御.*?物攻\+(\d+)%', d)
        if m:
            skill.counter_defense_self_atk = int(m.group(1)) / 100.0
        m = re.search(r'应对防御.*?物防\+(\d+)%', d)
        if m:
            skill.counter_defense_self_def = int(m.group(1)) / 100.0
        m = re.search(r'应对防御.*?物防-(\d+)%', d)
        if m:
            skill.counter_defense_enemy_def = int(m.group(1)) / 100.0
        m = re.search(r'应对防御.*?双防-(\d+)%', d)
        if m:
            v = int(m.group(1)) / 100.0
            skill.counter_defense_enemy_def += v
        m = re.search(r'应对防御.*?攻击技能能耗\+(\d+)', d)
        if m:
            skill.counter_defense_enemy_energy_cost = int(m.group(1))
        m = re.search(r'应对防御.*?失去(\d+)能量', d)
        if m:
            skill.counter_defense_enemy_energy_cost = int(m.group(1))
        m = re.search(r'应对防御.*?(\d+)层中毒', d)
        if m:
            skill.counter_status_poison_stacks = int(m.group(1))

    return skill


# ============================================================
# CSV 解析
# ============================================================
def _parse_csv_row(row):
    name = row[0].strip()
    if not name:
        return None

    skill_type = TYPE_NAME_MAP.get(row[1].strip(), Type.NORMAL)
    category = CATEGORY_NAME_MAP.get(row[2].strip(), SkillCategory.PHYSICAL)

    power = 0
    try:
        power = int(row[3].strip())
    except (ValueError, IndexError):
        pass

    energy = 0
    try:
        energy = int(row[4].strip())
    except (ValueError, IndexError):
        pass

    desc = row[5].strip() if len(row) > 5 else ""

    skill = Skill(
        name=name, skill_type=skill_type, category=category,
        power=power, energy_cost=energy,
    )

    if desc:
        parse_effect(skill, desc)

    return skill


def load_skills(csv_path: Optional[str] = None) -> Dict[str, Skill]:
    """加载技能数据库（威力数据来自 skills_all.csv）"""
    global _skill_db
    if _skill_db:
        return _skill_db

    if csv_path is None:
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "skills_all.csv"
        )

    if not os.path.exists(csv_path):
        print(f"[WARN] 技能数据库未找到: {csv_path}")
        return {}

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            skill = _parse_csv_row(row)
            if skill:
                _skill_db[skill.name] = skill

    print(f"[OK] 已加载 {len(_skill_db)} 个技能 (来源: skills_all.csv)")
    return _skill_db


def get_skill(name: str) -> Skill:
    """获取技能（返回副本）。未找到则返回默认普攻"""
    load_skills()
    if name in _skill_db:
        return _skill_db[name].copy()
    return Skill(name=name, skill_type=Type.NORMAL, category=SkillCategory.PHYSICAL,
                 power=40, energy_cost=2)


def get_all_skills() -> Dict[str, Skill]:
    """获取全部技能"""
    load_skills()
    return dict(_skill_db)


# ============================================================
# 精灵可学技能查询（来源：sprites.json）
# ============================================================
def _load_learnable() -> None:
    global _learnable, _learnable_loaded
    if _learnable_loaded:
        return

    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "sprites.json"
    )

    if not os.path.exists(json_path):
        _learnable_loaded = True
        return

    with open(json_path, encoding="utf-8") as f:
        sprites = json.load(f)

    for sprite in sprites:
        name = sprite.get("name")
        if not name:
            continue
        skill_names = [s["name"] for s in sprite.get("skills", []) if s.get("name")]
        # 同名精灵合并（不同形态可能有不同技能，取并集）
        if name in _learnable:
            existing = set(_learnable[name])
            existing.update(skill_names)
            _learnable[name] = list(existing)
        else:
            _learnable[name] = skill_names

    _learnable_loaded = True


def get_learnable_skills(pokemon_name: str) -> List[str]:
    """
    返回指定精灵可学的所有技能名列表（来源：sprites.json）。
    未找到则返回空列表。
    """
    _load_learnable()
    return list(_learnable.get(pokemon_name, []))
