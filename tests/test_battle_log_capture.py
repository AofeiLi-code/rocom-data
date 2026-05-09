"""
战斗日志捕获 — 不依赖 MariaDB 的烟雾测试。

验证：
1. BattleLogRecord 模型可正常导入并通过 SQLAlchemy 元数据生成 DDL
2. serialize_team / serialize_final_state 输出 JSON 可序列化
"""

import json

from sim.pokemon import Pokemon
from sim.skill import Skill
from sim.types import Type, SkillCategory
from sim.battle_state import BattleState
from sim.battle_log_capture import serialize_team, serialize_final_state


def _make_team():
    sk = Skill(name="打击", skill_type=Type.NORMAL, category=SkillCategory.PHYSICAL,
               power=80, energy_cost=3)
    p1 = Pokemon(name="测试一", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                 sp_attack=60, sp_defense=70, speed=80, ability="对流", skills=[sk])
    p2 = Pokemon(name="测试二", pokemon_type=Type.WATER, hp=120, attack=70, defense=80,
                 sp_attack=70, sp_defense=80, speed=70, skills=[sk])
    return [p1, p2]


def test_serialize_team_shape():
    team = _make_team()
    data = serialize_team(team)
    assert len(data) == 2
    assert data[0]["name"] == "测试一"
    assert data[0]["ability"] == "对流"
    assert data[0]["skills"][0]["name"] == "打击"
    assert data[0]["stats"]["hp"] == 100
    # JSON 可序列化
    json.dumps(data, ensure_ascii=False)


def test_serialize_final_state_shape():
    team_a = _make_team()
    team_b = _make_team()
    state = BattleState(team_a=team_a, team_b=team_b)
    team_a[0].current_hp = 30
    team_b[1].current_hp = 0
    snap = serialize_final_state(state)
    assert snap["lives_a"] == 4
    assert snap["team_a"][0]["hp"] == 30
    assert snap["team_b"][1]["hp"] == 0
    json.dumps(snap, ensure_ascii=False)


def test_battle_log_record_model_loads():
    from sim.data_store import BattleLogRecord, Base
    # 字段存在
    assert hasattr(BattleLogRecord, "team_a_lineup")
    assert hasattr(BattleLogRecord, "log_text")
    # 表已注册到 metadata
    assert "battle_log_records" in Base.metadata.tables
