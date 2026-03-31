"""
洛克王国 MCTS AI 训练 / 演示入口

菜单：
  1. 观战一局        — 双 MCTS 对战，实时打印日志
  2. 批量自我训练    — 跑 N 局，积累经验，保存到磁盘
  3. 查看经验统计    — 显示某个队伍的经验数据库摘要
  4. 基准对比        — MCTS vs 随机 AI，跑 N 局看胜率差距
  0. 退出

用法：
  python train.py
"""

import sys
import os
import random
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sim.pokemon_db import load_pokemon_db
from sim.skill_db import load_skills
from sim.battle_state import BattleState
from sim.battle_engine import BattleEngine
from sim.team_roster import list_teams, build_team
from sim.mcts_agent import MCTSAgent, run_mcts_battle
from sim.experience_db import ExperienceDB

SEP  = "=" * 56
LINE = "─" * 56


# ============================================================
# 选队工具
# ============================================================

def _print_roster() -> None:
    teams = list_teams()
    print(f"\n  队伍列表（{len(teams)} 支）：")
    for i, t in enumerate(teams, 1):
        tag     = "[预设]" if t.get("preset") else "[自定]"
        members = "  ".join(m["pokemon"] for m in t["members"])
        print(f"  {i:2}. {tag} {t['name']:<14} {members}")


def _pick_team(prompt: str) -> Optional[str]:
    _print_roster()
    teams = list_teams()
    print(f"\n  {prompt}（0 取消）：", end="")
    raw = input().strip()
    if raw == "0" or not raw:
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(teams):
            return teams[idx]["name"]
    print("  [!] 无效序号")
    return None


def _pick_iterations(default: int = 100) -> int:
    print(f"  MCTS 迭代次数（越大越强越慢，默认 {default}，建议 50-300）：", end="")
    raw = input().strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return default


# ============================================================
# 菜单 1：观战一局
# ============================================================

def _menu_watch() -> None:
    print(f"\n{SEP}")
    print("  观战模式 — 选 A 队")
    name_a = _pick_team("A 队序号")
    if not name_a:
        return
    print(f"  选 B 队")
    name_b = _pick_team("B 队序号")
    if not name_b:
        return

    iters = _pick_iterations(100)

    print(f"\n{SEP}")
    print(f"  {name_a}  vs  {name_b}   MCTS×{iters}")
    print(SEP)

    agent_a = MCTSAgent("a", name_a, iterations=iters)
    agent_b = MCTSAgent("b", name_b, iterations=iters)
    team_a  = build_team(name_a)
    team_b  = build_team(name_b)

    t0     = time.time()
    winner = run_mcts_battle(agent_a, agent_b, team_a, team_b, verbose=True, record=True)
    elapsed = time.time() - t0

    tag = (f"{name_a} 赢！" if winner == "a"
           else (f"{name_b} 赢！" if winner == "b" else "平局/超时"))
    print(f"\n{SEP}")
    print(f"  {tag}  耗时 {elapsed:.1f}s")
    print(SEP)

    print(f"  保存经验？(Y/n)：", end="")
    if input().strip().lower() != "n":
        pa = agent_a.save()
        pb = agent_b.save()
        print(f"  已保存：{os.path.basename(pa)}  {os.path.basename(pb)}")


# ============================================================
# 菜单 2：批量自我训练
# ============================================================

def _menu_train() -> None:
    print(f"\n{SEP}")
    print("  批量训练 — 选 A 队")
    name_a = _pick_team("A 队序号")
    if not name_a:
        return
    print(f"  选 B 队")
    name_b = _pick_team("B 队序号")
    if not name_b:
        return

    raw_n = input("  训练局数 N（默认 50）：").strip()
    n     = int(raw_n) if raw_n.isdigit() and int(raw_n) > 0 else 50

    iters = _pick_iterations(50)

    print(f"\n{SEP}")
    print(f"  {name_a} vs {name_b}  ×{n} 局  MCTS×{iters}")
    print(SEP)

    agent_a = MCTSAgent("a", name_a, iterations=iters)
    agent_b = MCTSAgent("b", name_b, iterations=iters)

    results = {"a": 0, "b": 0, "draw": 0}
    t0 = time.time()

    for i in range(1, n + 1):
        team_a = build_team(name_a)
        team_b = build_team(name_b)
        winner = run_mcts_battle(
            agent_a, agent_b, team_a, team_b, verbose=False, record=True
        )
        results[winner or "draw"] += 1

        # 进度条
        bar_len = 30
        filled  = int(bar_len * i / n)
        bar     = "#" * filled + "." * (bar_len - filled)
        elapsed = time.time() - t0
        rate_a  = results["a"] / i * 100
        print(f"\r  [{bar}] {i}/{n}  A:{rate_a:.0f}%  {elapsed:.0f}s", end="", flush=True)

    elapsed = time.time() - t0
    print()  # 换行
    print(f"\n{SEP}")
    print(f"  训练完成  ({n} 局  {elapsed:.1f}s  {elapsed/n*1000:.0f}ms/局)")
    print(f"  {name_a} 胜: {results['a']:4}  ({results['a']/n*100:.1f}%)")
    print(f"  {name_b} 胜: {results['b']:4}  ({results['b']/n*100:.1f}%)")
    print(f"  平局:     {results['draw']:4}  ({results['draw']/n*100:.1f}%)")
    print(SEP)

    pa = agent_a.save()
    pb = agent_b.save()
    print(f"  经验已保存：{os.path.basename(pa)}  {os.path.basename(pb)}")


