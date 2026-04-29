"""
并发批量战斗模拟器

使用多进程并行执行MCTS对战，加速训练过程。
每个进程独立运行完整的对战流程（加载数据→MCTS搜索→记录经验），
最后合并结果和经验数据库。

架构设计：
  - 主进程负责任务分发和进度跟踪
  - 工作进程各自独立运行对战，避免GIL锁争用
  - 经验数据在进程结束后合并到JSON文件
"""

import os
import sys
import time
import json
import multiprocessing as mp
from typing import List, Dict, Optional, Callable, Any

# 确保模块路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sim.pokemon_db import load_pokemon_db
from sim.skill_db import load_skills
from sim.team_roster import build_team
from sim.battle_state import BattleState
from sim.battle_engine import BattleEngine
from sim.mcts_agent import MCTSAgent
from sim.experience_db import ExperienceDB, ActionStats

# 批量模拟MCTS迭代次数（可调整：20快速 / 50标准 / 100强力）
_MCTS_ITERS_BATCH = 20

# 最大回合数限制
_MAX_TURNS = BattleEngine.MAX_TURNS


def _run_single_battle(args: tuple) -> dict:
    """
    在子进程中运行单场对战。
    
    Parameters
    ----------
    args : (team_a_name, team_b_name, mcts_iters)
        - team_a_name: A队名称（用于加载队伍和策略）
        - team_b_name: B队名称
        - mcts_iters: MCTS迭代次数
        
    Returns
    -------
    dict : {
        "winner": "a" | "b" | None,
        "turns": int,
        "exp_a": ExperienceDB实例（序列化后）,
        "exp_b": ExperienceDB实例
    }
    """
    team_a_name, team_b_name, mcts_iters = args
    
    # 在子进程中加载数据
    load_pokemon_db()
    load_skills()
    
    # 构建队伍
    team_a = build_team(team_a_name)
    team_b = build_team(team_b_name)
    
    # 创建MCTS Agent
    from sim.experience_db import ExperienceDB
    exp_a = ExperienceDB()  # 空经验库
    exp_b = ExperienceDB()
    
    agent_a = MCTSAgent("a", team_a_name, iterations=mcts_iters, load_exp=False)
    agent_b = MCTSAgent("b", team_b_name, iterations=mcts_iters, load_exp=False)
    # 替换经验库 — 必须同时替换agent和_search的引用，否则脱节
    agent_a.experience_db = exp_a
    agent_a._search.experience_db = exp_a
    agent_b.experience_db = exp_b
    agent_b._search.experience_db = exp_b
    
    # 运行对战
    state = BattleState(team_a=team_a, team_b=team_b)
    engine = BattleEngine(state, verbose=False)
    history = []
    winner = None
    
    for _ in range(_MAX_TURNS):
        winner = engine.check_winner()
        if winner:
            break
        snap = state.deep_copy()
        action_a = agent_a.choose_action(engine)
        action_b = agent_b.choose_action(engine)
        history.append((snap, action_a, action_b))
        engine.execute_turn(action_a, action_b)
    
    if not winner:
        winner = engine.check_winner()
    
    # 记录经验
    agent_a.experience_db.record_game(history, winner)
    agent_b.experience_db.record_game(history, winner)
    
    return {
        "winner": winner,
        "turns": state.turn,
        "exp_a": agent_a.experience_db._db,
        "exp_b": agent_b.experience_db._db,
        "total_games_a": agent_a.experience_db.total_games,
        "total_games_b": agent_b.experience_db.total_games,
    }


