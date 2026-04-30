"""
LLM Agent — 通过 OpenAI 兼容 API 的大模型战斗智能体

实现 AgentProtocol，每回合将战场状态序列化为文本发送给大模型，
解析其 JSON 回复得到 Action。

支持：
- 对战决策（逐回合选择动作）
- 战后经验文档生成
- 战前经验加载作为上下文
"""

import json
import os
import time
from typing import Optional, List, Dict, Any

import requests
import yaml as _yaml

from sim.battle_engine import BattleEngine, Action
from sim.battle_state import BattleState
from sim.pokemon import Pokemon
from sim.skill import Skill
from sim.types import StatusType

# ============================================================
# 配置加载
# ============================================================

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "llm_config.yaml",
)

_EXPERIENCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "llm_experience",
)


def _load_llm_config() -> Dict:
    """加载 LLM 配置文件。找不到或格式错误时抛出 EnvironmentError。"""
    if not os.path.exists(_CONFIG_PATH):
        raise EnvironmentError(
            f"LLM 配置文件不存在: {_CONFIG_PATH}\n"
            f"请在 data/llm_config.yaml 中配置 endpoint、model、api_key"
        )
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = _yaml.safe_load(f)
    required = ["endpoint", "model", "api_key"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise EnvironmentError(
            f"LLM 配置缺少必要字段: {missing}\n"
            f"请在 data/llm_config.yaml 中补充 endpoint、model、api_key"
        )
    return cfg


# ============================================================
# HTTP 请求工具
# ============================================================

def _call_llm(
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    timeout: Optional[int] = None,
) -> str:
    """
    调用 OpenAI 兼容 API，返回 assistant 的回复文本。
    """
    cfg = _load_llm_config()
    url = f"{cfg['endpoint']}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
    }

    # 使用配置的超时值（如果未显式指定）
    if timeout is None:
        timeout = int(cfg.get("timeout", 120))

    t0 = time.time()
    # 内网/本地端点不经过系统代理
    if cfg["endpoint"].startswith("http://"):
        # requests 在某些环境下即使 proxies={} 也会走系统代理，
        # 需要临时清除环境变量
        import os as _os
        proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
        saved = {}
        for v in proxy_vars:
            if v in _os.environ:
                saved[v] = _os.environ[v]
                del _os.environ[v]
        try:
            resp = requests.post(url, json=payload, headers=headers,
                                timeout=timeout)
        finally:
            for v, val in saved.items():
                _os.environ[v] = val
    else:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    elapsed = time.time() - t0
    print(f"  [LLM] API调用耗时 {elapsed:.1f}s")

    if resp.status_code != 200:
        raise EnvironmentError(
            f"LLM API 请求失败: HTTP {resp.status_code}\n"
            f"响应: {resp.text[:500]}"
        )

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return content.strip()


def _parse_action(content: str) -> Action:
    """
    解析 LLM 返回的 JSON，提取 action 字段。
    格式: {"action": [skill_idx], "reasoning": "..."}
          {"action": [-1], "reasoning": "..."}       # 汇合聚能
          {"action": [-2, target_idx], "reasoning": "..."}  # 切换精灵
    """
    # 尝试从内容中提取 JSON（处理可能包含 Markdown 代码块的情况）
    import re
    json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', content)
    if json_match:
        content = json_match.group(0)

    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        # 尝试提取最外层的 JSON 对象
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                obj = json.loads(content[start:end])
            except json.JSONDecodeError:
                print(f"  [LLM] JSON解析失败，原始内容: {content[:200]}")
                raise
        else:
            print(f"  [LLM] JSON解析失败，无法找到 JSON 对象: {content[:200]}")
            raise

    action_list = obj.get("action")
    if action_list is None or not isinstance(action_list, list):
        raise ValueError(f"LLM返回缺少 'action' 字段: {obj}")

    # 转换为 tuple
    return tuple(int(x) for x in action_list)


# ============================================================
# 战场状态序列化
# ============================================================

def _status_name(s: StatusType) -> str:
    mapping = {
        StatusType.NORMAL: "正常",
        StatusType.POISONED: "中毒",
        StatusType.BURNED: "灼烧",
        StatusType.PARALYZED: "麻痹",
        StatusType.FROZEN: "冻结",
        StatusType.SLEEP: "睡眠",
        StatusType.CONFUSED: "混乱",
    }
    return mapping.get(s, s.value)


