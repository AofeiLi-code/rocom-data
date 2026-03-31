"""
NRC_SIM — 洛克王国战斗模拟器
"""

from sim.types import Type, SkillCategory, StatusType, StatType, Weather
from sim.skill import Skill
from sim.pokemon import Pokemon
from sim.battle_state import BattleState
from sim.damage_calc import calculate_damage
from sim.counter_system import resolve_counter, CounterResult
from sim.battle_engine import BattleEngine, get_actions, execute_full_turn, check_winner, auto_switch

__version__ = "0.2.0"
__all__ = [
    "Type", "SkillCategory", "StatusType", "StatType", "Weather",
    "Skill", "Pokemon", "BattleState",
    "calculate_damage", "resolve_counter", "CounterResult",
    "BattleEngine", "get_actions", "execute_full_turn", "check_winner", "auto_switch",
]
