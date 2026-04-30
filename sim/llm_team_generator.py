"""
LLM 队伍生成器 — 使用大模型分析经验数据，生成优化后的精灵阵容和策略文件

功能：
- 读取 MCTS 历史对战经验（ExperienceDB）
- 调用 LLM 分析胜率数据、属性克制关系
- 生成新的精灵组合建议 + 技能配置 + 策略 YAML
- 保存到队伍名册中
"""

import json
import os
from typing import Optional, List, Dict

import yaml as _yaml

from sim.llm_agent import _call_llm, _load_llm_config

# ============================================================
# 路径常量
# ============================================================

_STRATEGY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "strategies",
)

_EXPERIENCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "experience",
)

_ROSTER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "teams.json",
)

_SPRITES_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "sprites.json",
)

# ============================================================
# 数据加载辅助
# ============================================================

def _load_sprites_db() -> List[Dict]:
    """读取精灵数据库，返回精简信息（名字、属性、六维）。"""
    if not os.path.exists(_SPRITES_DB):
        return []
    with open(_SPRITES_DB, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = []
    for sprite in data:
        stats = sprite.get("stats", {})
        attrs = sprite.get("attributes", [])
        primary_type = attrs[0] if attrs else "未知"
        secondary_type = attrs[1] if len(attrs) > 1 else ""
        skills_list = [s.get("name", "") for s in sprite.get("skills", [])]

        info = {
            "name": sprite.get("name", ""),
            "primary_type": primary_type,
            "secondary_type": secondary_type,
            "hp": stats.get("hp", 0),
            "attack": stats.get("atk", 0),
            "defense": stats.get("def", 0),
            "sp_attack": stats.get("sp_atk", 0),
            "sp_defense": stats.get("sp_def", 0),
            "speed": stats.get("spd", 0),
            "total": stats.get("total", 0),
            "ability": sprite.get("ability", {}).get("name", ""),
            "skills": skills_list,
        }
        result.append(info)
    return result


def _load_experience_summary() -> Dict:
    """
    读取所有 MCTS 经验文件，汇总胜率统计。
    返回 {team_name: {total_games, total_wins_a, ...}}
    """
    summary = {}
    if not os.path.exists(_EXPERIENCE_DIR):
        return summary

    for fname in os.listdir(_EXPERIENCE_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(_EXPERIENCE_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            team_name = fname.replace(".json", "")
            # 经验格式: {state_key: {action_key: {wins: X, total: Y}, ...}, ...}
            summary[team_name] = {
                "total_keys": len(data),
                "path": path,
            }
        except (json.JSONDecodeError, IOError):
            pass
    return summary


# ============================================================
# LLM 队伍生成
# ============================================================

def generate_team_with_llm(
    theme: Optional[str] = None,
) -> Optional[Dict]:
    """
    调用 LLM 生成一个新的精灵阵容。

    Parameters
    ----------
    theme : 主题/风格（如 "高速控制队", "重火力输出队", None=自由发挥）

    Returns
    -------
    队伍定义 dict，格式与 teams.json 中的条目一致；失败返回 None。
    """
    sprites = _load_sprites_db()
    exp_summary = _load_experience_summary()

    # 构建精灵列表（精简，只保留关键信息）
    sprite_lines = []
    # 按总战力排序，取前 80 只
    sorted_sprites = sorted(sprites, key=lambda s: s.get("total", 0), reverse=True)[:80]
    for s in sorted_sprites:
        primary = s.get("primary_type", "")
        secondary = s.get("secondary_type", "")
        type_str = primary + ("+" + secondary if secondary else "")
        ability = s.get("ability", "")
        skills = ", ".join(s.get("skills", [])[:4])  # 只取前4个技能
        sprite_lines.append(
            f"{s['name']}: 属性={type_str}, "
            f"HP{s['hp']} ATK{s['attack']} DEF{s['defense']} "
            f"SPATK{s['sp_attack']} SPDEF{s['sp_defense']} SPD{s['speed']} "
            f"总计{s['total']}, 特性={ability}, 技能=[{skills}]"
        )

    # 经验摘要
    exp_lines = []
    for team, info in exp_summary.items():
        exp_lines.append(f"- {team}: {info['total_keys']} 个状态记录")

    system_prompt = """你是洛克王国手游的阵容设计专家。请根据提供的精灵数据库和已有队伍经验，
设计一支新的6人精灵阵容。

胜利条件：每方4格生命格，精灵倒下-1格，归零判负。
核心机制：同时行动制、速度决定先后手、能量系统(初始10, 技能消耗2-8)、属性克制。

你必须返回严格的 JSON 格式:
{{
    "team_name": "队伍名称",
    "theme": "阵容风格描述",
    "members": [
        {{"pokemon": "精灵名", "skills": ["技能1", "技能2", "技能3", "技能4"]}}
    ],
    "strategy_notes": "简短的战术说明（100字以内）"
}}

要求：
- 6只精灵，每只4个技能
- 属性搭配合理（攻防兼备、有控场能力）
- 考虑前后排轮换策略
- 精灵名必须在提供的列表中
- 只返回 JSON，不要包含其他文本"""

    theme_hint = f"\n\n用户指定的主题: {theme}"
    user_msg = (
        "=== 可用精灵 ===\n"
        + "\n".join(sprite_lines[:200])   # 限制长度，避免 prompt 过长
        + f"\n(共 {len(sorted_sprites)} 只精灵，已按总战力排序取前80)"
        + (f"\n\n=== 已有队伍经验 ===\n{chr(10).join(exp_lines)}" if exp_lines else "")
        + theme_hint
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    try:
        content = _call_llm(messages, temperature=0.7)
        if not content or len(content.strip()) < 10:
            print(f"  [LLM] LLM 返回空内容，重试...")
            # 第二次尝试，降低温度
            content = _call_llm(messages, temperature=0.3)
        result = json.loads(content)

        # 验证返回格式
        if not isinstance(result.get("members"), list) or len(result["members"]) < 4:
            print(f"  [LLM] 生成的队伍格式不正确: {result.get('team_name', '未知')}")
            return None

        # 补充 preset=false
        result["preset"] = False
        return result

    except json.JSONDecodeError as e:
        print(f"  [LLM] JSON解析失败: {e}\n原始内容前200字符: {content[:200] if 'content' in dir() else 'N/A'}")
        return None
    except Exception as e:
        print(f"  [LLM] 生成队伍失败: {e}")
        return None


# ============================================================
# LLM 策略文件生成
# ============================================================

def generate_strategy_with_llm(
    team_name: str,
) -> Optional[Dict]:
    """
    调用 LLM 为指定队伍生成策略 YAML 数据。

    Parameters
    ----------
    team_name : 队伍名称（必须在 teams.json 中存在）

    Returns
    -------
    策略 dict（可写入 YAML），失败返回 None。
    """
    # 读取队伍定义
    if not os.path.exists(_ROSTER_PATH):
        print(f"  [LLM] 找不到队伍名册: {_ROSTER_PATH}")
        return None

    with open(_ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)

    team_def = None
    for t in roster:
        if t["name"] == team_name:
            team_def = t
            break

    if team_def is None:
        print(f"  [LLM] 找不到队伍「{team_name}」")
        return None

    # 读取策略模板
    template_path = os.path.join(_STRATEGY_DIR, "_template.yaml")
    template_info = ""
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            template_info = f.read()[:500]

    # 读取 LLM 经验文档
    from sim.llm_agent import _load_experience
    llm_exp = _load_experience(team_name) or []
    exp_text = ""
    if llm_exp:
        lines = ["=== 历史对战经验 ==="]
        for exp in llm_exp[-5:]:
            result = exp.get("result", "未知")
            summary = exp.get("summary", "")[:100]
            lessons = exp.get("lessons", [])
            lesson_str = "; ".join(str(l) for l in lessons)[:200] if isinstance(lessons, list) else str(lessons)[:200]
            lines.append(f"- 结果: {result} | 总结: {summary}")
            if lesson_str:
                lines.append(f"  教训: {lesson_str}")
        exp_text = "\n".join(lines)

    system_prompt = (
        f"你是洛克王国手游的策略设计师。请为队伍「{team_name}」生成一份策略配置文件。"
        f"\n\n该队伍的阵容:\n"
        + json.dumps(team_def["members"], ensure_ascii=False, indent=2)
        + (f"\n\n{exp_text}" if exp_text else "")
        + "\n\n策略文件用于 MCTS AI 的权重调整，格式如下（YAML）："
        "\n- prefer: 明确推荐的动作类型列表（如 ['attack', 'switch']）"
        "\n- avoid: 明确排斥的动作类型列表"
        "\n- conditions: 条件判断规则（hp_low, type_advantage, energy_low 等）"
        "\n- priorities: 优先级设置"
        + "\n\n你只需要返回 JSON 格式的策略数据："
        '{"prefer": ["动作1", "动作2"], "avoid": ["动作3"], '
        '"conditions": [{"when": "hp_low", "action": "switch"}], '
        '"notes": "策略说明"}'
        + "\n\n只返回 JSON，不要包含其他文本。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请为队伍「{team_name}」生成策略配置。"},
    ]

    try:
        content = _call_llm(messages, temperature=0.5)
        result = json.loads(content)
        return result
    except Exception as e:
        print(f"  [LLM] 生成策略失败: {e}")
        return None


# ============================================================
# 保存生成的队伍/策略到磁盘
# ============================================================

def save_generated_team(team_def: Dict) -> bool:
    """
    将 LLM 生成的队伍保存到 teams.json。
    """
    if not os.path.exists(_ROSTER_PATH):
        print(f"  [!] 找不到队伍名册")
        return False

    with open(_ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)

    # 检查是否已存在同名
    for i, t in enumerate(roster):
        if t["name"] == team_def["name"]:
            print(f"  [!] 队伍「{team_def['name']}」已存在，将覆盖")
            roster[i] = team_def
            break
    else:
        roster.append(team_def)

    with open(_ROSTER_PATH, "w", encoding="utf-8") as f:
        json.dump(roster, f, ensure_ascii=False, indent=2)

    print(f"  [OK] 队伍「{team_def['name']}」已保存")
    return True


def save_generated_strategy(team_name: str, strategy_data: Dict) -> bool:
    """
    将 LLM 生成的策略保存到 strategies/ 目录。
    """
    os.makedirs(_STRATEGY_DIR, exist_ok=True)
    path = os.path.join(_STRATEGY_DIR, f"{team_name}.yaml")

    with open(path, "w", encoding="utf-8") as f:
        _yaml.dump(strategy_data, f, allow_unicode=True, default_flow_style=False)

    print(f"  [OK] 策略文件已保存: {path}")
    return True