def _merge_experience_dbs(
    exp_data_list: list,  # list of (team, exp_dict, total_games)
) -> ExperienceDB:
    """
    合并多个经验数据库。
    
    Parameters
    ----------
    exp_data_list : [(team, exp_dict, total_games), ...]
        - team: "a" or "b"
        - exp_dict: _db dict from ExperienceDB (values are ActionStats objects)
        - total_games: int
    
    Returns
    -------
    ExperienceDB : 合并后的经验数据库
    """
    merged_db = {"a": {}, "b": {}}
    total_games = 0
    
    for team, exp_dict, games in exp_data_list:
        if team not in merged_db:
            continue
        total_games += games
        state_dict = merged_db[team]
        for sk, actions in exp_dict.items():
            if sk not in state_dict:
                state_dict[sk] = {}
            for ak, stats_obj in actions.items():
                if ak not in state_dict[sk]:
                    state_dict[sk][ak] = ActionStats()
                # 兼容两种格式：ActionStats对象和dict
                if isinstance(stats_obj, ActionStats):
                    merged_stats = state_dict[sk][ak]
                    merged_stats.wins += stats_obj.wins
                    merged_stats.total += stats_obj.total
                else:
                    # dict格式 {"w": ..., "n": ...}
                    state_dict[sk][ak].wins += stats_obj.get("w", 0)
                    state_dict[sk][ak].total += stats_obj.get("n", 0)
    
    merged_exp = ExperienceDB()
    merged_exp._db = merged_db
    merged_exp.total_games = total_games
    
    return merged_exp


def _serialize_exp_db(db_dict):
    """将ActionStats对象转为dict以便JSON序列化"""
    serialized = {}
    for team, states in db_dict.items():
        serialized[team] = {}
        for sk, actions in states.items():
            serialized[sk] = {}
            for ak, stats in actions.items():
                serialized[sk][ak] = {"w": stats.wins, "n": stats.total}
    return serialized


