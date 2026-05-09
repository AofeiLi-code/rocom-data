"""
LLM 战斗聚合复盘 — 基于 battle_log_records 中最近 N 场对战
（最多 100），让 LLM 总结胜率原因、识别队伍模式弱点并给出改阵建议。

核心入口：analyze_team_aggregate(team_name, n, opponent=None) -> str
"""

from typing import List, Dict, Any, Optional, Tuple

from sim.data_store import DataStore, get_engine, BattleLogRecord, get_config
from sqlalchemy.orm import sessionmaker


MAX_BATCHES = 100
MAX_LOSS_SAMPLES = 4          # 详细分析最多抽样几场失败
LOG_SAMPLE_CHARS = 1500       # 每场失败抽样日志字符数上限


# ============================================================
# 数据采集
# ============================================================

def _fetch_recent_for_team(
    team_name: str,
    n: int,
    opponent: Optional[str] = None,
) -> List[BattleLogRecord]:
    """从数据库拉取该队最近 n 场（含胜负）。"""
    config = get_config()
    engine = get_engine(config)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        from sqlalchemy import or_, and_
        q = session.query(BattleLogRecord)
        if opponent:
            q = q.filter(or_(
                and_(BattleLogRecord.team_a_name == team_name,
                     BattleLogRecord.team_b_name == opponent),
                and_(BattleLogRecord.team_a_name == opponent,
                     BattleLogRecord.team_b_name == team_name),
            ))
        else:
            q = q.filter(or_(
                BattleLogRecord.team_a_name == team_name,
                BattleLogRecord.team_b_name == team_name,
            ))
        return q.order_by(BattleLogRecord.created_at.desc()).limit(n).all()
    finally:
        session.close()


# ============================================================
# 单条记录视角化（以 team_name 视角统一为「我方/对手」）
# ============================================================

def _perspective(rec: BattleLogRecord, team_name: str) -> Dict[str, Any]:
    """把一场对战转成「我方=team_name」视角的精简字典。"""
    import json as _json
    if rec.team_a_name == team_name:
        my_side, opp_side = "a", "b"
        opponent = rec.team_b_name
        my_lineup = _json.loads(rec.team_a_lineup)
        opp_lineup = _json.loads(rec.team_b_lineup)
    else:
        my_side, opp_side = "b", "a"
        opponent = rec.team_a_name
        my_lineup = _json.loads(rec.team_b_lineup)
        opp_lineup = _json.loads(rec.team_a_lineup)

    if rec.winner == my_side:
        outcome = "win"
    elif rec.winner == opp_side:
        outcome = "loss"
    else:
        outcome = "draw"

    final = _json.loads(rec.final_state)
    my_team_state = final.get("team_a") if my_side == "a" else final.get("team_b")
    opp_team_state = final.get("team_b") if my_side == "a" else final.get("team_a")
    my_lives = final.get("lives_a") if my_side == "a" else final.get("lives_b")
    opp_lives = final.get("lives_b") if my_side == "a" else final.get("lives_a")

    return {
        "id": rec.id,
        "opponent": opponent,
        "outcome": outcome,
        "turns": rec.turns,
        "my_lineup": my_lineup,
        "opp_lineup": opp_lineup,
        "my_lives_remaining": my_lives,
        "opp_lives_remaining": opp_lives,
        "my_team_final": my_team_state,
        "opp_team_final": opp_team_state,
        "log_text": rec.log_text or "",
        "created_at": str(rec.created_at),
    }


# ============================================================
# 聚合统计
# ============================================================

