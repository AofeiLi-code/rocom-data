"""
NRC_SIM 测试套件 v2 — 新伤害公式 + 天气系统
"""

import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.types import Type, SkillCategory, StatusType, Weather
from sim.skill import Skill
from sim.pokemon import Pokemon
from sim.battle_state import BattleState
from sim.damage_calc import calculate_damage
from sim.counter_system import resolve_counter
from sim.battle_engine import BattleEngine


# ============================================================
# 辅助
# ============================================================
def make_pokemon(name="测试精灵", ptype=Type.NORMAL,
                 hp=1000, atk=400, dfn=300, spatk=400, spdef=300, spd=350,
                 skills=None):
    return Pokemon(
        name=name, pokemon_type=ptype,
        hp=hp, attack=atk, defense=dfn,
        sp_attack=spatk, sp_defense=spdef,
        speed=spd, skills=skills or [],
    )


def make_skill(name="普攻", power=100, energy=3, stype=Type.NORMAL,
               category=SkillCategory.PHYSICAL, **kwargs):
    return Skill(
        name=name, skill_type=stype, category=category,
        power=power, energy_cost=energy, **kwargs,
    )


# ============================================================
# 测试 1: 新伤害公式
# ============================================================
def test_damage_basic():
    """基础伤害: (atk/def) * 0.9 * power * 能力等级(1) * 无STAB * 无克制"""
    # 火系精灵用水系物攻技能 → 无STAB
    attacker = make_pokemon(ptype=Type.FIRE, atk=400)
    defender = make_pokemon(ptype=Type.NORMAL, dfn=300)
    skill = make_skill(power=100, stype=Type.WATER, category=SkillCategory.PHYSICAL)

    dmg = calculate_damage(attacker, defender, skill)
    # (400/300) * 0.9 * (100*1 + 0) * 1.0 * 1.0 * 1.0 * 1.0 * 1.0 = 120.0 → 120
    expected = int((400 / 300) * 0.9 * 100)
    assert dmg == expected, f"基础: 期望 {expected}, 实际 {dmg}"
    print(f"  [PASS] 基础伤害(无buff): {dmg} == {expected}")


def test_damage_stab():
    """本系加成 1.5x"""
    attacker = make_pokemon(ptype=Type.FIRE, spatk=400)
    defender = make_pokemon(spdef=300)
    skill = make_skill(power=100, stype=Type.FIRE, category=SkillCategory.MAGICAL)

    dmg = calculate_damage(attacker, defender, skill)
    expected = int((400 / 300) * 0.9 * 100 * 1.5)
    assert dmg == expected, f"STAB: 期望 {expected}, 实际 {dmg}"
    print(f"  [PASS] STAB: {dmg} == {expected}")


def test_damage_effectiveness():
    """属性克制 2x"""
    attacker = make_pokemon(spatk=400)
    defender = make_pokemon(ptype=Type.GRASS, spdef=300)
    skill = make_skill(power=100, stype=Type.FIRE, category=SkillCategory.MAGICAL)

    dmg = calculate_damage(attacker, defender, skill)
    expected = int((400 / 300) * 0.9 * 100 * 2.0)
    assert dmg == expected, f"克制: 期望 {expected}, 实际 {dmg}"
    print(f"  [PASS] 克制(火→草 2x): {dmg} == {expected}")


def test_damage_ability_level():
    """能力等级: 攻击方有 buff + 防御方有 debuff"""
    attacker = make_pokemon(ptype=Type.FIRE, atk=400)
    attacker.atk_boost = 0.5  # 我方攻击提升 50%
    defender = make_pokemon(ptype=Type.NORMAL, dfn=300)
    defender.def_reduce = 0.3  # 敌方防御降低 30%
    skill = make_skill(power=100, stype=Type.WATER, category=SkillCategory.PHYSICAL)

    dmg = calculate_damage(attacker, defender, skill)
    # 能力等级 = (1 + 0.5 + 0.3) / (1 + 0 + 0) = 1.8
    ability_level = (1 + 0.5 + 0.3) / 1.0
    expected = int((400 / 300) * 0.9 * 100 * ability_level)
    assert dmg == expected, f"能力等级: 期望 {expected}, 实际 {dmg}"
    print(f"  [PASS] 能力等级(1.8x): {dmg} == {expected}")


