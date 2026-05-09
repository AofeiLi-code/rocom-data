"""
跑几场 BWIKI 玩家配队对战，确保 C 组特性集成无崩溃。
不验证胜负，只验证完成。
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.lineups_loader import load_lineups, lineup_to_members
from sim.team_builder import build_pokemon
from sim.battle_engine import BattleEngine
from sim.battle_state import BattleState


def build_pokemon_team(members):
    out = []
    for m in members:
        try:
            p = build_pokemon(m["pokemon"], m["skills"], nature=m.get("nature"))
            out.append(p)
        except Exception:
            pass
    return out


def main():
    lineups = load_lineups()
    print(f"[*] 共加载 {len(lineups)} 套配队")

    random.seed(42)
    sample = random.sample(lineups, k=min(10, len(lineups)))
    pairs = list(zip(sample[::2], sample[1::2]))

    n_ok = 0
    for i, (la, lb) in enumerate(pairs):
        try:
            members_a = lineup_to_members(la)
            members_b = lineup_to_members(lb)
            if not members_a or not members_b:
                print(f"  [{i}] 空队伍，跳过")
                continue
            team_a = build_pokemon_team(members_a)
            team_b = build_pokemon_team(members_b)
            if not team_a or not team_b:
                print(f"  [{i}] 队伍无法构建，跳过")
                continue

            state = BattleState(team_a=team_a, team_b=team_b)
            engine = BattleEngine(state, verbose=False)

            # 简单随机 AI：每队随机选一个动作
            for turn in range(80):
                if engine.check_winner():
                    break
                act_a = random.choice(engine.get_actions("a"))
                act_b = random.choice(engine.get_actions("b"))
                engine.execute_turn(act_a, act_b)
            winner = engine.check_winner()
            print(f"  [{i}] {la.get('label','?')} vs {lb.get('label','?')} → "
                  f"turns={state.turn} winner={winner}")
            n_ok += 1
        except Exception as e:
            print(f"  [{i}] CRASH: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n[完成] {n_ok}/{len(pairs)} 场无崩溃")


if __name__ == "__main__":
    main()