def _serialize_pokemon(p: Pokemon, idx: int) -> Dict:
    hp_pct = round(p.current_hp / p.hp * 100, 1) if p.hp > 0 else 0.0
    skills_info = []
    for si, sk in enumerate(p.skills):
        cd = p.cooldowns.get(si, 0)
        skills_info.append({
            "idx": si,
            "name": sk.name,
            "power": sk.power,
            "cost": sk.energy_cost,
            "category": sk.category.value,
            "cd": cd if cd > 0 else None,
        })
    return {
        "idx": idx,
        "name": p.name,
        "hp_pct": hp_pct,
        "hp_raw": f"{p.current_hp}/{p.hp}",
        "energy": p.energy,
        "is_fainted": p.is_fainted,
        "burn_stacks": p.burn_stacks,
        "poison_stacks": p.poison_stacks,
        "freeze_stacks": p.freeze_stacks,
        "skills": skills_info,
    }


def _serialize_battle_state(engine: BattleEngine, my_team_id: str) -> Dict:
    """
    将当前战场状态序列化为字典（可 JSON 序列化）。
    """
    state = engine.state
    enemy_id = "b" if my_team_id == "a" else "a"

    return {
        "turn": state.turn,
        "weather": state.weather.value,
        "weather_turns_left": max(0, state.weather_turns),
        "my_lives": state.lives_a if my_team_id == "a" else state.lives_b,
        "enemy_lives": state.lives_b if my_team_id == "a" else state.lives_a,
        "my_team": [
            _serialize_pokemon(p, i)
            for i, p in enumerate(state.get_team(my_team_id))
        ],
        "enemy_team": [
            _serialize_pokemon(p, i)
            for i, p in enumerate(state.get_team(enemy_id))
        ],
    }


# ============================================================
# 经验文档管理
# ============================================================

def _experience_path(team_name: str) -> str:
    return os.path.join(_EXPERIENCE_DIR, f"{team_name}.json")