def test_damage_ability_level_debuffed():
    """能力等级: 攻击方被 debuff + 防御方有 buff"""
    attacker = make_pokemon(ptype=Type.FIRE, atk=400)
    attacker.atk_reduce = 0.2  # 我方攻击降低 20%
    defender = make_pokemon(ptype=Type.NORMAL, dfn=300)
    defender.def_boost = 0.5   # 敌方防御提升 50%
    skill = make_skill(power=100, stype=Type.WATER, category=SkillCategory.PHYSICAL)

    dmg = calculate_damage(attacker, defender, skill)
    # 能力等级 = (1 + 0 + 0) / (1 + 0.2 + 0.5) = 1/1.7
    ability_level = 1.0 / (1 + 0.2 + 0.5)
    expected = int((400 / 300) * 0.9 * 100 * ability_level)
    assert dmg == expected, f"被debuff: 期望 {expected}, 实际 {dmg}"
    print(f"  [PASS] 能力等级(被debuff): {dmg} == {expected}")


def test_damage_counter_power_mult():
    """应对倍率"""
    attacker = make_pokemon(ptype=Type.FIRE, atk=400)  # 火系，技能水系 → 无STAB
    defender = make_pokemon(dfn=300)
    skill = make_skill(power=100, stype=Type.WATER, category=SkillCategory.PHYSICAL)

    dmg = calculate_damage(attacker, defender, skill, counter_power_mult=2.0)
    # 有效威力 = 100 * 2.0 + 0 = 200
    expected = int((400 / 300) * 0.9 * 200)
    assert dmg == expected, f"应对倍率: 期望 {expected}, 实际 {dmg}"
    print(f"  [PASS] 应对倍率(2x): {dmg} == {expected}")


def test_damage_power_bonus():
    """威力加成"""
    attacker = make_pokemon(ptype=Type.FIRE, atk=400)
    attacker.power_bonus = 40  # 威力加成 +40
    defender = make_pokemon(dfn=300)
    skill = make_skill(power=100, stype=Type.WATER, category=SkillCategory.PHYSICAL)

    dmg = calculate_damage(attacker, defender, skill)
    # 有效威力 = 100 * 1.0 + 40 = 140
    expected = int((400 / 300) * 0.9 * 140)
    assert dmg == expected, f"威力加成: 期望 {expected}, 实际 {dmg}"
    print(f"  [PASS] 威力加成(+40): {dmg} == {expected}")


def test_damage_multi_hit():
    """连击: 单次伤害 × hit_count"""
    attacker = make_pokemon(ptype=Type.FIRE, atk=400)
    defender = make_pokemon(dfn=300)
    skill = make_skill(power=30, stype=Type.WATER, category=SkillCategory.PHYSICAL, hit_count=3)

    dmg = calculate_damage(attacker, defender, skill)
    expected = int((400 / 300) * 0.9 * 30 * 3)
    assert dmg == expected, f"连击: 期望 {expected}, 实际 {dmg}"
    print(f"  [PASS] 3连击: {dmg} == {expected}")


def test_damage_reduction():
    """减伤（多个乘算）"""
    attacker = make_pokemon(ptype=Type.FIRE, atk=400)  # 火系，技能水系 → 无STAB
    defender = make_pokemon(dfn=300)
    skill = make_skill(power=100, stype=Type.WATER, category=SkillCategory.PHYSICAL)

    dmg = calculate_damage(attacker, defender, skill, damage_reductions=[0.5, 0.3])
    # 减伤系数 = (1-0.5) * (1-0.3) = 0.35
    base = (400 / 300) * 0.9 * 100
    expected = int(base * 0.5 * 0.7)
    assert dmg == expected, f"减伤: 期望 {expected}, 实际 {dmg}"
    print(f"  [PASS] 多重减伤(50%+30%): {dmg} == {expected}")


