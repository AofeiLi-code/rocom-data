"""
洛克王国战斗模拟器 — 主入口

菜单:
  1. 开始对战        — 从队伍列表各选一支，AI 自战并输出日志
  2. 新建队伍        — 交互式组队并保存到列表
  3. 管理队伍        — 查看详情 / 删除 / 重命名
  4. 批量模拟        — 选两支队伍，跑 N 场，输出胜率统计
  0. 返回
"""

import sys
import os
import random
import time
from typing import List, Optional, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sim.pokemon import Pokemon
from sim.pokemon_db import load_pokemon_db
from sim.skill_db import load_skills, get_learnable_skills
from sim.battle_state import BattleState
from sim.battle_engine import BattleEngine
from sim.team_builder_interactive import build_team_interactive
from sim.team_roster import (
    list_teams, build_team, add_team, delete_team, rename_team, get_team_def
)
from sim.mcts_agent import MCTSAgent

# MCTS 每回合迭代次数（可调整：50 快速 / 100 标准 / 200 强力）
_MCTS_ITERS_BATTLE = 100   # 单局对战
_MCTS_ITERS_BATCH  = 50    # 批量模拟（兼顾速度）

_IMPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "import_images")
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

SEP = "=" * 56
LINE = "─" * 56


# ============================================================
# 显示工具
# ============================================================
def _hp_bar(current: int, maximum: int, width: int = 10) -> str:
    if maximum <= 0:
        return f"[{'?' * width}] ---/---"
    pct = max(0.0, min(100.0, current / maximum * 100))
    filled = int(pct / (100 / width))
    return f"[{'#' * filled}{'.' * (width - filled)}] {current:4}/{maximum}"


def _status_flags(p: Pokemon) -> str:
    parts = []
    if p.burn_stacks:   parts.append(f"烧{p.burn_stacks}")
    if p.poison_stacks: parts.append(f"毒{p.poison_stacks}")
    if p.freeze_stacks: parts.append(f"冻{p.freeze_stacks}")
    return " ".join(parts)


def _print_field(state: BattleState, label_a: str, label_b: str) -> None:
    pa, pb = state.get_current("a"), state.get_current("b")
    weather_str = f"  天气:{state.weather.value}" if state.weather.value != "none" else ""
    print(f"\n{LINE}  回合 {state.turn}{weather_str}")
    print(f"  {label_a}: {pa.name:<10} {_hp_bar(pa.current_hp, pa.hp)}  能量:{pa.energy:2}  {_status_flags(pa)}")
    print(f"  {label_b}: {pb.name:<10} {_hp_bar(pb.current_hp, pb.hp)}  能量:{pb.energy:2}  {_status_flags(pb)}")


def _print_team_summary(label: str, team: List[Pokemon]) -> None:
    print(f"\n  {label}:")
    for p in team:
        s = "FAINTED" if p.is_fainted else f"HP {p.current_hp}/{p.hp}"
        print(f"    {p.name:<12} {s}")


# ============================================================
# 队伍列表显示
# ============================================================
def _print_roster(header: str = "队伍列表") -> None:
    teams = list_teams()
    print(f"\n  {header}（共 {len(teams)} 支）：")
    for i, t in enumerate(teams, 1):
        tag = "[预设]" if t.get("preset") else "[自定]"
        members = "  ".join(m["pokemon"] for m in t["members"])
        print(f"  {i:2}. {tag} {t['name']:<14} {members}")


def _pick_team(prompt: str = "选择队伍序号") -> Optional[str]:
    """显示名册，让用户选一支队伍，返回队伍名；输入 0 取消返回 None"""
    _print_roster()
    teams = list_teams()
    print(f"\n  {prompt}（0 取消）：", end="")
    raw = input().strip()
    if raw == "0" or raw == "":
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(teams):
            return teams[idx]["name"]
    print("  [!] 无效序号")
    return None