def run_concurrent_batch_with_experience(
    team_a_name: str,
    team_b_name: str,
    n: int,
    workers: int = None,
    mcts_iters: int = _MCTS_ITERS_BATCH,
    exp_dir: str = None,
) -> dict:
    """
    并发批量模拟并合并经验数据库。
    
    使用multiprocessing.Pool替代ProcessPoolExecutor，
    避免Python 3.9的"dictionary changed size during iteration" bug。
    
    Parameters
    ----------
    team_a_name : A队名称
    team_b_name : B队名称
    n : 对战总场数
    workers : 工作进程数
    mcts_iters : MCTS迭代次数
    exp_dir : 经验数据库保存目录
    
    Returns
    -------
    dict : {
        "results": {"a": int, "b": int, "draw": int},
        "total_turns": int,
        "elapsed": float,
        "exp_a_path": str,  # A队经验保存路径
        "exp_b_path": str,  # B队经验保存路径
    }
    """
    if workers is None:
        workers = min(mp.cpu_count(), n)
        workers = max(1, workers)
    
    exp_dir = exp_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "data", "experience"
    )
    os.makedirs(exp_dir, exist_ok=True)
    
    print(f"\n  [并发模拟+经验] {team_a_name} vs {team_b_name}")
    print(f"  [配置] 场数={n}, MCTS迭代={mcts_iters}, 工作进程={workers}")
    
    # 检查是否使用数据库后端
    try:
        from sim.data_store import DataStore
        store = DataStore()
        use_db = store.db_enabled
    except ImportError:
        use_db = False
    
    if use_db:
        print(f"  [存储] MariaDB（增量保存）")
    else:
        print(f"  [存储] JSON文件")
    
    results = {"a": 0, "b": 0, "draw": 0}
    total_turns = 0
    t0 = time.time()
    
    # 准备任务列表
    tasks = [
        (team_a_name, team_b_name, mcts_iters)
        for _ in range(n)
    ]
    
    # 收集经验数据 — 按队伍分组
    all_exp_data_a = []  # list of exp_dict from agent_a
    all_exp_data_b = []  # list of exp_dict from agent_b
    total_games_sum_a = 0
    total_games_sum_b = 0
    
    # 使用multiprocessing.Pool替代ProcessPoolExecutor
    # Pool更稳定，不会出现"dictionary changed size during iteration" bug
    with mp.Pool(processes=workers) as pool:
        # imap_unordered返回结果不保证顺序，但能尽早处理完成的任务
        iterator = pool.imap_unordered(_run_single_battle, tasks)
        
        completed = 0
        for result in iterator:
            winner = result["winner"]
            results[winner or "draw"] += 1
            total_turns += result["turns"]
            
            # 收集经验数据 — 按队伍分别存储
            all_exp_data_a.append(result["exp_a"])
            all_exp_data_b.append(result["exp_b"])
            total_games_sum_a += result["total_games_a"]
            total_games_sum_b += result["total_games_b"]
            
            completed += 1
            elapsed_so_far = time.time() - t0
            rate = elapsed_so_far / completed
            eta = rate * (n - completed)
            bar_filled = int(20 * completed / n)
            bar = "#" * bar_filled + "." * (20 - bar_filled)
            
            print(
                f"\r  [{bar}] {completed:4}/{n}  "
                f"A:{results['a']} B:{results['b']} 平:{results['draw']}  "
                f"ETA:{eta:.0f}s ",
                end="", flush=True,
            )
    
    elapsed = time.time() - t0
    
    # 合并经验数据库 — 按队伍分别合并
    print("\n  [合并经验] 正在合并各进程的经验数据...")
    
    # A队：只合并每个exp_a中team='a'的部分，B队同理
    merged_db_a = {"a": {}, "b": {}}
    for exp_dict in all_exp_data_a:
        team_data = exp_dict.get("a", {})
        for sk, actions in team_data.items():
            if sk not in merged_db_a["a"]:
                merged_db_a["a"][sk] = {}
            for ak, stats_obj in actions.items():
                if isinstance(stats_obj, ActionStats):
                    if ak not in merged_db_a["a"][sk]:
                        merged_db_a["a"][sk][ak] = ActionStats()
                    merged_db_a["a"][sk][ak].wins += stats_obj.wins
                    merged_db_a["a"][sk][ak].total += stats_obj.total
    
    merged_db_b = {"a": {}, "b": {}}
    for exp_dict in all_exp_data_b:
        team_data = exp_dict.get("b", {})
        for sk, actions in team_data.items():
            if sk not in merged_db_b["b"]:
                merged_db_b["b"][sk] = {}
            for ak, stats_obj in actions.items():
                if isinstance(stats_obj, ActionStats):
                    if ak not in merged_db_b["b"][sk]:
                        merged_db_b["b"][sk][ak] = ActionStats()
                    merged_db_b["b"][sk][ak].wins += stats_obj.wins
                    merged_db_b["b"][sk][ak].total += stats_obj.total
    
    # 创建合并后的ExperienceDB实例
    merged_a = ExperienceDB()
    merged_a._db = merged_db_a
    merged_a.total_games = total_games_sum_a
    
    merged_b = ExperienceDB()
    merged_b._db = merged_db_b
    merged_b.total_games = total_games_sum_b
    
    # 保存经验数据库 — 根据配置选择后端
    exp_a_path = os.path.join(exp_dir, f"{team_a_name}.json")
    exp_b_path = os.path.join(exp_dir, f"{team_b_name}.json")
    
    if use_db:
        # 保存到数据库（增量保存，只更新被修改过的记录）
        print("  [保存] 正在写入MariaDB...")
        for team in ("a", "b"):
            merged_exp = merged_a if team == "a" else merged_b
            team_name = team_a_name if team == "a" else team_b_name
            
            # 遍历所有经验记录并保存到数据库
            for sk, actions in merged_exp._db.get(team, {}).items():
                for ak, stats_obj in actions.items():
                    store.update_experience(
                        team=team,
                        state_key=sk,
                        action_key=ak,
                        wins=stats_obj.wins,
                        total=stats_obj.total
                    )
            
            # 记录对战结果到数据库
            store.record_battle(
                team_a_name=team_a_name,
                team_b_name=team_b_name,
                winner="a" if results["a"] > results["b"] else ("b" if results["b"] > results["a"] else None),
                turns=total_turns // n,
                elapsed_ms=int(elapsed * 1000),
                mcts_iters=mcts_iters
            )
        
        print(f"  [保存] A队经验 → MariaDB")
        print(f"  [保存] B队经验 → MariaDB")
    else:
        # 保存到JSON文件（原有逻辑）
        with open(exp_a_path, "w", encoding="utf-8") as f:
            json.dump(_serialize_exp_db(merged_a._db), f, ensure_ascii=False)
        
        with open(exp_b_path, "w", encoding="utf-8") as f:
            json.dump(_serialize_exp_db(merged_b._db), f, ensure_ascii=False)
        
        print(f"  [保存] A队经验 → {exp_a_path}")
        print(f"  [保存] B队经验 → {exp_b_path}")
    
    print(f"\n{'=' * 56}")
    print(f"  并发批量模拟结果（{n} 场，MCTS×{mcts_iters}）")
    print(f"  {team_a_name} 胜: {results['a']:4} 场  ({results['a']/n*100:.1f}%)")
    print(f"  {team_b_name} 胜: {results['b']:4} 场  ({results['b']/n*100:.1f}%)")
    print(f"  平局:     {results['draw']:4} 场  ({results['draw']/n*100:.1f}%)")
    print(f"  平均回合数: {total_turns/n:.1f}")
    print(f"  总耗时: {elapsed:.2f}s  ({elapsed/n*1000:.1f}ms/场)")
    print("=" * 56)
    
    return {
        "results": results,
        "total_turns": total_turns,
        "elapsed": elapsed,
        "exp_a_path": exp_a_path,
        "exp_b_path": exp_b_path,
    }


