"""C-group 特性单元测试：对流 / 石头大餐 / 慢热型 / 捉迷藏 / 陨落 / 泛音列 / 预警 / 哨兵"""

from sim.pokemon import Pokemon
from sim.skill import Skill
from sim.types import Type, SkillCategory
from sim.battle_state import BattleState
from sim.battle_engine import BattleEngine
from sim.mark_system import TeamMark, MarkType
from sim.ability_engine import _ability_hooks as h


def _basic_skill():
    return Skill(name="打击", skill_type=Type.NORMAL, category=SkillCategory.PHYSICAL,
                 power=80, energy_cost=3)


def test_dui_liu_negation():
    s = Skill(name="水柱", skill_type=Type.WATER, category=SkillCategory.PHYSICAL,
              power=80, energy_cost=3)
    p1 = Pokemon(name="利灯鱼", pokemon_type=Type.WATER, hp=100, attack=80, defense=70,
                 sp_attack=60, sp_defense=70, speed=80, ability="对流", skills=[s])
    p2 = Pokemon(name="测试", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                 sp_attack=60, sp_defense=70, speed=80, skills=[s])
    state = BattleState(team_a=[p1], team_b=[p2])
    state.set_mark("a", TeamMark(MarkType.WET, 2))
    engine = BattleEngine(state)
    cost = engine._get_effective_energy_cost(s, "a")
    # 湿润 -2 → 对流取反 +2 → 3+2 = 5
    assert cost == 5, f"对流 expected 5, got {cost}"


def test_slow_heat_init_energy_zero():
    sk = _basic_skill()
    slow = Pokemon(name="瞌睡王", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                   sp_attack=60, sp_defense=70, speed=80, ability="慢热型", skills=[sk])
    assert slow.energy == 0


def test_slow_heat_counter_and_swap_in():
    sk = _basic_skill()
    defense_sk = Skill(name="防御", skill_type=Type.NORMAL, category=SkillCategory.DEFENSE,
                       power=0, energy_cost=1, damage_reduction=0.5)
    slow = Pokemon(name="瞌睡王", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                   sp_attack=60, sp_defense=70, speed=80, ability="慢热型", skills=[sk])
    ally = Pokemon(name="队友", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                   sp_attack=60, sp_defense=70, speed=80, skills=[defense_sk])
    target = Pokemon(name="敌方", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                     sp_attack=60, sp_defense=70, speed=80, skills=[sk])
    state = BattleState(team_a=[ally, slow], team_b=[target])
    engine = BattleEngine(state, verbose=False)
    for _ in range(3):
        h.on_use_defense_skill(state, engine, ally, "a")
    assert state.ability_counters.get("slow_heat_a") == 2  # capped
    assert slow.energy == 0
    engine._apply_switch("a", 1)
    assert slow.energy == 10  # 5 × 2
    assert state.ability_counters["slow_heat_a"] == 0


def test_hideseek_extra_cost():
    sk = _basic_skill()
    freeze_skill = Skill(name="冻结术", skill_type=Type.ICE, category=SkillCategory.STATUS,
                         power=0, energy_cost=2, freeze_stacks=3)
    mao = Pokemon(name="大耳帽兜", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                  sp_attack=80, sp_defense=70, speed=80, ability="捉迷藏",
                  skills=[freeze_skill])
    target = Pokemon(name="敌方", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                     sp_attack=60, sp_defense=70, speed=80, skills=[sk])
    state = BattleState(team_a=[mao], team_b=[target])
    engine = BattleEngine(state, verbose=False)
    engine._apply_status_skill(mao, target, freeze_skill)
    assert target.hideseek_freeze_active
    assert target.extra_energy_cost == 1
    cost = engine._get_effective_energy_cost(sk, "b")
    assert cost == 4  # 3 + 1


def test_hideseek_clears_when_freeze_gone():
    sk = _basic_skill()
    freeze_skill = Skill(name="冻结术", skill_type=Type.ICE, category=SkillCategory.STATUS,
                         power=0, energy_cost=2, freeze_stacks=3)
    mao = Pokemon(name="大耳帽兜", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                  sp_attack=80, sp_defense=70, speed=80, ability="捉迷藏",
                  skills=[freeze_skill])
    target = Pokemon(name="敌方", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                     sp_attack=60, sp_defense=70, speed=80, skills=[sk])
    state = BattleState(team_a=[mao], team_b=[target])
    engine = BattleEngine(state, verbose=False)
    engine._apply_status_skill(mao, target, freeze_skill)
    target.freeze_stacks = 0
    h.on_turn_end(state, engine)
    assert not target.hideseek_freeze_active
    assert target.extra_energy_cost == 0


def test_falling_star_skips_burn_damage():
    sk = _basic_skill()
    fall = Pokemon(name="落陨星兔", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                   sp_attack=60, sp_defense=70, speed=80, ability="陨落", skills=[sk])
    victim = Pokemon(name="受害者", pokemon_type=Type.NORMAL, hp=100, attack=80,
                     defense=70, sp_attack=60, sp_defense=70, speed=80, skills=[sk])
    victim.burn_stacks = 4
    state = BattleState(team_a=[fall], team_b=[victim])
    engine = BattleEngine(state, verbose=False)
    hp_before = victim.current_hp
    engine._turn_end_effects()
    assert victim.current_hp == hp_before  # 烧伤伤害被跳过
    assert victim.burn_stacks == 2  # 层数仍衰减


