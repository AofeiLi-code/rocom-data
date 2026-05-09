"""
Human Agent — 终端交互决策

每回合显示战场状态和合法动作列表，读取用户输入后返回 Action。
实现 AgentProtocol 协议。
"""

from typing import List, Optional

from sim.battle_engine import BattleEngine, Action
from sim.pokemon import Pokemon


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


def _print_field(state, label_you: str, label_opp: str) -> None:
    pa = state.get_current("a")
    pb = state.get_current("b")
    weather_str = f"  天气:{state.weather.value}" if state.weather.value != "none" else ""
    lives_a = state.lives_a
    lives_b = state.lives_b
    print(f"\n{'─' * 56}  回合 {state.turn}{weather_str}")
    print(
        f"  {label_you}: {pa.name:<10} {_hp_bar(pa.current_hp, pa.hp)}  "
        f"能量:{pa.energy:2}  生命格:{lives_a}  {_status_flags(pa)}"
    )
    print(
        f"  {label_opp}: {pb.name:<10} {_hp_bar(pb.current_hp, pb.hp)}  "
        f"能量:{pb.energy:2}  生命格:{lives_b}  {_status_flags(pb)}"
    )


def _print_team_summary(label: str, team: list) -> None:
    print(f"\n  {label}:")
    for i, p in enumerate(team):
        s = "已倒下" if p.is_fainted else f"HP {p.current_hp}/{p.hp}"
        print(f"    [{i}] {p.name:<12} {s}")


def _print_actions(engine: BattleEngine, team: str) -> dict:
    """打印合法动作列表，返回 (编号->Action) 映射"""
    actions = engine.get_actions(team)
    current = engine.state.get_current(team)
    print(f"\n  === {current.name} — 可选动作 ===")

    mapping = {}
    for idx, action in enumerate(actions, 1):
        if len(action) == 1 and action[0] == -1:
            label = "汇合聚能（回复5点能量）"
        elif len(action) >= 2 and action[0] == -2:
            target_idx = action[1]
            team_list = engine.state.get_team(team)
            target = team_list[target_idx]
            label = f"切换 -> {target.name} (HP:{target.current_hp}/{target.hp})"
        else:
            skill_idx = action[0]
            skill = current.skills[skill_idx]
            cost = engine._get_effective_energy_cost(skill, team)
            category_label = {
                "物攻": "物",
                "魔攻": "魔",
                "防御": "防",
                "状态": "状",
            }.get(skill.category.value, skill.category.value)
            label = f"{skill.name}（{category_label}，威力{skill.power}，能耗{cost}"
            if hasattr(engine.state.get_current(team), 'cooldowns'):
                cd = engine.state.get_current(team).cooldowns.get(skill_idx, 0)
                if cd > 0:
                    label += f" CD:{cd}"
            # 特殊效果提示
            effects = []
            if skill.life_drain:    effects.append(f"吸血{int(skill.life_drain*100)}%")
            if skill.damage_reduction: effects.append(f"减伤{int(skill.damage_reduction*100)}%")
            if skill.self_heal_hp:  effects.append(f"回血{int(skill.self_heal_hp*100)}%")
            if skill.poison_stacks: effects.append(f"中毒{skill.poison_stacks}")
            if skill.burn_stacks:   effects.append(f"灼烧{skill.burn_stacks}")
            if skill.freeze_stacks: effects.append(f"冻结{skill.freeze_stacks}")
            if skill.steal_energy:  effects.append(f"偷能{skill.steal_energy}")
            if skill.force_switch:  effects.append("脱离")
            if skill.agility:       effects.append("迅捷")
            if skill.charge:        effects.append("蓄力")
            if effects:
                label += " [" + ",".join(effects) + "]"
            label += ")"
        mapping[idx] = action
        print(f"    {idx}. {label}")

    return mapping


def _read_choice(mapping: dict) -> Action:
    """读取用户输入，返回对应的 Action"""
    while True:
        try:
            raw = input("  输入序号: ").strip()
            if not raw:
                continue
            choice = int(raw)
            if choice in mapping:
                return mapping[choice]
            print(f"  [!] 无效序号，请输入 1-{len(mapping)}")
        except ValueError:
            print("  [!] 请输入数字")


class HumanAgent:
    """
    人类玩家代理 — 每回合通过终端交互选择动作。
    实现 AgentProtocol 协议（含 show_team_status = True）。

    Parameters
    ----------
    team : "a" 或 "b"
    label : 显示在战场上的队伍名称
    """

    show_team_status: bool = True

    def __init__(self, team: str, label: str):
        self.team = team
        self.label = label

    # ------------------------------------------------------------------
    # AgentProtocol — choose_action
    # ------------------------------------------------------------------

    def choose_action(self, engine: BattleEngine) -> Action:
        """显示状态，读取用户输入，返回 Action。"""
        is_a = self.team == "a"
        label_opp = engine.label_b if is_a else engine.label_a
        _print_field(engine.state, f"{self.label}(你)", label_opp)
        mapping = _print_actions(engine, self.team)
        return _read_choice(mapping)

    # ------------------------------------------------------------------
    # AgentProtocol — on_game_end（人类玩家不记录经验）
    # ------------------------------------------------------------------

    def on_game_end(self, history: list, winner: Optional[str]) -> None:
        """战斗结束时打印结果。"""
        pass  # battle.py 会统一打印结果
