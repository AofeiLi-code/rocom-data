"""
队伍图片解析器

将洛克王国标准组队分享图（含 6 只精灵 + 技能 + 队伍名）
通过 Claude Vision API 解析为结构化 JSON，
然后与本地数据库做校验，返回可直接存入名册的成员列表。

依赖：
  pip install anthropic

API Key：
  设置环境变量 ANTHROPIC_API_KEY，或在调用时传入 api_key 参数。
"""

import base64
import json
import os
import re
from pathlib import Path
from typing import Optional

# ============================================================
# 提示词
# ============================================================
_SYSTEM_PROMPT = """\
你是一个游戏数据识别助手，专门解析"洛克王国"游戏的队伍配置截图。
图片格式固定：右下角有队伍名称（如"队伍1"），\
图中有 6 只精灵，每只精灵卡片包含精灵名和 4 个技能名（技能图标正下方）。

只输出 JSON，不要输出任何解释文字。格式如下：
{
  "team_name": "队伍1",
  "members": [
    {"pokemon": "精灵名", "skills": ["技能1", "技能2", "技能3", "技能4"]},
    {"pokemon": "精灵名", "skills": ["技能1", "技能2", "技能3", "技能4"]},
    {"pokemon": "精灵名", "skills": ["技能1", "技能2", "技能3", "技能4"]},
    {"pokemon": "精灵名", "skills": ["技能1", "技能2", "技能3", "技能4"]},
    {"pokemon": "精灵名", "skills": ["技能1", "技能2", "技能3", "技能4"]},
    {"pokemon": "精灵名", "skills": ["技能1", "技能2", "技能3", "技能4"]}
  ]
}
members 数组必须恰好有 6 条，skills 数组必须恰好有 4 条。
"""

_USER_PROMPT = "请识别这张洛克王国队伍配置图，按要求格式输出 JSON。"


# ============================================================
# 图片编码
# ============================================================
def _encode_image(path: str) -> tuple[str, str]:
    """返回 (base64_data, media_type)"""
    suffix = Path(path).suffix.lower()
    media_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_map.get(suffix, "image/jpeg")
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


# ============================================================
# 主解析函数
# ============================================================
def parse_team_image(
    image_path: str,
    api_key: Optional[str] = None,
    model: str = "claude-opus-4-6",
) -> dict:
    """
    解析队伍配置图片，返回原始识别结果 dict。

    Parameters
    ----------
    image_path : 图片文件路径
    api_key    : Anthropic API Key（None 时读取环境变量 ANTHROPIC_API_KEY）
    model      : 使用的 Claude 模型，默认 claude-opus-4-6

    Returns
    -------
    {
      "team_name": str,
      "members": [{"pokemon": str, "skills": [str, str, str, str]}, ...]
    }

    Raises
    ------
    EnvironmentError : API Key 未配置
    ValueError       : API 返回内容无法解析为合法 JSON
    FileNotFoundError: 图片文件不存在
    """
    import anthropic  # 延迟导入，未安装时给出清晰提示

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "未找到 ANTHROPIC_API_KEY。\n"
            "请设置环境变量：set ANTHROPIC_API_KEY=sk-ant-..."
        )

    img_data, media_type = _encode_image(image_path)

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_data,
                        },
                    },
                    {"type": "text", "text": _USER_PROMPT},
                ],
            }
        ],
    )

    raw_text = message.content[0].text.strip()

    # 从返回文本中提取 JSON（防止模型多输出了解释文字）
    json_match = re.search(r'\{[\s\S]+\}', raw_text)
    if not json_match:
        raise ValueError(f"API 返回内容中未找到 JSON：\n{raw_text[:300]}")

    try:
        result = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败：{e}\n原始内容：\n{raw_text[:300]}")

    # 基本结构校验
    if "members" not in result:
        raise ValueError(f"返回 JSON 缺少 members 字段：{result}")

    return result


# ============================================================
# 数据库校验与模糊修正
# ============================================================
def validate_and_fix(parsed: dict) -> dict:
    """
    对解析结果做数据库校验，返回带校验报告的增强结构。

    Returns
    -------
    {
      "team_name": str,
      "members": [...],          # 校验后的成员列表（名称已尽量修正）
      "warnings": [str, ...],    # 未能匹配的警告信息
      "ok": bool                 # True = 所有精灵和技能均在数据库中
    }
    """
    from sim.pokemon_db import get_pokemon, get_all_pokemon_names, load_pokemon_db
    from sim.skill_db import load_skills, get_all_skills

    load_pokemon_db()
    load_skills()

    all_pokemon = get_all_pokemon_names()
    all_skills = set(get_all_skills().keys())
    warnings = []
    fixed_members = []

    for i, member in enumerate(parsed.get("members", []), 1):
        raw_name = member.get("pokemon", "")
        raw_skills = member.get("skills", [])

        # --- 精灵名校验与模糊修正 ---
        fixed_name = raw_name
        if not get_pokemon(raw_name):
            # 尝试模糊匹配
            candidates = [n for n in all_pokemon if raw_name in n or n in raw_name]
            if candidates:
                fixed_name = candidates[0]
                warnings.append(
                    f"第{i}只：「{raw_name}」→ 模糊匹配为「{fixed_name}」"
                )
            else:
                warnings.append(
                    f"第{i}只：「{raw_name}」未在数据库中找到，请手动修正"
                )

        # --- 技能校验与模糊修正 ---
        fixed_skills = []
        for skill_name in raw_skills:
            if skill_name in all_skills:
                fixed_skills.append(skill_name)
            else:
                # 模糊匹配
                candidates = [s for s in all_skills if skill_name in s or s in skill_name]
                if candidates:
                    fixed_skills.append(candidates[0])
                    warnings.append(
                        f"第{i}只技能：「{skill_name}」→ 模糊匹配为「{candidates[0]}」"
                    )
                else:
                    fixed_skills.append(skill_name)  # 保留原名，让用户知晓
                    warnings.append(
                        f"第{i}只技能：「{skill_name}」未在技能库中找到"
                    )

        # 补足或截断到 4 个
        while len(fixed_skills) < 4:
            fixed_skills.append("")
        fixed_skills = fixed_skills[:4]

        fixed_members.append({"pokemon": fixed_name, "skills": fixed_skills})

    # 补足到 6 只
    while len(fixed_members) < 6:
        fixed_members.append({"pokemon": "", "skills": ["", "", "", ""]})
        warnings.append(f"识别结果不足 6 只精灵，已补空位（请手动修正）")

    return {
        "team_name": parsed.get("team_name", "导入队伍"),
        "members": fixed_members[:6],
        "warnings": warnings,
        "ok": len(warnings) == 0,
    }


# ============================================================
# 一步到位：解析 + 校验
# ============================================================
def parse_and_validate(
    image_path: str,
    api_key: Optional[str] = None,
) -> dict:
    """解析图片并做数据库校验，返回带 warnings 的完整结果"""
    parsed = parse_team_image(image_path, api_key=api_key)
    return validate_and_fix(parsed)
