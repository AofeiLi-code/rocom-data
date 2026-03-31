"""
交互式组队构建器

流程（每只精灵）:
  1. 输入精灵名（支持模糊搜索 / ? 前缀触发搜索）
  2. 从可学技能列表中选 4 个（按序号，已选标记 [✓]）
  3. 确认后继续下一只，共 6 只

为保证可测试性，input/print 通过参数注入（默认为内置函数）。
"""

from typing import List, Callable, Optional

from sim.pokemon import Pokemon
from sim.pokemon_db import get_pokemon, get_all_pokemon_names, get_nature, load_pokemon_db
from sim.skill_db import get_skill, get_learnable_skills, load_skills
# build_pokemon 在函数内延迟导入，避免与 team_builder.py 的循环引用

_InputFn = Callable[[], str]
_PrintFn = Callable[..., None]

TEAM_SIZE = 6
SKILL_SLOTS = 4


# ============================================================
# 精灵搜索
# ============================================================
def _search_pokemon(keyword: str) -> List[str]:
    """在所有精灵名中模糊查找，返回包含 keyword 的名称列表（最多 20 条）"""
    all_names = get_all_pokemon_names()
    return [n for n in all_names if keyword in n][:20]


def _select_pokemon(slot: int, _input: _InputFn, _print: _PrintFn) -> str:
    """
    交互式选择一只精灵，返回精灵名。
    输入 '?' 或 '?关键字' 触发模糊搜索；否则直接匹配。
    """
    while True:
        _print(f"\n── 第 {slot} 只精灵 ──")
        _print("输入精灵名（输入 ? 或 ?关键字 可搜索）：", end="")
        raw = _input().strip()

        if not raw:
            _print("  [!] 输入不能为空")
            continue

        # ------ 搜索模式 ------
        if raw.startswith("?"):
            keyword = raw[1:].strip()
            candidates = _search_pokemon(keyword) if keyword else get_all_pokemon_names()[:20]
            if not candidates:
                _print(f"  [!] 未找到包含「{keyword}」的精灵")
                continue
            _print(f"\n  搜索结果（共 {len(candidates)} 条，最多显示 20）：")
            for i, name in enumerate(candidates, 1):
                _print(f"    {i:2}. {name}")
            _print("  输入序号选择（或直接回车重新输入名称）：", end="")
            sel = _input().strip()
            if not sel:
                continue
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(candidates):
                    chosen = candidates[idx]
                    if get_pokemon(chosen):
                        return chosen
                    _print(f"  [!] 精灵「{chosen}」数据不存在")
                else:
                    _print("  [!] 序号超出范围")
            except ValueError:
                _print("  [!] 请输入数字序号")
            continue

        # ------ 精确匹配 ------
        data = get_pokemon(raw)
        if data:
            return data["名称"]

        # ------ 模糊匹配 ------
        candidates = _search_pokemon(raw)
        if not candidates:
            _print(f"  [!] 未找到精灵「{raw}」，请重新输入")
            continue

        if len(candidates) == 1:
            # 唯一候选，直接确认
            _print(f"  → 自动匹配到：{candidates[0]}")
            return candidates[0]

        _print(f"\n  找到 {len(candidates)} 个相关精灵：")
        for i, name in enumerate(candidates, 1):
            _print(f"    {i:2}. {name}")
        _print("  输入序号选择（或直接回车重新输入）：", end="")
        sel = _input().strip()
        if not sel:
            continue
        try:
            idx = int(sel) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
            _print("  [!] 序号超出范围")
        except ValueError:
            _print("  [!] 请输入数字序号")


# ============================================================
# 技能选择
# ============================================================
def _display_skill_list(
    skills: List[str],
    chosen: List[str],
    _print: _PrintFn,
) -> None:
    """以每行 3 列的紧凑格式显示技能列表，已选标记 [✓]"""
    _print(f"\n  可学技能（共 {len(skills)} 个）：")
    cols = 3
    for i, name in enumerate(skills, 1):
        mark = "[✓]" if name in chosen else "   "
        cell = f"  {i:3}. {mark}{name}"
        end = "\n" if i % cols == 0 or i == len(skills) else ""
        _print(cell, end=end)
    if len(skills) % cols != 0:
        _print()  # 补换行


