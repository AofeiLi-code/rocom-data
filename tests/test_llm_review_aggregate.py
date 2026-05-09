"""
LLM 聚合复盘 — 不依赖 MariaDB / 不调 LLM 的纯逻辑测试。
仅测试视角化 + 聚合统计 + prompt 构建。
"""

from sim.llm_review import (
    _aggregate, _build_aggregate_prompt, _format_battle_row, MAX_BATCHES,
)


def _mk_p(id_: int, opp: str, outcome: str, turns: int = 10,
          fainted=(), alive=("精灵A",)):
    """构造一个 perspective 视角化记录。"""
    return {
        "id": id_,
        "opponent": opp,
        "outcome": outcome,
        "turns": turns,
        "my_lineup": [
            {"name": "精灵A", "type": "fire", "ability": "对流", "nature": "勇敢",
             "stats": {"hp": 100, "attack": 80, "defense": 70,
                       "sp_attack": 60, "sp_defense": 70, "speed": 80},
             "skills": [{"name": "火焰", "type": "fire", "category": "physical",
                         "power": 80, "energy_cost": 3}]},
        ],
        "opp_lineup": [
            {"name": "对手1", "type": "water", "ability": "", "nature": "",
             "stats": {"hp": 110, "attack": 90, "defense": 70,
                       "sp_attack": 60, "sp_defense": 70, "speed": 85},
             "skills": [{"name": "水柱", "type": "water", "category": "physical",
                         "power": 80, "energy_cost": 3}]},
        ],
        "my_lives_remaining": 0 if outcome == "loss" else 3,
        "opp_lives_remaining": 3 if outcome == "loss" else 0,
        "my_team_final": (
            [{"name": n, "hp": 0, "hp_max": 100, "energy": 0, "fainted": True,
              "burn": 0, "poison": 0, "freeze": 0} for n in fainted] +
            [{"name": n, "hp": 50, "hp_max": 100, "energy": 1, "fainted": False,
              "burn": 0, "poison": 0, "freeze": 0} for n in alive]
        ),
        "opp_team_final": [
            {"name": "对手1", "hp": 30, "hp_max": 110, "energy": 1, "fainted": False,
             "burn": 0, "poison": 0, "freeze": 0}
        ],
        "log_text": f"回合1: 精灵A vs 对手1\n回合{turns}: 战斗结束（{outcome}）",
        "created_at": "2025-01-01 00:00:00",
    }


def test_aggregate_basic():
    ps = [
        _mk_p(1, "狼王队", "win"),
        _mk_p(2, "狼王队", "win"),
        _mk_p(3, "狼王队", "loss", fainted=["精灵A"], alive=[]),
        _mk_p(4, "毒队",   "loss", fainted=["精灵A"], alive=[]),
        _mk_p(5, "毒队",   "draw"),
    ]
    s = _aggregate(ps)
    assert s["n"] == 5
    assert s["wins"] == 2
    assert s["losses"] == 2
    assert s["draws"] == 1
    assert abs(s["win_rate"] - 0.4) < 1e-6
    assert s["by_opponent"]["狼王队"]["total"] == 3
    assert s["by_opponent"]["狼王队"]["win"] == 2
    assert s["by_opponent"]["毒队"]["loss"] == 1
    assert s["loss_fainted_freq"]["精灵A"] == 2


def test_format_row_outcome_label():
    win_row = _format_battle_row(_mk_p(1, "X", "win"))
    loss_row = _format_battle_row(_mk_p(2, "X", "loss"))
    draw_row = _format_battle_row(_mk_p(3, "X", "draw"))
    assert "胜" in win_row
    assert "败" in loss_row
    assert "平" in draw_row


def test_build_prompt_has_required_sections():
    ps = [_mk_p(1, "狼王队", "loss", fainted=["精灵A"], alive=[])]
    s = _aggregate(ps)
    sys_, usr = _build_aggregate_prompt("我的队", ps, s)
    assert "战术分析师" in sys_
    assert "我的队" in usr
    assert "标准阵容" in usr
    assert "聚合统计" in usr
    assert "按对手分布" in usr
    assert "败局阵亡频次" in usr
    assert "全部场次摘要" in usr
    # 单场失败 → 应有日志摘录块
    assert "失败战例日志摘录" in usr
    assert "狼王队" in usr


def test_max_batches_constant():
    assert MAX_BATCHES == 100


def test_empty_perspectives_safe():
    s = _aggregate([])
    assert s["n"] == 0
    assert s["win_rate"] == 0.0
    assert s["wins"] == s["losses"] == s["draws"] == 0


def test_all_wins_no_loss_block():
    ps = [_mk_p(i, "X", "win") for i in range(3)]
    s = _aggregate(ps)
    sys_, usr = _build_aggregate_prompt("纯胜队", ps, s)
    # 无败局时不应有"失败战例日志摘录"块
    assert "失败战例日志摘录" not in usr