def test_damage_rain_water():
    """雨天水系技能威力 +50%"""
    attacker = make_pokemon(ptype=Type.FIRE, spatk=400)
    defender = make_pokemon(spdef=300)
    skill = make_skill(power=100, stype=Type.WATER, category=SkillCategory.MAGICAL)

    dmg_normal = calculate_damage(attacker, defender, skill)
    dmg_rain = calculate_damage(attacker, defender, skill, weather=Weather.RAIN)

    expected_rain = int((400 / 300) * 0.9 * 100 * 1.5)
    assert dmg_rain == expected_rain, f"雨天: 期望 {expected_rain}, 实际 {dmg_rain}"
    assert dmg_rain > dmg_normal, "雨天水系伤害应 > 正常"
    print(f"  [PASS] 雨天水系(+50%): {dmg_normal} → {dmg_rain}")


def test_damage_rain_fire():
    """雨天非水系技能不受影响"""
    attacker = make_pokemon(spatk=400)
    defender = make_pokemon(spdef=300)
    skill = make_skill(power=100, stype=Type.FIRE, category=SkillCategory.MAGICAL)

    dmg_normal = calculate_damage(attacker, defender, skill)
    dmg_rain = calculate_damage(attacker, defender, skill, weather=Weather.RAIN)

    assert dmg_normal == dmg_rain, f"雨天火系应不变: {dmg_normal} vs {dmg_rain}"
    print(f"  [PASS] 雨天火系不变: {dmg_normal} == {dmg_rain}")


def test_damage_physical_vs_magical():
    """物攻/魔攻由技能 category 决定"""
    attacker = make_pokemon(atk=500, spatk=200)
    defender = make_pokemon(dfn=300, spdef=100)

    phys = make_skill(power=100, category=SkillCategory.PHYSICAL, stype=Type.FIRE)
    magi = make_skill(power=100, category=SkillCategory.MAGICAL, stype=Type.FIRE)

    dmg_p = calculate_damage(attacker, defender, phys)
    dmg_m = calculate_damage(attacker, defender, magi)

    # 物攻: 500/300 * 0.9 * 100 = 150
    # 魔攻: 200/100 * 0.9 * 100 = 180
    expected_p = int((500 / 300) * 0.9 * 100)
    expected_m = int((200 / 100) * 0.9 * 100)
    assert dmg_p == expected_p, f"物攻: 期望 {expected_p}, 实际 {dmg_p}"
    assert dmg_m == expected_m, f"魔攻: 期望 {expected_m}, 实际 {dmg_m}"
    print(f"  [PASS] 物/魔攻由category决定: 物={dmg_p} 魔={dmg_m}")


# ============================================================
# 测试 2: 天气系统
# ============================================================
def test_weather_snow():
    """雪天：每回合所有精灵 +2 冻结层"""
    p1 = make_pokemon("冰人", skills=[make_skill()])
    p2 = make_pokemon("靶子", skills=[make_skill()])

    state = BattleState(team_a=[p1], team_b=[p2])
    state.weather = Weather.SNOW
    state.weather_turns = 3

    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    assert p1.freeze_stacks == 2, f"A冻结: 期望 2, 实际 {p1.freeze_stacks}"
    assert p2.freeze_stacks == 2, f"B冻结: 期望 2, 实际 {p2.freeze_stacks}"
    assert state.weather_turns == 2, f"天气剩余: 期望 2, 实际 {state.weather_turns}"
    print(f"  [PASS] 雪天: 双方各+2冻结, 剩余{state.weather_turns}回合")