# ============================================================
# 核心：单场对战
# ============================================================
def run_battle(
    team_a: List[Pokemon],
    team_b: List[Pokemon],
    label_a: str = "A队",
    label_b: str = "B队",
    verbose: bool = True,
) -> Optional[str]:
    """
    运行一场对战（随机 AI），verbose=True 时实时打印日志。
    返回胜者 "a" / "b" 或 None（平局/超时）。
    """
    state = BattleState(team_a=team_a, team_b=team_b)
    engine = BattleEngine(state, verbose=verbose)

    if verbose:
        print(f"\n{SEP}")
        print(f"  {label_a}  VS  {label_b}")
        skills_a = [s.name for s in team_a[0].skills]
        skills_b = [s.name for s in team_b[0].skills]
        print(f"  先锋: {team_a[0].name}[{', '.join(skills_a)}]")
        print(f"        vs  {team_b[0].name}[{', '.join(skills_b)}]")
        print(SEP)

    agent_a = MCTSAgent("a", label_a, iterations=_MCTS_ITERS_BATTLE)
    agent_b = MCTSAgent("b", label_b, iterations=_MCTS_ITERS_BATTLE)
    history = []

    winner = None
    for _ in range(BattleEngine.MAX_TURNS):
        winner = engine.check_winner()
        if winner:
            break
        if verbose:
            _print_field(state, label_a, label_b)
        snap     = state.deep_copy()
        action_a = agent_a.choose_action(engine)
        action_b = agent_b.choose_action(engine)
        history.append((snap, action_a, action_b))
        engine.execute_turn(action_a, action_b)

    if not winner:
        winner = engine.check_winner()

    # 记录经验并保存
    agent_a.experience_db.record_game(history, winner)
    agent_b.experience_db.record_game(history, winner)
    agent_a.save()
    agent_b.save()

    if verbose:
        tag = f"{label_a} 赢！" if winner == "a" else (f"{label_b} 赢！" if winner == "b" else "平局/超时")
        print(f"\n{SEP}")
        print(f"  结果：{tag}  (共 {state.turn} 回合)")
        _print_team_summary(label_a, team_a)
        _print_team_summary(label_b, team_b)
        print(SEP)

    return winner