def test_yujing_speed_bonus():
    sk = _basic_skill()
    strong_skill = Skill(name="超杀", skill_type=Type.NORMAL,
                         category=SkillCategory.PHYSICAL, power=200, energy_cost=3)
    warn = Pokemon(name="黑猫巫师", pokemon_type=Type.PSYCHIC, hp=50, attack=60, defense=50,
                   sp_attack=80, sp_defense=70, speed=80, ability="预警", skills=[sk])
    warn.current_hp = 30
    killer = Pokemon(name="强敌", pokemon_type=Type.NORMAL, hp=100, attack=200, defense=70,
                     sp_attack=200, sp_defense=70, speed=70, skills=[strong_skill])
    state = BattleState(team_a=[warn], team_b=[killer])
    engine = BattleEngine(state, verbose=False)
    h.on_turn_start(state, engine)
    assert warn.temp_speed_bonus == 50.0


def test_yujing_no_trigger_when_safe():
    sk = _basic_skill()
    weak_skill = Skill(name="软击", skill_type=Type.NORMAL,
                       category=SkillCategory.PHYSICAL, power=10, energy_cost=2)
    warn = Pokemon(name="黑猫巫师", pokemon_type=Type.PSYCHIC, hp=200, attack=60, defense=50,
                   sp_attack=80, sp_defense=70, speed=80, ability="预警", skills=[sk])
    weak = Pokemon(name="弱敌", pokemon_type=Type.NORMAL, hp=100, attack=20, defense=70,
                   sp_attack=20, sp_defense=70, speed=70, skills=[weak_skill])
    state = BattleState(team_a=[warn], team_b=[weak])
    engine = BattleEngine(state, verbose=False)
    h.on_turn_start(state, engine)
    assert warn.temp_speed_bonus == 0.0


def test_shaobing_force_switch():
    sk = _basic_skill()
    strong_skill = Skill(name="超杀", skill_type=Type.NORMAL,
                         category=SkillCategory.PHYSICAL, power=200, energy_cost=3)
    sent = Pokemon(name="优优", pokemon_type=Type.NORMAL, hp=50, attack=60, defense=50,
                   sp_attack=70, sp_defense=70, speed=80, ability="哨兵", skills=[sk])
    sent.current_hp = 30
    backup = Pokemon(name="后备", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                     sp_attack=60, sp_defense=70, speed=80, skills=[sk])
    killer = Pokemon(name="强敌", pokemon_type=Type.NORMAL, hp=100, attack=200, defense=70,
                     sp_attack=200, sp_defense=70, speed=70, skills=[strong_skill])
    state = BattleState(team_a=[sent, backup], team_b=[killer])
    engine = BattleEngine(state, verbose=False)
    h.on_turn_start(state, engine)
    assert sent.sentinel_must_switch
    engine._maybe_sentinel_escape("a")
    assert state.current_a == 1
    assert not sent.sentinel_must_switch


def test_shaobing_no_switch_when_last():
    sk = _basic_skill()
    strong_skill = Skill(name="超杀", skill_type=Type.NORMAL,
                         category=SkillCategory.PHYSICAL, power=200, energy_cost=3)
    sent = Pokemon(name="优优", pokemon_type=Type.NORMAL, hp=50, attack=60, defense=50,
                   sp_attack=70, sp_defense=70, speed=80, ability="哨兵", skills=[sk])
    sent.current_hp = 30
    killer = Pokemon(name="强敌", pokemon_type=Type.NORMAL, hp=100, attack=200, defense=70,
                     sp_attack=200, sp_defense=70, speed=70, skills=[strong_skill])
    state = BattleState(team_a=[sent], team_b=[killer])
    engine = BattleEngine(state, verbose=False)
    h.on_turn_start(state, engine)
    assert sent.sentinel_must_switch
    engine._maybe_sentinel_escape("a")
    assert state.current_a == 0  # 仍为唯一存活，不脱离
    assert not sent.sentinel_must_switch  # flag 仍被清


def test_fanyin_extra_cost():
    sk = _basic_skill()
    status_sk = Skill(name="聒噪", skill_type=Type.NORMAL, category=SkillCategory.STATUS,
                      power=0, energy_cost=1)
    fy = Pokemon(name="号儿鱼", pokemon_type=Type.WATER, hp=100, attack=70, defense=60,
                 sp_attack=70, sp_defense=60, speed=80, ability="泛音列",
                 skills=[status_sk])
    target = Pokemon(name="敌方", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                     sp_attack=60, sp_defense=70, speed=80, skills=[sk])
    state = BattleState(team_a=[fy], team_b=[target])
    engine = BattleEngine(state, verbose=False)
    h.on_use_status_skill(state, engine, fy, target, status_sk, "a")
    assert target.quiet_debuff_turns == 3
    assert target.quiet_debuff_extra == 3
    cost = engine._get_effective_energy_cost(sk, "b")
    assert cost == 6  # 3 + 3


def test_stone_meal_pays_with_hp():
    stoneskill = Skill(name="岩崩", skill_type=Type.GROUND,
                       category=SkillCategory.PHYSICAL, power=80, energy_cost=4)
    sk = _basic_skill()
    ami = Pokemon(name="阿米亚特", pokemon_type=Type.GROUND, hp=100, attack=80, defense=70,
                  sp_attack=60, sp_defense=70, speed=80, ability="石头大餐",
                  skills=[stoneskill])
    ami.energy = 1
    target = Pokemon(name="敌方", pokemon_type=Type.NORMAL, hp=100, attack=80, defense=70,
                     sp_attack=60, sp_defense=70, speed=80, skills=[sk])
    state = BattleState(team_a=[ami], team_b=[target])
    engine = BattleEngine(state, verbose=False)
    hp_before = ami.current_hp
    engine._execute_action("a", (0,), "b", (-1,), is_first=True)
    # 缺 3 能量 × 5% HP = 15 HP
    assert ami.current_hp == hp_before - 15
    assert ami.energy == 0