def test_weather_sandstorm():
    """沙暴：地系技能能耗减半"""
    ground_skill = make_skill("地刺", power=80, energy=6, stype=Type.GROUND,
                              category=SkillCategory.PHYSICAL)
    water_skill = make_skill("水枪", power=80, energy=4, stype=Type.WATER,
                             category=SkillCategory.MAGICAL)

    p1 = make_pokemon("地系", skills=[ground_skill, water_skill])
    p2 = make_pokemon("靶子", skills=[make_skill()])

    state = BattleState(team_a=[p1], team_b=[p2])
    state.weather = Weather.SANDSTORM
    state.weather_turns = 5

    engine = BattleEngine(state)

    # 地系技能能耗 6 → 3
    assert engine._get_effective_energy_cost(ground_skill) == 3
    # 水系技能不受影响
    assert engine._get_effective_energy_cost(water_skill) == 4
    print(f"  [PASS] 沙暴: 地系6→3, 水系4→4")


def test_weather_duration():
    """天气持续 8 回合后消散"""
    p1 = make_pokemon(skills=[make_skill()])
    p2 = make_pokemon(skills=[make_skill()])

    state = BattleState(team_a=[p1], team_b=[p2])
    state.weather = Weather.RAIN
    state.weather_turns = 1  # 只剩 1 回合

    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    assert state.weather == Weather.NONE, f"天气应消散: 实际 {state.weather}"
    assert state.weather_turns == 0
    print(f"  [PASS] 天气消散: {state.weather} turns={state.weather_turns}")


# ============================================================
# 测试 3: 战斗回合（保留原有）
# ============================================================
def test_full_turn_basic():
    """完整回合执行"""
    s1 = make_skill("火球", 100, 3, Type.FIRE, SkillCategory.MAGICAL)
    s2 = make_skill("水枪", 80, 2, Type.WATER, SkillCategory.MAGICAL)

    p1 = make_pokemon("火精灵", Type.FIRE, 1000, 400, 300, 450, 300, 400, [s1])
    p2 = make_pokemon("水精灵", Type.WATER, 1000, 350, 300, 400, 350, 350, [s2])

    state = BattleState(team_a=[p1], team_b=[p2])
    engine = BattleEngine(state)
    engine.execute_turn((0,), (0,))

    assert p1.current_hp < 1000 or p2.current_hp < 1000
    print(f"  [PASS] 完整回合: A HP={p1.current_hp}, B HP={p2.current_hp}")


def test_gather_energy():
    """汇合聚能"""
    p1 = make_pokemon(skills=[make_skill(energy=5)])
    p2 = make_pokemon(skills=[make_skill(energy=5)])
    p1.energy = 3
    p2.energy = 3

    state = BattleState(team_a=[p1], team_b=[p2])
    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    assert p1.energy == 8 and p2.energy == 8
    print(f"  [PASS] 聚能: A={p1.energy}, B={p2.energy}")


def test_dot_damage():
    """烧伤：-2% × 层数，然后层数减半"""
    p1 = make_pokemon("烧伤的", hp=1000, skills=[make_skill()])
    p2 = make_pokemon(skills=[make_skill()])
    p1.burn_stacks = 4

    state = BattleState(team_a=[p1], team_b=[p2])
    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    # 烧伤伤害 = 1000 * 0.02 * 4 = 80
    # 烧伤后层数减半: 4 → 2
    expected_hp = 1000 - 80
    assert p1.current_hp == expected_hp, f"烧伤HP: 期望 {expected_hp}, 实际 {p1.current_hp}"
    assert p1.burn_stacks == 2, f"烧伤层数: 期望 2, 实际 {p1.burn_stacks}"
    print(f"  [PASS] 烧伤(4层): HP {1000}→{p1.current_hp}, 层数 4→{p1.burn_stacks}")


def test_poison_damage():
    """中毒：-3% × 层数，不衰减"""
    p1 = make_pokemon("中毒的", hp=1000, skills=[make_skill()])
    p2 = make_pokemon(skills=[make_skill()])
    p1.poison_stacks = 3

    state = BattleState(team_a=[p1], team_b=[p2])
    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    # 中毒伤害 = 1000 * 0.03 * 3 = 90
    expected_hp = 1000 - 90
    assert p1.current_hp == expected_hp, f"中毒HP: 期望 {expected_hp}, 实际 {p1.current_hp}"
    assert p1.poison_stacks == 3, "中毒层数不应衰减"
    print(f"  [PASS] 中毒(3层): HP {1000}→{p1.current_hp}, 层数不变={p1.poison_stacks}")


