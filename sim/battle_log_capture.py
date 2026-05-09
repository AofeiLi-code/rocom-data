"""
战斗日志捕获工具 — 把一场对战的阵容、最终状态、引擎日志
序列化为可写入 BattleLogRecord 的结构。
"""

from typing import List, Dict, Any


def serialize_team(team: list) -> List[Dict[str, Any]]:
    """把一支队伍序列化为 JSON 友好结构（含技能/特性/性格细节）。"""
    out = []
    for p in team:
        skills_info = []
        for sk in getattr(p, "skills", []) or []:
            skills_info.append({
                "name": sk.name,
                "type": getattr(sk.skill_type, "value", str(sk.skill_type)),
                "category": getattr(sk.category, "value", str(sk.category)),
                "power": sk.power,
                "energy_cost": sk.energy_cost,
            })
        out.append({
            "name": p.name,
            "type": getattr(p.pokemon_type, "value", str(p.pokemon_type)),
            "ability": getattr(p, "ability", "") or "",
            "nature": getattr(p, "nature", "") or "",
            "stats": {
                "hp": p.hp,
                "attack": p.attack,
                "defense": p.defense,
                "sp_attack": p.sp_attack,
                "sp_defense": p.sp_defense,
                "speed": p.speed,
            },
            "skills": skills_info,
        })
    return out


def serialize_final_state(state) -> Dict[str, Any]:
    """捕获对战结束时双方残血/能量/异常状态。"""
    def _team_state(team):
        rows = []
        for p in team:
            rows.append({
                "name": p.name,
                "hp": p.current_hp,
                "hp_max": p.hp,
                "energy": getattr(p, "energy", 0),
                "fainted": p.is_fainted,
                "burn": getattr(p, "burn_stacks", 0),
                "poison": getattr(p, "poison_stacks", 0),
                "freeze": getattr(p, "freeze_stacks", 0),
            })
        return rows
    return {
        "turn": state.turn,
        "lives_a": state.lives_a,
        "lives_b": state.lives_b,
        "team_a": _team_state(state.team_a),
        "team_b": _team_state(state.team_b),
    }
