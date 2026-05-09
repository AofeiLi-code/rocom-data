"""
让 DeepSeek 协同分析 Top 18 缺失特性的战斗机制。
输出 JSON 报告到 tools/ability_analysis.json，供后续人工核对 + hook 实现。

用法: python tools/analyze_abilities.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.llm_agent import _call_llm


# 18 个待分析特性（从 sprites.json 的 ability.description 字段抽取，
# 跳过 #4 付给恶魔的赎价 / #14 最好的伙伴 — 描述空白）
ABILITIES = [
    ("不朽",       "力竭3回合后复活。",                                              "大头骨龙/寂灭骨龙"),
    ("预警",       "若敌方技能足够击败自己，回合开始时自己获得速度+50。",          "黑猫巫师"),
    ("泛音列",     "使用状态技能后，敌方获得【聒噪】技能的效果，持续3回合。",      "号儿鱼/圆号鱼"),
    ("哨兵",       "回合开始时若敌方技能足够击败自己，自己获得速度+50，行动后脱离。", "优优"),
    ("捉迷藏",     "使敌方获得冻结时，也会使其获得全技能能耗+1。",                "大耳帽兜"),
    ("冰钻",       "敌方携带技能总能耗每有1点，自己攻击时威力+10%。",              "冰钻布鲁斯"),
    ("灵魂灼伤",   "冰系技能使敌方获得4层灼烧，火系技能使敌方获得2层冻结。",       "九尾狐"),
    ("助燃",       "使用火系技能后，获得双攻+20%。",                              "火神"),
    ("稀兽花宝",   "根据自己的血脉，入场时获得不同效果。",                        "兽花蕾"),
    ("慢热型",     "初始能量为0，入场前己方精灵每成功应对1次，回复5能量。",       "瞌睡王"),
    ("陨落",       "在场时，双方回合结束时触发的效果，触发次数-1。",              "落陨星兔"),
    ("石头大餐",   "能量不足时，消耗5%生命，代替1能量。",                        "阿米亚特"),
    ("野性感官",   "应对成功后，下次行动先手+1。",                                "针叶巡林"),
    ("浸润",       "使用水系技能后，全技能能耗-1。",                              "水蓝蓝"),
    ("氧循环",     "使用草系技能后，回复10%生命。",                              "魔力猫"),
    ("吸积盘",     "回合结束时，敌方获得2层星陨印记。",                          "怖哭菇"),
    ("月牙雪糕",   "使用攻击技能时，敌方每层冻结视为1层额外星陨印记。",          "月牙雪熊"),
    ("对流",       "自己的能耗增加变为能耗降低；能耗降低变为能耗增加。",          "利灯鱼"),
]


SYSTEM = """你是洛克王国战斗模拟引擎的特性逻辑顾问。给定特性官方描述，
你需要把它翻译成可在 sim 引擎中实现的 hook 逻辑。

【可用的 hook 接入点】
- on_battle_start(state, engine)
- on_switch_in(state, engine, team, new_idx)
- on_switch_out(state, engine, team, old_idx, new_idx)
- on_faint(state, engine, team, fainted_p)
- get_priority_bonus(state, team, skill_idx, skill) -> 浮点；999 表示绝对先手
- get_attack_mods(state, engine, attacker, defender, skill, skill_idx, team, is_first)
    返回 AttackModContext(power_mult, power_flat_bonus)
- get_defense_mods(state, engine, attacker, defender, skill, attacker_team)
    返回减伤倍率列表（每项 0~1，多项乘算）
- on_post_attack(state, engine, attacker, defender, skill, skill_idx, actual_damage, team, counter_applied)
- on_use_defense_skill(state, engine, user, team)  # 任何防御技能使用后
- intercept_burn_decay(state, engine, pokemon) -> bool；True 表示烧伤增长
- get_extra_hit_count(state, attacker, skill, skill_idx) -> int  # 额外连击
- on_defender_damaged(state, engine, defender, old_hp, new_hp)
- apply_mark_damage(state, engine)
- on_turn_end(state, engine)  # 状态伤害之后、冷却递减之前
- on_turn_end_switches(state, engine)  # 回合结束的强制换人
- get_mark_energy_cost_mod(state, team, skill) -> int  # 印记带来的能耗修正
- get_mark_speed_penalty(state, team) -> float  # 印记带来的速度惩罚

【可访问的 Pokemon 字段】
hp, current_hp, energy, atk_boost/def_boost/spatk_boost/spdef_boost/speed_boost,
atk_reduce/.../speed_reduce, poison_stacks, burn_stacks, freeze_stacks,
entry_turn, hit_count_bonus, hp_milestone_flags, ability, skills, pokemon_type, secondary_type

【可访问的 BattleState 字段】
turn, lives_a, lives_b, weather, ability_counters (Dict[str, int]),
get_current(team), get_team(team), get_positive_mark(team), get_negative_mark(team),
set_mark(team, TeamMark), clear_mark(team, category)

【已实现示例（参考写法风格）】
- 暴食(翼龙)：龙系技能获先手
  → get_priority_bonus: if skill.skill_type == Type.DRAGON: return 999.0
- 渗透(棋绮后)：用武/地系技能后永久攻防+5%
  → on_post_attack: if skill.skill_type in (FIGHTING, GROUND): attacker.atk_boost += 0.05; ...
- 诈死(卡瓦重)：力竭少扣1格生命
  → on_faint: state.lives_X = min(state.lives_X + 1, 4)
- 嫁祸(朔夜伊芙)：HP 里程碑触发连击+2
  → on_defender_damaged + get_extra_hit_count，需要 hp_milestone_flags 状态字段

【输出要求】
对每个特性，输出 JSON 对象，字段：
- "ability": 特性名
- "mechanic": 一句话总结战斗机制（避免歧义）
- "hooks": 该特性需要挂在哪些 hook 上（数组）
- "needs_state": 是否需要在 Pokemon/BattleState 新增字段；新增的话说明字段名+用途
- "needs_new_hook": 现有 hook 是否够用？不够请说明需要什么新 hook
- "complexity": "low" | "medium" | "high"
- "ambiguity": 描述里有没有模糊或可能多解的地方？写下来
- "pseudocode": 用 Python 风格伪代码勾出关键逻辑（5~15 行）

只输出 JSON 数组，不要 markdown 代码块包裹，不要多余文字。"""


def main():
    abilities_block = "\n".join(
        f'{i+1}. 「{name}」（代表精灵: {sample}）：{desc}'
        for i, (name, desc, sample) in enumerate(ABILITIES)
    )
    user_msg = f"请逐一分析以下 18 个特性：\n\n{abilities_block}"

    print(f"[*] 发送 {len(ABILITIES)} 个特性给 DeepSeek 分析...")
    resp = _call_llm(
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        timeout=240,
    )

    # 尝试解析 JSON（剥掉可能的 markdown 包裹）
    text = resp.strip()
    if text.startswith("```"):
        # 去掉 ```json ... ```
        lines = text.splitlines()
        # 去首尾
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[!] JSON 解析失败: {e}")
        out_path = os.path.join(os.path.dirname(__file__), "ability_analysis_raw.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(resp)
        print(f"  原始回复已保存: {out_path}")
        return

    out_path = os.path.join(os.path.dirname(__file__), "ability_analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 解析结果已保存: {out_path}")
    print(f"     共 {len(data)} 条")


if __name__ == "__main__":
    main()