def test_parasite():
    """寄生：被寄生者 -8%，寄生者在场回复"""
    p1 = make_pokemon("寄生者", hp=1000, skills=[make_skill()])
    p1.current_hp = 500  # 半血
    p2 = make_pokemon("被寄生", hp=1000, skills=[make_skill()])
    p2.parasited_by = "寄生者"

    state = BattleState(team_a=[p1], team_b=[p2])
    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    # 寄生伤害 = 1000 * 0.08 = 80
    expected_victim = 1000 - 80
    expected_owner = 500 + 80  # 寄生者在场，回复等量
    assert p2.current_hp == expected_victim, f"被寄生HP: 期望 {expected_victim}, 实际 {p2.current_hp}"
    assert p1.current_hp == expected_owner, f"寄生者HP: 期望 {expected_owner}, 实际 {p1.current_hp}"
    print(f"  [PASS] 寄生: 被寄生 {1000}→{p2.current_hp}, 寄生者 {500}→{p1.current_hp}")


def test_parasite_off_field():
    """寄生：寄生者不在场则不回复"""
    owner = make_pokemon("寄生者", hp=1000, skills=[make_skill()])
    owner.current_hp = 500
    reserve = make_pokemon("替补A", hp=1000, skills=[make_skill()])
    victim = make_pokemon("被寄生", hp=1000, skills=[make_skill()])
    victim.parasited_by = "寄生者"

    # A队: [寄生者, 替补A]，当前出战 = 替补A (index=1)
    state = BattleState(team_a=[owner, reserve], team_b=[victim], current_a=1)
    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    expected_victim = 1000 - 80
    assert victim.current_hp == expected_victim, f"被寄生HP: {victim.current_hp}"
    assert owner.current_hp == 500, f"寄生者不应回复: {owner.current_hp}"
    print(f"  [PASS] 寄生(不在场): 被寄生→{victim.current_hp}, 寄生者HP不变={owner.current_hp}")


def test_freeze_threshold():
    """冻结：HP < 冻结条则死亡"""
    p1 = make_pokemon("冻结的", hp=1200, skills=[make_skill()])
    p1.freeze_stacks = 6  # 冻结条 = 1200 * 6/12 = 600
    p1.current_hp = 500   # 500 < 600 → 死亡
    p2 = make_pokemon(skills=[make_skill()])

    state = BattleState(team_a=[p1], team_b=[p2])
    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    assert p1.is_fainted, f"应该冻毙: status={p1.status}, hp={p1.current_hp}"
    print(f"  [PASS] 冻结(6层): HP 500 < 冻结条 600 → 冻毙")


def test_freeze_safe():
    """冻结：HP >= 冻结条则存活"""
    p1 = make_pokemon("冻结的", hp=1200, skills=[make_skill()])
    p1.freeze_stacks = 3  # 冻结条 = 1200 * 3/12 = 300
    p1.current_hp = 400   # 400 >= 300 → 存活
    p2 = make_pokemon(skills=[make_skill()])

    state = BattleState(team_a=[p1], team_b=[p2])
    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    assert not p1.is_fainted, f"不应死亡: status={p1.status}, hp={p1.current_hp}"
    print(f"  [PASS] 冻结(3层): HP 400 >= 冻结条 300 → 存活")


def test_burn_decay():
    """烧伤层数衰减到 0"""
    p1 = make_pokemon("烧伤的", hp=1000, skills=[make_skill()])
    p2 = make_pokemon(skills=[make_skill()])
    p1.burn_stacks = 1  # 1层 → 减半 → 0

    state = BattleState(team_a=[p1], team_b=[p2])
    engine = BattleEngine(state)
    engine.execute_turn((-1,), (-1,))

    # 伤害 = 1000 * 0.02 * 1 = 20, 层数 1//2 = 0
    assert p1.current_hp == 980, f"HP: {p1.current_hp}"
    assert p1.burn_stacks == 0, f"层数应为0: {p1.burn_stacks}"
    print(f"  [PASS] 烧伤衰减: 1层→0层, HP {1000}→{p1.current_hp}")