# ============================================================
# 菜单 3：查看经验统计
# ============================================================

def _menu_stats() -> None:
    exp_dir = os.path.join(os.path.dirname(__file__), "data", "experience")
    if not os.path.isdir(exp_dir):
        print("\n  [!] 尚无经验数据（先运行训练）")
        return

    files = [f for f in os.listdir(exp_dir) if f.endswith(".json")]
    if not files:
        print("\n  [!] data/experience/ 中没有经验文件")
        return

    print(f"\n  可用经验文件：")
    for i, fn in enumerate(files, 1):
        fp = os.path.join(exp_dir, fn)
        sz = os.path.getsize(fp) // 1024
        print(f"  {i:2}. {fn[:-5]:<20} ({sz} KB)")

    print("  输入序号（0 取消）：", end="")
    raw = input().strip()
    if not raw.isdigit() or int(raw) == 0:
        return
    idx = int(raw) - 1
    if not (0 <= idx < len(files)):
        print("  [!] 无效序号")
        return

    name = files[idx][:-5]
    db = ExperienceDB.load_or_create(name)
    print(f"\n{SEP}")
    print(db.summary("a"))
    print()
    print(db.summary("b"))
    print(SEP)


# ============================================================
# 菜单 4：基准对比（MCTS vs 随机）
# ============================================================

def _menu_benchmark() -> None:
    print(f"\n{SEP}")
    print("  基准对比：MCTS（A队）vs 随机AI（B队）")
    name_a = _pick_team("MCTS 队伍序号")
    if not name_a:
        return
    print("  选择随机 AI 对手队伍")
    name_b = _pick_team("对手队伍序号")
    if not name_b:
        return

    raw_n = input("  对战局数（默认 30）：").strip()
    n     = int(raw_n) if raw_n.isdigit() and int(raw_n) > 0 else 30
    iters = _pick_iterations(80)

    print(f"\n{SEP}")
    print(f"  MCTS({name_a}) vs 随机({name_b})  ×{n} 局  MCTS×{iters}")
    print(SEP)

    agent_a = MCTSAgent("a", name_a, iterations=iters)
    results = {"a": 0, "b": 0, "draw": 0}
    t0 = time.time()

    for i in range(1, n + 1):
        state  = BattleState(team_a=build_team(name_a), team_b=build_team(name_b))
        engine = BattleEngine(state, verbose=False)
        winner = None

        for _ in range(BattleEngine.MAX_TURNS):
            winner = engine.check_winner()
            if winner:
                break
            action_a = agent_a.choose_action(engine)        # MCTS
            action_b = random.choice(engine.get_actions("b"))  # 随机
            engine.execute_turn(action_a, action_b)

        if not winner:
            winner = engine.check_winner()
        results[winner or "draw"] += 1

        bar_len = 30
        filled  = int(bar_len * i / n)
        bar     = "#" * filled + "." * (bar_len - filled)
        rate_a  = results["a"] / i * 100
        print(f"\r  [{bar}] {i}/{n}  MCTS:{rate_a:.0f}%  {time.time()-t0:.0f}s",
              end="", flush=True)

    elapsed = time.time() - t0
    print()
    print(f"\n{SEP}")
    print(f"  基准对比结果（{n} 局  {elapsed:.1f}s）")
    print(f"  MCTS({name_a}) 胜: {results['a']:3}  ({results['a']/n*100:.1f}%)")
    print(f"  随机({name_b}) 胜: {results['b']:3}  ({results['b']/n*100:.1f}%)")
    print(f"  平局:           {results['draw']:3}  ({results['draw']/n*100:.1f}%)")
    print(SEP)

    print(f"  保存 MCTS 经验？(Y/n)：", end="")
    if input().strip().lower() != "n":
        path = agent_a.save()
        print(f"  已保存：{os.path.basename(path)}")


# ============================================================
# 主菜单
# ============================================================

def main() -> None:
    load_pokemon_db()
    load_skills()
    list_teams()  # 确保默认队伍已初始化

    print(f"\n{SEP}")
    print("  洛克王国  MCTS AI 训练系统")
    print(SEP)
    print("  经验数据库存储在 data/experience/")
    print("  每完成训练/观战后可保存，下次自动加载继续学习")
    print(SEP)

    while True:
        print(f"\n  1. 观战一局      （双 MCTS 实时对战）")
        print(f"  2. 批量自我训练  （跑 N 局，积累经验）")
        print(f"  3. 查看经验统计  （胜率/动作频率）")
        print(f"  4. 基准对比      （MCTS vs 随机 AI）")
        print(f"  0. 退出")
        print(f"  选择 [0-4]：", end="")

        try:
            choice = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！")
            break

        if choice == "0":
            print("  再见！")
            break
        elif choice == "1":
            _menu_watch()
        elif choice == "2":
            _menu_train()
        elif choice == "3":
            _menu_stats()
        elif choice == "4":
            _menu_benchmark()
        else:
            print("  无效选择")
            continue

        try:
            input("\n  按 Enter 继续...")
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