def _aggregate(perspectives: List[Dict[str, Any]]) -> Dict[str, Any]:
    """对一批 perspective 视角化记录做聚合统计。"""
    n = len(perspectives)
    wins = sum(1 for p in perspectives if p["outcome"] == "win")
    losses = sum(1 for p in perspectives if p["outcome"] == "loss")
    draws = n - wins - losses
    avg_turns = (sum(p["turns"] for p in perspectives) / n) if n else 0

    # 按对手分组
    by_opp: Dict[str, Dict[str, int]] = {}
    for p in perspectives:
        opp = p["opponent"]
        slot = by_opp.setdefault(opp, {"win": 0, "loss": 0, "draw": 0, "total": 0})
        slot[p["outcome"]] += 1
        slot["total"] += 1

    # 失败局上「最先倒下的我方精灵」分布（首要弱点）
    first_fall_dist: Dict[str, int] = {}
    last_alive_dist: Dict[str, int] = {}
    for p in perspectives:
        if p["outcome"] != "loss":
            continue
        fainted = [r["name"] for r in p["my_team_final"] if r.get("fainted")]
        alive = [r["name"] for r in p["my_team_final"] if not r.get("fainted")]
        if fainted:
            # final_state 不保留顺序信息，这里只记「倒下的精灵频次」
            for n_ in fainted:
                first_fall_dist[n_] = first_fall_dist.get(n_, 0) + 1
        for n_ in alive:
            last_alive_dist[n_] = last_alive_dist.get(n_, 0) + 1

    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": (wins / n) if n else 0.0,
        "avg_turns": avg_turns,
        "by_opponent": by_opp,
        "loss_fainted_freq": first_fall_dist,
        "loss_survivor_freq": last_alive_dist,
    }


# ============================================================
# Prompt 构建
# ============================================================

def _format_lineup(lineup: list) -> str:
    lines = []
    for p in lineup:
        sk_str = ", ".join(
            f"{s['name']}({s['type']}/{s['category']},威{s['power']},耗{s['energy_cost']})"
            for s in p.get("skills", [])
        )
        nat = f"·{p['nature']}" if p.get("nature") else ""
        ab = f" 特性[{p['ability']}]" if p.get("ability") else ""
        st = p.get("stats", {})
        stats_str = f"H{st.get('hp')}/A{st.get('attack')}/D{st.get('defense')}/SA{st.get('sp_attack')}/SD{st.get('sp_defense')}/S{st.get('speed')}"
        lines.append(f"  - {p['name']}({p['type']}{nat}){ab} {stats_str}\n      技能: {sk_str}")
    return "\n".join(lines)


def _truncate_log(text: str, max_chars: int) -> str:
    if not text or len(text) <= max_chars:
        return text
    head = max_chars * 2 // 3
    tail = max_chars - head - 24
    return text[:head] + f"\n... [略 {len(text) - head - tail} 字] ...\n" + text[-tail:]


def _format_battle_row(p: Dict[str, Any]) -> str:
    """单场战斗一行紧凑摘要"""
    o = {"win": "胜", "loss": "败", "draw": "平"}[p["outcome"]]
    return (f"  #{p['id']:<5} {o}  vs {p['opponent']:<14} "
            f"{p['turns']:>2}回 (我方残命{p['my_lives_remaining']}/4 vs 对方残命{p['opp_lives_remaining']}/4)")


def _format_freq(d: Dict[str, int], top: int = 6) -> str:
    if not d:
        return "  (无)"
    items = sorted(d.items(), key=lambda x: -x[1])[:top]
    return "  " + ", ".join(f"{k}×{v}" for k, v in items)