def test_auto_switch():
    """自动换人"""
    p1 = make_pokemon("主力", hp=100, skills=[make_skill()])
    p2 = make_pokemon("替补", skills=[make_skill()])
    p1.current_hp = 1

    enemy = make_pokemon("敌人", atk=9999, skills=[make_skill(power=999)])

    state = BattleState(team_a=[p1, p2], team_b=[enemy])
    engine = BattleEngine(state)
    engine.execute_turn((-1,), (0,))

    assert state.current_a == 1
    print(f"  [PASS] 自动换人: current_a={state.current_a}")


# ============================================================
# 测试 4: 数据加载
# ============================================================
def test_data_loading():
    """数据加载验证"""
    from sim.skill_db import load_skills, get_skill
    from sim.pokemon_db import load_pokemon_db, get_pokemon

    skills = load_skills()
    assert len(skills) > 0
    print(f"  [PASS] 技能数据库: {len(skills)} 个技能")

    load_pokemon_db()
    data = get_pokemon("千棘盔")
    assert data is not None
    print(f"  [PASS] 精灵数据库: 千棘盔 HP={data['生命值']}")

    skill = get_skill("水刃")
    assert skill.power > 0
    print(f"  [PASS] 技能解析: {skill.name} 威力={skill.power}")


# ============================================================
# 测试 5: 完整对战
# ============================================================
def test_full_battle():
    """完整对战（随机 vs 随机）"""
    from sim.team_builder import create_toxic_team, create_wing_team

    state = BattleState(team_a=create_toxic_team(), team_b=create_wing_team())
    engine = BattleEngine(state)

    random.seed(42)
    for _ in range(150):
        winner = engine.check_winner()
        if winner:
            break
        actions_a = engine.get_actions("a")
        actions_b = engine.get_actions("b")
        engine.execute_turn(random.choice(actions_a), random.choice(actions_b))

    winner = winner or engine.check_winner()
    tag = winner.upper() if winner else "平局"
    print(f"  [PASS] 完整对战: {tag} 赢 (回合 {state.turn})")


# ============================================================
# 运行全部
# ============================================================
def main():
    print("=" * 60)
    print("NRC_SIM 战斗引擎测试套件 v2 (新伤害公式)")
    print("=" * 60)

    groups = [
        ("伤害计算(新公式)", [
            test_damage_basic,
            test_damage_stab,
            test_damage_effectiveness,
            test_damage_ability_level,
            test_damage_ability_level_debuffed,
            test_damage_counter_power_mult,
            test_damage_power_bonus,
            test_damage_multi_hit,
            test_damage_reduction,
            test_damage_rain_water,
            test_damage_rain_fire,
            test_damage_physical_vs_magical,
        ]),
        ("天气系统", [
            test_weather_snow,
            test_weather_sandstorm,
            test_weather_duration,
        ]),
        ("战斗回合", [
            test_full_turn_basic,
            test_gather_energy,
            test_auto_switch,
        ]),
        ("异常状态", [
            test_dot_damage,
            test_poison_damage,
            test_parasite,
            test_parasite_off_field,
            test_freeze_threshold,
            test_freeze_safe,
            test_burn_decay,
        ]),
        ("数据加载", [
            test_data_loading,
        ]),
        ("完整对战", [
            test_full_battle,
        ]),
    ]

    total_pass = 0
    total_fail = 0

    for group_name, tests in groups:
        print(f"\n--- {group_name} ---")
        for test_fn in tests:
            try:
                test_fn()
                total_pass += 1
            except Exception as e:
                print(f"  [FAIL] {test_fn.__name__}: {e}")
                total_fail += 1
                import traceback
                traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"结果: {total_pass} 通过, {total_fail} 失败")
    print(f"{'=' * 60}")
    return total_fail == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
