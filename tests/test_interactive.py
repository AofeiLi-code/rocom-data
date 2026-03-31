"""
交互式组队构建器测试

策略：将预设的用户输入序列放入队列，注入到 build_team_interactive 的
_input 参数，验证最终返回的队伍是否符合预期。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import deque
from sim.team_builder_interactive import build_team_interactive
from sim.pokemon_db import load_pokemon_db, get_pokemon
from sim.skill_db import load_skills, get_learnable_skills


# ============================================================
# 测试工具
# ============================================================
def make_input(responses: list):
    """把预设回答做成 _input 函数，耗尽后抛出 AssertionError 方便定位"""
    q = deque(responses)
    def _input():
        if not q:
            raise AssertionError("预设输入已耗尽，流程比预期多调用了一次 input()")
        val = q.popleft()
        return val
    return _input


def silent_print(*args, **kwargs):
    """测试时静默输出"""
    pass


# ============================================================
# 辅助：查询精灵第 N 个可学技能的序号（1-based）
# ============================================================
def skill_idx(pokemon_name: str, skill_name: str) -> str:
    skills = get_learnable_skills(pokemon_name)
    return str(skills.index(skill_name) + 1)


# ============================================================
# 测试 1：完整 6 只精灵，精确名称输入 + 按序号选技能
# ============================================================
def test_full_team_exact_names():
    """精确输入精灵名，按序号选技能，选满 6 只"""
    load_pokemon_db()
    load_skills()

    # 使用 6 只确定存在于 sprites.json 的精灵，每只选前 4 个技能
    pokemon_configs = []
    for pname in ["迪莫", "千棘盔", "影狸", "裘卡", "琉璃水母", "迷迷箱怪"]:
        data = get_pokemon(pname)
        # 找到实际精灵名（可能模糊匹配）
        actual_name = data["名称"] if data else pname
        skills = get_learnable_skills(actual_name)
        # 取前 4 个技能的序号
        chosen_indices = [str(i) for i in range(1, 5)]
        chosen_names = skills[:4]
        pokemon_configs.append((actual_name, chosen_indices, chosen_names))

    # 构造输入序列：每只精灵 = 1次名称输入 + 4次技能序号
    responses = []
    for name, indices, _ in pokemon_configs:
        responses.append(name)      # 精灵名
        responses.extend(indices)   # 4 个技能序号

    team = build_team_interactive("测试队", _input=make_input(responses), _print=silent_print)

    assert len(team) == 6, f"队伍应有 6 只精灵，实际 {len(team)}"
    for i, (pname, _, expected_skills) in enumerate(pokemon_configs):
        p = team[i]
        assert p.name == pname, f"第{i+1}只：期望 {pname}，实际 {p.name}"
        assert len(p.skills) == 4, f"{pname} 应有 4 个技能，实际 {len(p.skills)}"
        actual_skill_names = [s.name for s in p.skills]
        assert actual_skill_names == expected_skills, (
            f"{pname} 技能不符：期望 {expected_skills}，实际 {actual_skill_names}"
        )
    print(f"  [PASS] 完整6只精灵（精确名称+序号选技能）：{[p.name for p in team]}")


# ============================================================
# 测试 2：模糊搜索精灵名 → 选候选序号
# ============================================================
def test_fuzzy_pokemon_search():
    """输入不完整名称触发模糊搜索，从候选列表选序号"""
    load_pokemon_db()
    load_skills()

    # "迪莫" 用 "迪" 搜索，应命中多个候选（迪莫、圣光迪莫等），选序号1
    # 确保 "迪" 搜索至少有一个结果
    from sim.team_builder_interactive import _search_pokemon
    candidates = _search_pokemon("迪")
    assert candidates, "搜索'迪'应有结果"
    first_name = candidates[0]

    first_skills = get_learnable_skills(first_name)
    assert len(first_skills) >= 4, f"{first_name} 技能不足4个"

    # 构造 1 只精灵的输入序列（其余 5 只用迪莫精确输入补全）
    diemo_data = get_pokemon("迪莫")
    diemo_name = diemo_data["名称"]
    diemo_skills = get_learnable_skills(diemo_name)

    responses = (
        ["迪", "1"]              # 模糊搜索"迪"，选第1个候选
        + ["1", "2", "3", "4"]   # 为 first_name 选前4个技能
    )
    # 补齐剩余 5 只（精确名称 + 技能序号）
    for _ in range(5):
        responses += [diemo_name, "1", "2", "3", "4"]

    team = build_team_interactive("模糊搜索队", _input=make_input(responses), _print=silent_print)

    assert len(team) == 6
    assert team[0].name == first_name, f"第1只应为 {first_name}，实际 {team[0].name}"
    print(f"  [PASS] 模糊搜索：'迪' → {first_name}")


# ============================================================
# 测试 3：? 前缀触发搜索
# ============================================================
def test_question_mark_search():
    """? 前缀触发搜索，?关键字 过滤结果"""
    load_pokemon_db()
    load_skills()

    from sim.team_builder_interactive import _search_pokemon
    candidates = _search_pokemon("棘")
    assert candidates, "搜索'棘'应有结果"
    target = candidates[0]
    target_skills = get_learnable_skills(target)
    assert len(target_skills) >= 4

    diemo_data = get_pokemon("迪莫")
    diemo_name = diemo_data["名称"]

    responses = (
        ["?棘", "1"]             # ? 前缀搜索，选第1个
        + ["1", "2", "3", "4"]   # 技能选择
    )
    for _ in range(5):
        responses += [diemo_name, "1", "2", "3", "4"]

    team = build_team_interactive("?搜索队", _input=make_input(responses), _print=silent_print)

    assert len(team) == 6
    assert team[0].name == target, f"第1只应为 {target}，实际 {team[0].name}"
    print(f"  [PASS] ?前缀搜索：'?棘' → {target}")


# ============================================================
# 测试 4：重复选技能时自动跳过，重新选
# ============================================================
def test_duplicate_skill_rejected():
    """重复选同一技能时应被拒绝，再次输入有效序号后继续"""
    load_pokemon_db()
    load_skills()

    diemo_data = get_pokemon("迪莫")
    diemo_name = diemo_data["名称"]
    skills = get_learnable_skills(diemo_name)
    assert len(skills) >= 4

    # 第1只精灵：先选1，再选1（重复，应拒绝），再选2、3、4
    responses_first = [diemo_name, "1", "1", "2", "3", "4"]
    # 剩余5只精灵正常
    responses_rest = []
    for _ in range(5):
        responses_rest += [diemo_name, "1", "2", "3", "4"]

    team = build_team_interactive(
        "重复测试队",
        _input=make_input(responses_first + responses_rest),
        _print=silent_print,
    )

    assert len(team) == 6
    first_pokemon_skills = [s.name for s in team[0].skills]
    # 4 个技能不应有重复
    assert len(set(first_pokemon_skills)) == 4, f"技能有重复: {first_pokemon_skills}"
    # 应选的是 1、2、3、4 号技能（第二次选1被拒绝后选了2）
    assert first_pokemon_skills == skills[:4], (
        f"期望 {skills[:4]}，实际 {first_pokemon_skills}"
    )
    print(f"  [PASS] 重复技能拒绝：{first_pokemon_skills}")


# ============================================================
# 测试 5：Pokemon 对象完整性
# ============================================================
def test_pokemon_fields():
    """构建的 Pokemon 对象六维、特性、属性均正确填充"""
    load_pokemon_db()
    load_skills()

    diemo_data = get_pokemon("迪莫")
    diemo_name = diemo_data["名称"]
    skills = get_learnable_skills(diemo_name)

    responses = [diemo_name, "1", "2", "3", "4"]
    for _ in range(5):
        responses += [diemo_name, "1", "2", "3", "4"]

    team = build_team_interactive("字段测试队", _input=make_input(responses), _print=silent_print)

    p = team[0]
    assert p.name == diemo_name
    assert p.hp > 0,       f"HP 应>0，实际 {p.hp}"
    assert p.attack > 0,   f"物攻 应>0，实际 {p.attack}"
    assert p.sp_attack > 0
    assert p.defense > 0
    assert p.sp_defense > 0
    assert p.speed > 0
    assert p.ability,      f"特性不应为空"
    assert len(p.skills) == 4
    # 六维都是正整数
    for stat_name, val in [("HP", p.hp), ("物攻", p.attack), ("物防", p.defense),
                            ("魔攻", p.sp_attack), ("魔防", p.sp_defense), ("速度", p.speed)]:
        assert isinstance(val, int) and val > 0, f"{stat_name}={val} 异常"
    print(f"  [PASS] Pokemon字段完整：{p.name} HP={p.hp} 物攻={p.attack} 魔攻={p.sp_attack}"
          f" 物防={p.defense} 魔防={p.sp_defense} 速度={p.speed}")


# ============================================================
# 运行全部
# ============================================================
def main():
    print("=" * 50)
    print("  交互式组队构建器测试")
    print("=" * 50)

    tests = [
        ("完整6只精灵（精确名+序号）",  test_full_team_exact_names),
        ("模糊搜索精灵名",              test_fuzzy_pokemon_search),
        ("?前缀触发搜索",               test_question_mark_search),
        ("重复技能拒绝",                test_duplicate_skill_rejected),
        ("Pokemon对象字段完整性",       test_pokemon_fields),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            import traceback
            print(f"  [FAIL] {name}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"  结果：{passed} 通过，{failed} 失败")
    print(f"{'='*50}")
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