def _build_aggregate_prompt(
    team_name: str,
    perspectives: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> Tuple[str, str]:
    """构建聚合 prompt，返回 (system, user)。"""

    # 阵容取最近一场我方阵容（理论上稳定不变）
    recent_lineup = perspectives[0]["my_lineup"] if perspectives else []

    # 摘要表
    summary_lines = [_format_battle_row(p) for p in perspectives]

    # 对手分布
    opp_lines = []
    for opp, s in sorted(stats["by_opponent"].items(),
                          key=lambda kv: -kv[1]["total"]):
        wr = (s["win"] / s["total"] * 100) if s["total"] else 0
        opp_lines.append(f"  - {opp:<14} {s['total']}场  {s['win']}胜/{s['loss']}败/{s['draw']}平  胜率{wr:.0f}%")

    # 抽样失败战例（最近）
    losses = [p for p in perspectives if p["outcome"] == "loss"]
    sampled = losses[:MAX_LOSS_SAMPLES]
    detail_blocks = []
    for p in sampled:
        opp_lineup_str = _format_lineup(p["opp_lineup"])
        log_snippet = _truncate_log(p["log_text"], LOG_SAMPLE_CHARS)
        my_final_parts = []
        for r in p["my_team_final"]:
            tag = "倒" if r.get("fainted") else f"HP{r['hp']}"
            my_final_parts.append(f"{r['name']}({tag})")
        detail_blocks.append(
            f"\n--- 失败战例 #{p['id']} vs {p['opponent']}（{p['turns']} 回合）---\n"
            f"对手阵容:\n{opp_lineup_str}\n"
            f"我方残局: " + ", ".join(my_final_parts) + "\n"
            f"日志摘录:\n{log_snippet}"
        )

    system = (
        "你是洛克王国（Roco Kingdom）资深战术分析师。"
        "用户会给你一支队伍最近 N 场对战的聚合数据：胜率统计、按对手分布、"
        "败局的精灵阵亡分布、若干败局的详细日志摘录、以及该队的标准阵容。"
        "请严格基于这些数据输出分析报告，**避免空泛套话**，结构如下：\n"
        "  1. 整体胜率诊断（哪些对手是大坑、哪些是优势局，本队是高方差还是稳定型）\n"
        "  2. 模式化弱点（重复出现的失败模式：能量曲线 / 属性短板 / 关键精灵被秒 等）\n"
        "  3. 单只精灵评估（结合阵亡频次，谁是核心、谁是负担）\n"
        "  4. 改阵建议（具体到换哪只、换什么技能/性格/特性，给出至少 2 条且各自说明针对的弱点）\n"
        "用中文回答，每节短而具体。"
    )

    user_parts = [
        f"== 队伍 ==\n{team_name}",
        f"\n== 标准阵容（取最近一场）==\n{_format_lineup(recent_lineup)}",
        (f"\n== 聚合统计（{stats['n']} 场）==\n"
         f"  战绩: {stats['wins']}胜 / {stats['losses']}败 / {stats['draws']}平   "
         f"胜率 {stats['win_rate']*100:.1f}%\n"
         f"  平均回合数: {stats['avg_turns']:.1f}"),
        f"\n== 按对手分布 ==\n" + ("\n".join(opp_lines) if opp_lines else "  (无)"),
        f"\n== 败局阵亡频次 ==\n{_format_freq(stats['loss_fainted_freq'])}",
        f"\n== 败局存活频次 ==\n{_format_freq(stats['loss_survivor_freq'])}",
        f"\n== 全部场次摘要 ==\n" + ("\n".join(summary_lines) if summary_lines else "  (无)"),
    ]
    if detail_blocks:
        user_parts.append("\n== 失败战例日志摘录 ==" + "".join(detail_blocks))

    return system, "\n".join(user_parts)


# ============================================================
# 公共入口
# ============================================================

def analyze_team_aggregate(
    team_name: str,
    n: int = 50,
    opponent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    对一支队伍最近 n 场对战做聚合复盘分析。

    Returns
    -------
    dict : {
        "ok": bool,
        "message": str,           # 错误时的提示
        "stats": dict,            # 聚合统计（即使 LLM 调用失败也会返回）
        "analysis": str,          # LLM 输出的分析文本，调用失败时为空
        "battles_used": int,      # 实际拉到的对战数
    }
    """
    if n <= 0:
        return {"ok": False, "message": "n 必须 > 0", "stats": {}, "analysis": "", "battles_used": 0}
    n = min(n, MAX_BATCHES)

    store = DataStore()
    if not store.db_enabled:
        return {"ok": False, "message": "数据库未启用，请在 .env 中设 DB_ENABLED=true",
                "stats": {}, "analysis": "", "battles_used": 0}

    rows = _fetch_recent_for_team(team_name, n, opponent=opponent)
    if not rows:
        return {"ok": False, "message": f"未找到「{team_name}」的对战日志（请先批量训练）",
                "stats": {}, "analysis": "", "battles_used": 0}

    perspectives = [_perspective(r, team_name) for r in rows]
    stats = _aggregate(perspectives)

    try:
        from sim.llm_agent import _call_llm
    except Exception as e:
        return {"ok": False, "message": f"LLM 模块导入失败: {e}",
                "stats": stats, "analysis": "", "battles_used": len(rows)}

    system, user = _build_aggregate_prompt(team_name, perspectives, stats)
    try:
        analysis = _call_llm(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
        )
    except Exception as e:
        return {"ok": False, "message": f"LLM 调用失败: {e}",
                "stats": stats, "analysis": "", "battles_used": len(rows)}

    return {
        "ok": True, "message": "",
        "stats": stats,
        "analysis": analysis,
        "battles_used": len(rows),
    }