def _load_experience(team_name: str) -> Optional[List[Dict]]:
    """加载队伍的历史经验文档列表。"""
    path = _experience_path(team_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兼容旧格式（单条记录）
        if isinstance(data, dict):
            return [data]
        return data
    except (json.JSONDecodeError, IOError):
        return None


def _save_experience(team_name: str, experience: Dict) -> None:
    """
    追加一条经验文档到队伍的经验文件。
    保留最近 50 条（防止无限增长）。
    """
    os.makedirs(_EXPERIENCE_DIR, exist_ok=True)
    path = _experience_path(team_name)

    existing = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                existing = [data]
            elif isinstance(data, list):
                existing = data
        except (json.JSONDecodeError, IOError):
            pass

    # 添加时间戳
    experience["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    existing.append(experience)

    # 只保留最近 50 条
    if len(existing) > 50:
        existing = existing[-50:]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def _format_experience_for_prompt(experiences: List[Dict]) -> str:
    """
    将经验文档格式化为简短的提示文本（不超过 1000 字符）。
    """
    if not experiences:
        return ""

    lines = ["=== 历史对战经验 ==="]
    # 只取最近 5 条
    recent = experiences[-5:]
    for exp in recent:
        result = exp.get("result", "未知")
        summary = exp.get("summary", "")[:100]
        lesson = exp.get("lessons", [""])[0][:200] if isinstance(exp.get("lessons"), list) else str(exp.get("lessons", ""))[:200]
        lines.append(f"- 结果: {result} | 总结: {summary}")
        if lesson:
            lines.append(f"  教训: {lesson}")

    return "\n".join(lines)


# ============================================================
# LLM Agent
# ============================================================

class LLMAgent:
    """
    大模型战斗智能体 — 每回合通过 HTTP API 调用大模型做决策。

    Parameters
    ----------
    team : "a" 或 "b"
    team_name : 队伍名称（用于经验文档存储和策略加载）
    temperature : LLM 温度参数，默认从配置文件读取
    """

    show_team_status: bool = False  # AI 模式，由引擎打印日志

    def __init__(self, team: str, team_name: str, temperature: Optional[float] = None):
        self.team = team
        self.team_name = team_name
        self._config = _load_llm_config()
        self.temperature = temperature if temperature is not None else float(self._config.get("temperature", 0.3))
        self.timeout = int(self._config.get("timeout", 30))

        # 加载历史经验文档
        self._experiences = _load_experience(team_name)
        if self._experiences:
            print(f"  [LLM] {team_name}（{team}）加载了 {len(self._experiences)} 条历史经验")
        else:
            print(f"  [LLM] {team_name}（{team}）无历史经验，从头开始")

    # ------------------------------------------------------------------
    # AgentProtocol — choose_action
    # ------------------------------------------------------------------

    def choose_action(self, engine: BattleEngine) -> Action:
        """
        将战场状态发送给 LLM，解析回复得到 Action。
        """
        state = _serialize_battle_state(engine, self.team)
        enemy_id = "b" if self.team == "a" else "a"

        # 构建系统提示
        system_prompt = self._build_system_prompt(state)

        # 构建用户消息（战场状态 + 经验）
        user_msg = self._build_user_message(state, enemy_id)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        try:
            content = _call_llm(messages, self.temperature, self.timeout)
            action = _parse_action(content)
            print(f"  [LLM] 选择动作: {action}")
            return action
        except Exception as e:
            print(f"  [LLM] 决策失败: {e}，回退到汇合聚能")
            return (-1,)

    # ------------------------------------------------------------------
    # AgentProtocol — on_game_end
    # ------------------------------------------------------------------

    def on_game_end(self, history: list, winner: Optional[str]) -> None:
        """
        战斗结束后，调用 LLM 生成经验文档并保存。
        """
        result = {
            "a": f"{self.team_name} 胜利",
            "b": f"对手胜利",
            None: "平局/超时",
        }.get(winner, "未知")

        # 构建战后分析提示
        state = _serialize_battle_state(
            type('FakeEngine', (), {'state': history[-1][0] if history else None})(),
            self.team,
        ) if history else {}

        try:
            analysis = self._generate_post_battle_analysis(result, history)
            experience = {
                "team_name": self.team_name,
                "result": result,
                "winner": winner,
                "summary": analysis.get("summary", ""),
                "lessons": analysis.get("lessons", []),
                "turns": len(history),
            }
            _save_experience(self.team_name, experience)
            print(f"  [LLM] {self.team_name} 经验文档已保存")
        except Exception as e:
            print(f"  [LLM] 生成经验文档失败: {e}")

    # ------------------------------------------------------------------
    # Prompt 构建
    # ------------------------------------------------------------------

    def _build_system_prompt(self, state: Dict) -> str:
        return f"""你是洛克王国战斗AI。返回严格JSON: {{"action":[技能索引] 或 [-1]汇合聚能 或 [-2,精灵索引]换人}}。
动作编码: [N]=用第N个技能(从0开始), [-1]=聚能(+5能量), [-2,N]=切到后备精灵索引N。"""

    def _build_user_message(self, state: Dict, enemy_id: str) -> str:
        parts = []
        # 我方队伍
        for p in state["my_team"]:
            st = ""
            if p.get("burn_stacks", 0):   st += f"灼烧{p['burn_stacks']} "
            if p.get("poison_stacks", 0): st += f"中毒{p['poison_stacks']} "
            if p.get("freeze_stacks", 0): st += f"冻结{p['freeze_stacks']} "
            sk = ",".join(f"[{s['idx']}]={s['name']}({s['category']},威{s['power']},耗{s['cost']})"
                for s in p["skills"])
            parts.append(f"我[{p['idx']}] {p['name']} HP:{p['hp_pct']}% E:{p['energy']} {'|' if st else ''}{st} 技能:[{sk}]")
        # 对手
        for p in state["enemy_team"]:
            parts.append(f"敌[{p['idx']}] {p['name']} HP:{p['hp_pct']}% E:{p['energy']} {'倒' if p.get('is_fainted') else '活'}")
        # 经验
        exp_text = _format_experience_for_prompt(self._experiences or [])
        if exp_text:
            parts.append(exp_text)
        return "\n".join(parts)

    def _generate_post_battle_analysis(self, result: str, history: list) -> Dict:
        """
        调用 LLM 生成战后分析文档。
        """
        system = """你是洛克王国手游的战斗分析师。请根据对战记录生成简短的经验总结。

返回严格的 JSON 格式:
- "summary": 一句话概括本局对战的关键点（50字以内）
- "lessons": 2-3条经验教训列表，每条100字以内

只返回 JSON，不要包含其他文本。"""

        # 构建对战记录摘要
        if history:
            last_state = history[-1][0] if history else None
            turn_count = len(history)
            summary_text = f"\n本局共 {turn_count} 回合，结果: {result}。"
        else:
            turn_count = 0
            summary_text = "\n本局对战无有效记录。"

        user_msg = f"请分析以下对战并生成经验总结:{summary_text}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

        content = _call_llm(messages, 0.5, self.timeout)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            print(f"  [LLM] 经验分析 JSON 解析失败: {content[:200]}")
            return {"summary": "JSON解析失败", "lessons": []}

    # ------------------------------------------------------------------
    # 保存经验（兼容 MCTSAgent 接口）
    # ------------------------------------------------------------------

    def save(self) -> str:
        """LLM Agent 不记录 MCTS 经验，此方法为空操作。"""
        return ""