def _select_skills(
    pokemon_name: str,
    _input: _InputFn,
    _print: _PrintFn,
) -> List[str]:
    """
    交互式为精灵选择 4 个技能，返回技能名列表。
    支持：数字序号 / 直接输入技能名。
    """
    learnable = get_learnable_skills(pokemon_name)
    if not learnable:
        _print(f"  [!] 未找到「{pokemon_name}」的可学技能，将使用空技能槽")
        return []

    chosen: List[str] = []

    while len(chosen) < SKILL_SLOTS:
        remaining = SKILL_SLOTS - len(chosen)
        _display_skill_list(learnable, chosen, _print)
        _print(f"\n  已选 ({len(chosen)}/{SKILL_SLOTS})：{' | '.join(chosen) if chosen else '（无）'}")
        _print(f"  选择第 {len(chosen)+1} 个技能（输入序号或技能名）：", end="")
        raw = _input().strip()

        if not raw:
            _print("  [!] 输入不能为空")
            continue

        # 尝试按序号选
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(learnable):
                skill_name = learnable[idx]
                if skill_name in chosen:
                    _print(f"  [!] 「{skill_name}」已选过，请选其他技能")
                else:
                    chosen.append(skill_name)
            else:
                _print(f"  [!] 序号超出范围（1~{len(learnable)}）")
            continue

        # 尝试按名称精确匹配
        if raw in learnable:
            if raw in chosen:
                _print(f"  [!] 「{raw}」已选过")
            else:
                chosen.append(raw)
            continue

        # 模糊匹配技能名
        fuzzy = [n for n in learnable if raw in n]
        if not fuzzy:
            _print(f"  [!] 未找到技能「{raw}」，请重新输入")
        elif len(fuzzy) == 1:
            skill_name = fuzzy[0]
            if skill_name in chosen:
                _print(f"  [!] 「{skill_name}」已选过")
            else:
                _print(f"  → 自动匹配：{skill_name}")
                chosen.append(skill_name)
        else:
            _print(f"  模糊匹配结果：{', '.join(fuzzy[:10])}")
            _print("  请输入更精确的名称或序号")

    return chosen


# ============================================================
# 主入口
# ============================================================
def build_team_interactive(
    team_name: str,
    _input: _InputFn = input,
    _print: _PrintFn = print,
) -> List[Pokemon]:
    """
    交互式组队，返回包含 6 只 Pokemon 的队伍列表。

    Parameters
    ----------
    team_name : 队伍名称（仅用于显示）
    _input    : 输入函数（默认 input，测试时可注入）
    _print    : 输出函数（默认 print，测试时可注入）
    """
    from sim.team_builder import build_pokemon  # 延迟导入，避免循环依赖

    load_pokemon_db()
    load_skills()

    _print(f"\n{'='*50}")
    _print(f"  组建队伍：{team_name}")
    _print(f"  请依次选择 {TEAM_SIZE} 只精灵，每只选 {SKILL_SLOTS} 个技能")
    _print(f"{'='*50}")

    team: List[Pokemon] = []

    for slot in range(1, TEAM_SIZE + 1):
        pokemon_name = _select_pokemon(slot, _input, _print)
        data = get_pokemon(pokemon_name)

        attrs = data.get("属性列表", [data.get("属性", "普通")]) if data else ["普通"]
        type_str = "+".join(attrs)
        total = data.get("种族值总和", 0) if data else 0
        nature_boost  = data.get("性格提升", "?") if data else "?"
        nature_reduce = data.get("性格降低", "?") if data else "?"
        _print(f"\n  ✔ {pokemon_name}  [{type_str}]  种族值总和 {total}"
               f"  性格：{nature_boost}↑ {nature_reduce}↓")

        skill_names = _select_skills(pokemon_name, _input, _print)
        pokemon = build_pokemon(pokemon_name, skill_names)
        team.append(pokemon)

        _print(f"\n  ── 已加入队伍：{pokemon_name}  性格：{nature_boost}↑ {nature_reduce}↓"
               f"  技能：[{', '.join(skill_names)}]")
        _print(f"     HP={pokemon.hp}  物攻={pokemon.attack}  魔攻={pokemon.sp_attack}"
               f"  物防={pokemon.defense}  魔防={pokemon.sp_defense}  速度={pokemon.speed}")

    _print(f"\n{'='*50}")
    _print(f"  队伍「{team_name}」组建完成：")
    for i, p in enumerate(team, 1):
        skill_names = [s.name for s in p.skills]
        nature = get_nature(p.name)
        nature_str = (f"  性格：{nature['提升']}↑{nature['降低']}↓"
                      if nature else "")
        _print(f"  {i}. {p.name:<12}{nature_str}  [{', '.join(skill_names)}]")
    _print(f"{'='*50}\n")

    return team