# ============================================================
# 批量模拟
# ============================================================
def run_batch(
    factory_a: Callable[[], List[Pokemon]],
    factory_b: Callable[[], List[Pokemon]],
    label_a: str,
    label_b: str,
    n: int,
) -> None:
    results = {"a": 0, "b": 0, "draw": 0}
    total_turns = 0
    t0 = time.time()

    agent_a = MCTSAgent("a", label_a, iterations=_MCTS_ITERS_BATCH)
    agent_b = MCTSAgent("b", label_b, iterations=_MCTS_ITERS_BATCH)

    for i in range(n):
        state = BattleState(team_a=factory_a(), team_b=factory_b())
        engine = BattleEngine(state, verbose=False)
        history = []
        winner = None
        for _ in range(BattleEngine.MAX_TURNS):
            winner = engine.check_winner()
            if winner:
                break
            snap     = state.deep_copy()
            action_a = agent_a.choose_action(engine)
            action_b = agent_b.choose_action(engine)
            history.append((snap, action_a, action_b))
            engine.execute_turn(action_a, action_b)
        if not winner:
            winner = engine.check_winner()
        agent_a.experience_db.record_game(history, winner)
        agent_b.experience_db.record_game(history, winner)
        total_turns += state.turn
        results[winner or "draw"] += 1
        if (i + 1) % max(1, n // 10) == 0:
            print(f"  ... {i+1}/{n}", flush=True)

    agent_a.save()
    agent_b.save()

    elapsed = time.time() - t0
    print(f"\n{SEP}")
    print(f"  批量模拟结果（{n} 场，MCTS×{_MCTS_ITERS_BATCH}）")
    print(f"  {label_a} 胜: {results['a']:4} 场  ({results['a']/n*100:.1f}%)")
    print(f"  {label_b} 胜: {results['b']:4} 场  ({results['b']/n*100:.1f}%)")
    print(f"  平局:     {results['draw']:4} 场  ({results['draw']/n*100:.1f}%)")
    print(f"  平均回合数: {total_turns/n:.1f}")
    print(f"  总耗时: {elapsed:.2f}s  ({elapsed/n*1000:.1f}ms/场)")
    print(SEP)


# ============================================================
# 菜单：1. 开始对战
# ============================================================
def _menu_battle() -> None:
    print(f"\n{SEP}")
    print("  开始对战 — 选择 A 队")
    name_a = _pick_team("A 队序号")
    if name_a is None:
        return

    print(f"\n  A 队：{name_a}")
    print(f"  选择 B 队")
    name_b = _pick_team("B 队序号")
    if name_b is None:
        return

    team_a = build_team(name_a)
    team_b = build_team(name_b)
    run_battle(team_a, team_b, name_a, name_b, verbose=True)


# ============================================================
# 菜单：2. 新建队伍
# ============================================================
def _menu_new_team() -> None:
    print(f"\n{SEP}")
    print("  新建队伍")
    print("  输入队伍名称（留空取消）：", end="")
    name = input().strip()
    if not name:
        print("  已取消")
        return

    # 检查是否与预设同名
    existing = get_team_def(name)
    if existing and existing.get("preset"):
        print(f"  [!] 「{name}」是内置预设名，请换一个名称")
        return
    if existing:
        print(f"  队伍「{name}」已存在，继续将覆盖原内容。确认？(y/N)：", end="")
        if input().strip().lower() != "y":
            print("  已取消")
            return

    # 交互组队
    pokemon_list = build_team_interactive(name)

    # 从 Pokemon 对象提取成员定义
    members = [
        {"pokemon": p.name, "skills": [s.name for s in p.skills]}
        for p in pokemon_list
    ]

    result = add_team(name, members)
    verb = "已覆盖" if result == "replaced" else "已保存"
    print(f"\n  队伍「{name}」{verb}！（共 {len(members)} 只精灵）")


# ============================================================
# 菜单：3. 管理队伍
# ============================================================
def _edit_team(team_name: str) -> None:
    """交互式编辑队伍中任意精灵的技能和性格，完成后保存。"""
    from sim.skill_db import get_learnable_skills, get_all_skills
    from sim.team_roster import get_team_def
    from sim.pokemon_db import (get_nature, nature_display, NATURES,
                                compute_stats_with_nature, _STAT_KEY_DISPLAY)

    team_def = get_team_def(team_name)
    if team_def is None:
        print(f"  [!] 找不到队伍「{team_name}」")
        return

    # 深复制成员列表（保留 nature 字段）
    members = [
        {"pokemon": m["pokemon"], "skills": list(m["skills"]),
         "nature": m.get("nature")}
        for m in team_def["members"]
    ]
    all_skill_names = set(get_all_skills().keys())

    # 25 种性格有序列表，方便按序号选择
    _NATURE_LIST = list(NATURES.keys())  # 固定顺序

    def _nat_str(m: dict) -> str:
        """返回该成员当前显示的性格字符串"""
        custom = m.get("nature")
        if custom:
            return f"[{nature_display(custom)}*]"   # * = 自定义
        auto = get_nature(m["pokemon"])
        return f"[{nature_display(auto)}]" if auto else ""

    def _print_nature_table() -> None:
        """打印 25 种性格表（带序号，4 列）"""
        print("  25 种性格：")
        cols = 4
        for i, name in enumerate(_NATURE_LIST, 1):
            pair = NATURES[name]
            if pair[0]:
                tag = f"{name}({_STAT_KEY_DISPLAY[pair[0]]}↑{_STAT_KEY_DISPLAY[pair[1]]}↓)"
            else:
                tag = f"{name}（无变化）"
            print(f"  {i:2}. {tag:<18}", end="\n" if i % cols == 0 else "")
        if len(_NATURE_LIST) % cols != 0:
            print()

    while True:
        print(f"\n{LINE}")
        print(f"  编辑精灵配置  ·  队伍「{team_name}」")
        print(f"  <序号>=编辑技能和性格  n<序号>=仅改性格  0=保存退出")
        print(LINE)
        for i, m in enumerate(members, 1):
            ns = _nat_str(m)
            skills_str = "  |  ".join(f"{j}:{s}" for j, s in enumerate(m["skills"], 1))
            print(f"  {i}. {m['pokemon']:<12}{ns}  {skills_str}")
        print(LINE)
        print("  输入：", end="")
        raw = input().strip()

        if raw == "0" or raw == "":
            add_team(team_name, members)
            print(f"  队伍「{team_name}」已保存。")
            return

        # ── 改性格 n<序号> ──────────────────────────────────────
        if raw.lower().startswith("n") and raw[1:].isdigit():
            poke_idx = int(raw[1:]) - 1
            if not (0 <= poke_idx < len(members)):
                print("  [!] 序号超出范围")
                continue
            member = members[poke_idx]
            pname  = member["pokemon"]
            auto_nat = get_nature(pname) or "认真"
            cur_nat  = member.get("nature") or auto_nat

            print(f"\n  {pname} 当前性格：{nature_display(cur_nat)}"
                  + ("（自动）" if not member.get("nature") else "（自定义*）"))
            _print_nature_table()
            print(f"\n  输入序号或性格名（回车=恢复自动 [{nature_display(auto_nat)}]）：", end="")
            cmd = input().strip()

            if not cmd:
                member["nature"] = None
                print(f"  已恢复自动性格：{nature_display(auto_nat)}")
                continue

            # 尝试序号
            new_nat = None
            if cmd.isdigit() and 1 <= int(cmd) <= len(_NATURE_LIST):
                new_nat = _NATURE_LIST[int(cmd) - 1]
            elif cmd in NATURES:
                new_nat = cmd
            else:
                # 模糊匹配
                fuzzy = [n for n in NATURES if cmd in n]
                if len(fuzzy) == 1:
                    new_nat = fuzzy[0]
                    print(f"  → 模糊匹配：{new_nat}")
                elif len(fuzzy) > 1:
                    print(f"  [!] 匹配多个：{', '.join(fuzzy)}，请更精确")
                    continue
                else:
                    print(f"  [!] 未找到性格「{cmd}」")
                    continue

            member["nature"] = new_nat
            new_stats = compute_stats_with_nature(pname, new_nat)
            if new_stats:
                print(f"  {pname} 性格已设为 {nature_display(new_nat)}  "
                      f"→ HP={new_stats['生命值']} 物攻={new_stats['物攻']} "
                      f"魔攻={new_stats['魔攻']} 物防={new_stats['物防']} "
                      f"魔防={new_stats['魔防']} 速度={new_stats['速度']}")
            continue

        # ── 改技能 <序号> ───────────────────────────────────────
        if not raw.isdigit() or not (1 <= int(raw) <= len(members)):
            print("  [!] 无效输入")
            continue

        poke_idx = int(raw) - 1
        member = members[poke_idx]
        pname = member["pokemon"]
        learnable = get_learnable_skills(pname)

        # 显示可学技能列表（仅显示一次）
        print(f"\n  {pname} 的可学技能（共 {len(learnable)} 个）：")
        cols = 3
        for i, sname in enumerate(learnable, 1):
            in_team = "✓" if sname in member["skills"] else " "
            print(f"  {i:3}.{in_team}{sname:<12}", end="\n" if i % cols == 0 else "")
        if len(learnable) % cols != 0:
            print()

        # 技能编辑子循环：持续编辑直到回车空行返回
        while True:
            print(f"\n  当前技能：  1:{member['skills'][0]}  2:{member['skills'][1]}"
                  f"  3:{member['skills'][2]}  4:{member['skills'][3]}")
            print(f"  输入替换（支持多个，如 1:喷火, 2:水刃，3:冰晶）回车=完成：", end="")
            cmd = input().strip()

            if not cmd:
                break   # 回到外层精灵选择循环

            # 规范化：中文冒号→英文，中文逗号→英文
            normalized = cmd.replace("：", ":").replace("，", ",")

            # 拆分成多个 "槽位:技能" 对
            pairs = [p.strip() for p in normalized.split(",") if p.strip()]

            # 单个输入且不含冒号 → 可能是纯技能名（补全当前第一个空格或直接报错）
            if len(pairs) == 1 and ":" not in pairs[0]:
                print("  [!] 格式：槽位:技能，如  2:水刃  或  1:喷火, 2:冰晶")
                continue

            applied = []
            errors  = []

            for pair in pairs:
                if ":" not in pair:
                    errors.append(f"「{pair}」缺少冒号，跳过")
                    continue

                slot_str, skill_input = pair.split(":", 1)
                slot_str    = slot_str.strip()
                skill_input = skill_input.strip()

                if not slot_str.isdigit() or not (1 <= int(slot_str) <= 4):
                    errors.append(f"「{slot_str}」槽位须为 1-4，跳过")
                    continue
                slot = int(slot_str) - 1

                # 解析技能：序号 → 技能名 → 精确名 → 模糊匹配
                new_skill = None
                if skill_input.isdigit():
                    si = int(skill_input) - 1
                    if 0 <= si < len(learnable):
                        new_skill = learnable[si]
                    else:
                        errors.append(f"槽{slot_str}：序号 {skill_input} 超出范围，跳过")
                        continue
                elif skill_input in all_skill_names:
                    new_skill = skill_input
                else:
                    fuzzy = [s for s in learnable if skill_input in s]
                    if len(fuzzy) == 1:
                        new_skill = fuzzy[0]
                    elif len(fuzzy) > 1:
                        errors.append(f"槽{slot_str}：「{skill_input}」匹配多个（{', '.join(fuzzy[:4])}…），请更精确")
                        continue
                    else:
                        errors.append(f"槽{slot_str}：未找到技能「{skill_input}」")
                        continue

                old = member["skills"][slot]
                member["skills"][slot] = new_skill
                match_note = f"（模糊→{new_skill}）" if new_skill != skill_input and not skill_input.isdigit() else ""
                applied.append(f"  槽{slot_str} {old} → {new_skill}{match_note}")

            if applied:
                print("  已更新：")
                for line in applied:
                    print(line)
            for e in errors:
                print(f"  [!] {e}")


def _menu_manage() -> None:
    while True:
        _print_roster("队伍管理")
        print(f"\n  操作：e<序号>=编辑精灵配置  r<序号>=重命名  d<序号>=删除  <序号>=查看详情  0=返回")
        print("  输入：", end="")
        raw = input().strip()

        if raw == "0" or raw == "":
            return

        # 编辑: e3
        if raw.startswith("e") and raw[1:].isdigit():
            idx = int(raw[1:]) - 1
            teams = list_teams()
            if 0 <= idx < len(teams):
                t = teams[idx]
                if t.get("preset"):
                    print(f"  [!] 「{t['name']}」是内置预设，不可编辑")
                else:
                    _edit_team(t["name"])
            else:
                print("  [!] 序号超出范围")
            continue

        # 删除: d3
        if raw.startswith("d") and raw[1:].isdigit():
            idx = int(raw[1:]) - 1
            teams = list_teams()
            if 0 <= idx < len(teams):
                t = teams[idx]
                if t.get("preset"):
                    print(f"  [!] 「{t['name']}」是内置预设，不可删除")
                else:
                    print(f"  确认删除「{t['name']}」？(y/N)：", end="")
                    if input().strip().lower() == "y":
                        delete_team(t["name"])
                        print(f"  已删除「{t['name']}」")
            else:
                print("  [!] 序号超出范围")
            continue

        # 重命名: r3
        if raw.startswith("r") and raw[1:].isdigit():
            idx = int(raw[1:]) - 1
            teams = list_teams()
            if 0 <= idx < len(teams):
                t = teams[idx]
                if t.get("preset"):
                    print(f"  [!] 「{t['name']}」是内置预设，不可重命名")
                else:
                    print(f"  新名称（留空取消）：", end="")
                    new_name = input().strip()
                    if new_name:
                        try:
                            rename_team(t["name"], new_name)
                            print(f"  已重命名为「{new_name}」")
                        except ValueError as e:
                            print(f"  [!] {e}")
            else:
                print("  [!] 序号超出范围")
            continue

        # 查看详情
        if raw.isdigit():
            idx = int(raw) - 1
            teams = list_teams()
            if 0 <= idx < len(teams):
                t = teams[idx]
                tag = "[预设]" if t.get("preset") else "[自定]"
                print(f"\n  {tag} 队伍：{t['name']}")
                from sim.pokemon_db import get_nature, nature_display
                for i, m in enumerate(t["members"], 1):
                    custom = m.get("nature")
                    if custom:
                        nat_str = f"  {nature_display(custom)}*"
                    else:
                        auto = get_nature(m["pokemon"])
                        nat_str = f"  {nature_display(auto)}" if auto else ""
                    print(f"    {i}. {m['pokemon']:<12}{nat_str}"
                          f"  技能：{', '.join(m['skills'])}")
                input("\n  按 Enter 返回...")   # ← 修复：暂停后再刷新列表
            else:
                print("  [!] 序号超出范围")
            continue

        print("  [!] 无效输入")


# ============================================================
# 菜单：4. 批量模拟
# ============================================================
def _menu_batch() -> None:
    print(f"\n{SEP}")
    print("  批量模拟 — 选择 A 队")
    name_a = _pick_team("A 队序号")
    if name_a is None:
        return

    print(f"  A 队：{name_a}")
    print("  选择 B 队")
    name_b = _pick_team("B 队序号")
    if name_b is None:
        return

    raw = input("  模拟场数 N（默认 100）：").strip()
    n = int(raw) if raw.isdigit() and int(raw) > 0 else 100

    run_batch(
        lambda: build_team(name_a),
        lambda: build_team(name_b),
        name_a, name_b, n,
    )


# ============================================================
# 菜单：5. 从图片导入队伍
# ============================================================
def _pick_parse_method() -> Optional[str]:
    """让用户选择解析方式，返回 'api' | 'ocr_rapid' | 'ocr_easy' | None"""
    from sim.team_image_parser_ocr import get_available_engines

    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
    ocr_engines = get_available_engines()

    print(f"\n  选择识别方式：")

    options = []
    # API 选项
    api_note = "（已配置 API Key）" if has_api_key else "（需配置 ANTHROPIC_API_KEY）"
    print(f"  1. Claude Vision API  ★精度最高{api_note}")
    options.append("api")

    # OCR 选项
    if "rapid" in ocr_engines:
        print(f"  2. 本地 OCR（rapidocr）  免费，有一定错误率，建议导入后核对")
        options.append("ocr_rapid")
    else:
        print(f"  2. 本地 OCR（rapidocr）  [未安装] pip install rapidocr-onnxruntime")
        options.append(None)

    if "easy" in ocr_engines:
        print(f"  3. 本地 OCR（easyocr）   免费，精度略高于 rapid，依赖 PyTorch")
        options.append("ocr_easy")
    else:
        print(f"  3. 本地 OCR（easyocr）   [未安装] pip install easyocr")
        options.append(None)

    print(f"  0. 取消")
    print(f"  选择 [0-3]：", end="")
    raw = input().strip()

    if raw == "0" or not raw:
        return None
    if raw.isdigit() and 1 <= int(raw) <= 3:
        chosen = options[int(raw) - 1]
        if chosen is None:
            print(f"  [!] 该 OCR 引擎未安装，请先安装后再使用")
            return None
        return chosen
    print("  [!] 无效选择")
    return None


def _do_parse(img_path: str, method: str) -> Optional[dict]:
    """执行解析，返回校验后的结果 dict，失败返回 None"""
    from sim.team_image_parser import parse_and_validate as api_parse
    from sim.team_image_parser import validate_and_fix
    from sim.team_image_parser_ocr import parse_team_image_ocr

    if method == "api":
        print("  正在调用 Claude Vision API（约 3-8 秒）...")
        try:
            return api_parse(img_path)
        except EnvironmentError as e:
            print(f"\n  [!] {e}")
            return None
        except Exception as e:
            print(f"\n  [!] API 解析失败：{e}")
            return None

    # OCR 方式
    engine = "rapid" if method == "ocr_rapid" else "easy"
    engine_name = "rapidocr" if engine == "rapid" else "easyocr"
    print(f"  正在用 {engine_name} 识别（首次运行会下载模型）...")
    print("  ⚠ OCR 识别游戏字体存在一定错误率，建议导入后人工核对技能名称")
    try:
        raw = parse_team_image_ocr(img_path, engine=engine)
        return validate_and_fix(raw)
    except ImportError as e:
        print(f"\n  [!] {e}")
        return None
    except Exception as e:
        print(f"\n  [!] OCR 解析失败：{e}")
        return None


def _menu_import_image() -> None:
    os.makedirs(_IMPORT_DIR, exist_ok=True)

    # 扫描 import_images/ 下的图片文件
    images = sorted(
        p for p in os.listdir(_IMPORT_DIR)
        if os.path.splitext(p)[1].lower() in _IMAGE_EXTS
    )

    if not images:
        print(f"\n  [!] import_images/ 文件夹中没有图片。")
        print(f"  请将队伍配置截图放入以下目录：")
        print(f"  {_IMPORT_DIR}")
        return

    print(f"\n{SEP}")
    print(f"  import_images/ 中的图片（共 {len(images)} 张）：")
    for i, name in enumerate(images, 1):
        print(f"    {i:2}. {name}")
    print("  输入序号选择图片（0 取消）：", end="")

    raw = input().strip()
    if raw == "0" or not raw:
        return
    if not raw.isdigit() or not (1 <= int(raw) <= len(images)):
        print("  [!] 无效序号")
        return

    img_path = os.path.join(_IMPORT_DIR, images[int(raw) - 1])
    print(f"\n  已选：{images[int(raw)-1]}")

    # 选择解析方式
    method = _pick_parse_method()
    if method is None:
        return

    result = _do_parse(img_path, method)
    if result is None:
        return

    # 显示解析结果
    print(f"\n{SEP}")
    print(f"  识别结果：队伍名「{result['team_name']}」")
    for i, m in enumerate(result["members"], 1):
        skills_str = ", ".join(s for s in m["skills"] if s)
        print(f"    {i}. {m['pokemon']:<12} 技能：{skills_str}")

    if result["warnings"]:
        print(f"\n  ⚠ 校验提示（{len(result['warnings'])} 条）：")
        for w in result["warnings"]:
            print(f"    · {w}")

    # 确认队伍名
    print(f"\n  队伍名称（直接回车使用「{result['team_name']}」，或输入新名称）：", end="")
    custom_name = input().strip()
    final_name = custom_name if custom_name else result["team_name"]

    # 检查是否与预设同名
    existing = get_team_def(final_name)
    if existing and existing.get("preset"):
        print(f"  [!] 「{final_name}」是内置预设名，请重新输入队伍名称：", end="")
        final_name = input().strip()
        if not final_name:
            print("  已取消")
            return

    # 过滤掉技能为空的槽位
    valid_members = [
        {"pokemon": m["pokemon"], "skills": [s for s in m["skills"] if s]}
        for m in result["members"]
        if m["pokemon"]
    ]

    if not valid_members:
        print("  [!] 没有有效的精灵数据，已取消")
        return

    print(f"\n  确认保存队伍「{final_name}」（{len(valid_members)} 只精灵）？(Y/n)：", end="")
    confirm = input().strip().lower()
    if confirm == "n":
        print("  已取消")
        return

    save_result = add_team(final_name, valid_members)
    verb = "已覆盖" if save_result == "replaced" else "已保存"
    print(f"\n  队伍「{final_name}」{verb}！可在对战菜单中选用。")


# ============================================================
# 主菜单
# ============================================================
def main() -> None:
    load_pokemon_db()
    load_skills()
    # 确保名册已初始化（首次运行时写入默认预设）
    list_teams()

    while True:
        print(f"\n{SEP}")
        print("  洛克王国战斗模拟器")
        print(SEP)
        teams = list_teams()
        print(f"  当前队伍列表（{len(teams)} 支）：")
        for i, t in enumerate(teams, 1):
            tag = "[预设]" if t.get("preset") else "[自定]"
            print(f"    {i:2}. {tag} {t['name']}")
        print(SEP)
        print("  1. 开始对战        （从列表选两支队伍）")
        print("  2. 新建队伍        （交互组队并保存）")
        print("  3. 管理队伍        （查看 / 删除 / 重命名）")
        print("  4. 批量模拟        （选两支队伍跑 N 场）")
        print("  5. 从图片导入队伍  （识别标准组队分享图）")
        print("  0. 返回")
        print(SEP)

        try:
            choice = input("  选择 [0-5]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！")
            break

        if choice == "0":
            break
        elif choice == "1":
            _menu_battle()
        elif choice == "2":
            _menu_new_team()
        elif choice == "3":
            _menu_manage()
        elif choice == "4":
            _menu_batch()
        elif choice == "5":
            _menu_import_image()
        else:
            print("  无效选择，请输入 0-5")
            continue

        try:
            input("\n  按 Enter 继续...")
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