def run_concurrent_batch(
    team_a_name: str,
    team_b_name: str,
    n: int,
    workers: int = None,
    mcts_iters: int = _MCTS_ITERS_BATCH,
) -> dict:
    """
    并发批量模拟（不保存经验数据，仅统计结果）。
    
    Parameters
    ----------
    team_a_name : A队名称
    team_b_name : B队名称
    n : 对战总场数
    workers : 工作进程数
    mcts_iters : MCTS迭代次数
    
    Returns
    -------
    dict : {
        "results": {"a": int, "b": int, "draw": int},
        "total_turns": int,
        "elapsed": float,
    }
    """
    if workers is None:
        workers = min(mp.cpu_count(), n)
        workers = max(1, workers)
    
    print(f"\n  [并发模拟] {team_a_name} vs {team_b_name}")
    print(f"  [配置] 场数={n}, MCTS迭代={mcts_iters}, 工作进程={workers}")
    
    results = {"a": 0, "b": 0, "draw": 0}
    total_turns = 0
    t0 = time.time()
    
    # 准备任务列表
    tasks = [
        (team_a_name, team_b_name, mcts_iters)
        for _ in range(n)
    ]
    
    with mp.Pool(processes=workers) as pool:
        iterator = pool.imap_unordered(_run_single_battle, tasks)
        
        completed = 0
        for result in iterator:
            winner = result["winner"]
            results[winner or "draw"] += 1
            total_turns += result["turns"]
            
            completed += 1
            elapsed_so_far = time.time() - t0
            rate = elapsed_so_far / completed
            eta = rate * (n - completed)
            bar_filled = int(20 * completed / n)
            bar = "#" * bar_filled + "." * (20 - bar_filled)
            
            print(
                f"\r  [{bar}] {completed:4}/{n}  "
                f"A:{results['a']} B:{results['b']} 平:{results['draw']}  "
                f"ETA:{eta:.0f}s ",
                end="", flush=True,
            )
    
    elapsed = time.time() - t0
    print(f"\n{'=' * 56}")
    print(f"  并发批量模拟结果（{n} 场，MCTS×{mcts_iters}）")
    print(f"  {team_a_name} 胜: {results['a']:4} 场  ({results['a']/n*100:.1f}%)")
    print(f"  {team_b_name} 胜: {results['b']:4} 场  ({results['b']/n*100:.1f}%)")
    print(f"  平局:     {results['draw']:4} 场  ({results['draw']/n*100:.1f}%)")
    print(f"  平均回合数: {total_turns/n:.1f}")
    print(f"  总耗时: {elapsed:.2f}s  ({elapsed/n*1000:.1f}ms/场)")
    print("=" * 56)
    
    return {
        "results": results,
        "total_turns": total_turns,
        "elapsed": elapsed,
    }


if __name__ == "__main__":
    # 测试并发模拟
    load_pokemon_db()
    load_skills()
    
    print("测试并发批量模拟：预设毒队 vs 狼王队（10场）")
    run_concurrent_batch_with_experience(
        team_a_name="预设毒队",
        team_b_name="狼王队",
        n=10,
        workers=4,  # 使用4个进程
        mcts_iters=_MCTS_ITERS_BATCH,
    )
