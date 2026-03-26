"""
洛克王国精灵图鉴终端查看器
操作: ← → 翻页  /搜索  q退出
"""

import json
import msvcrt
import os
import sys
from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich import box

DATA_PATH = Path("data/sprites.json")
WIDTH = 46

console = Console(width=WIDTH, highlight=False)

ATTR_COLOR = {
    "火": "red", "水": "blue", "草": "green", "电": "yellow",
    "冰": "cyan", "幽": "magenta", "恶": "dark_red", "幻": "bright_magenta",
    "普通": "white", "光": "bright_yellow", "暗": "grey62",
}

STAT_MAX = 180
BAR_W = 12


def attr_tag(name: str) -> Text:
    color = ATTR_COLOR.get(name, "white")
    t = Text()
    t.append(f" {name} ", style=f"bold {color} on grey19")
    return t


def stat_bar(val: int) -> Text:
    t = Text()
    if not val:
        t.append("──────────────  --", style="grey35")
        return t
    filled = min(int(BAR_W * val / STAT_MAX), BAR_W)
    color = "green" if val >= 120 else ("yellow" if val >= 80 else "red")
    t.append("█" * filled, style=color)
    t.append("░" * (BAR_W - filled), style="grey30")
    t.append(f"  {val:>3}", style="dim")
    return t


def render(sprite: dict, index: int, total: int):
    os.system("cls")

    name = sprite["name"]
    form = f"（{sprite['form']}）" if sprite.get("form") else ""
    no   = sprite.get("no", "?")
    stats   = sprite.get("stats") or {}
    ability = sprite.get("ability") or {}
    matchup = sprite.get("type_matchup") or {}
    skills  = sprite.get("skills") or []
    attrs   = sprite.get("attributes") or []

    rows = []   # list of rich renderables

    # ── 名称行 ────────────────────────────────────────
    title_line = Text()
    title_line.append(f"NO.{no:03d}  ", style="dim")
    title_line.append(f"{name}{form}", style="bold white")
    if sprite.get("has_shiny"):
        title_line.append("  ✦", style="bright_yellow")
    rows.append(title_line)

    # ── 属性 ─────────────────────────────────────────
    attr_line = Text()
    attr_line.append("属性  ", style="dim")
    if attrs:
        for a in attrs:
            attr_line.append_text(attr_tag(a))
            attr_line.append(" ")
    else:
        attr_line.append("未知", style="dim")
    rows.append(attr_line)
    rows.append(Text())

    # ── 种族值 ────────────────────────────────────────
    if stats:
        rows.append(Rule("[cyan]种族值[/cyan]", style="grey30"))
        for cn, key in [("生命", "hp"), ("物攻", "atk"), ("魔攻", "sp_atk"),
                        ("物防", "def"), ("魔防", "sp_def"), ("速度", "spd")]:
            line = Text()
            line.append(f"{cn} ", style="dim")
            line.append_text(stat_bar(stats.get(key, 0)))
            rows.append(line)
        if stats.get("total"):
            total_line = Text()
            total_line.append("合计", style="dim")
            total_line.append(f"{'':>16}", style="")
            total_line.append(f"{stats['total']:>3}", style="bold white")
            rows.append(total_line)
        rows.append(Text())

    # ── 特性 ──────────────────────────────────────────
    aname = ability.get("name", "")
    adesc = ability.get("description", "")
    if adesc == aname:
        adesc = ""
    if aname:
        rows.append(Rule("[cyan]特性[/cyan]", style="grey30"))
        rows.append(Text(aname, style="bold"))
        if adesc:
            rows.append(Text(adesc[:42], style="dim"))
        rows.append(Text())

    # ── 克制关系 ──────────────────────────────────────
    has_matchup = any(matchup.get(k) for k in matchup)
    if has_matchup:
        rows.append(Rule("[cyan]克制关系[/cyan]", style="grey30"))
        for label, key in [("克制  ", "strong_against"), ("被克制", "weak_to"),
                           ("抵抗  ", "resists"),        ("被抵抗", "resisted_by")]:
            items = matchup.get(key) or []
            if not items:
                continue
            line = Text()
            line.append(f"{label}  ", style="dim")
            for a in items:
                line.append_text(attr_tag(a))
                line.append(" ")
            rows.append(line)
        rows.append(Text())

    # ── 技能 ──────────────────────────────────────────
    if skills:
        rows.append(Rule("[cyan]技能[/cyan]", style="grey30"))
        for s in skills[:10]:
            sname = s.get("name", "")
            attr  = s.get("attribute", "")
            cat   = s.get("category", "")
            power = s.get("power", 0)
            cost  = s.get("cost", 0)
            desc  = s.get("description", "")

            line = Text()
            line.append(f"{sname}", style="bold")
            line.append("  ")
            line.append_text(attr_tag(attr))
            line.append(f" {cat}", style="dim")
            if power:
                line.append(f"  威力{power}", style="bright_white")
            if cost:
                line.append("  " + "★" * cost, style="yellow")
            rows.append(line)
            if desc:
                rows.append(Text(f"  {desc[:40]}", style="dim"))

    footer = Text(justify="center")
    footer.append("← →", style="bold")
    footer.append(" 翻页    ", style="dim")
    footer.append("/", style="bold")
    footer.append(" 搜索    ", style="dim")
    footer.append("q", style="bold")
    footer.append(" 退出", style="dim")

    console.print(Panel(
        Group(*rows),
        title="[bold]洛克王国图鉴[/bold]",
        subtitle=f"[dim]{index + 1} / {total}[/dim]",
        border_style="bright_blue",
        box=box.ROUNDED,
        width=WIDTH,
        padding=(0, 1),
    ))
    console.print(footer)


# ── 搜索 ──────────────────────────────────────────────────────────────────────

def search(data: list[dict], query: str) -> int | None:
    q = query.strip().lower()
    if not q:
        return None
    for i, s in enumerate(data):
        if q == s["name"].lower():
            return i
    for i, s in enumerate(data):
        name = s["name"].lower()
        form = (s.get("form") or "").lower()
        if q in name or q in form:
            return i
    for i, s in enumerate(data):
        if q == str(s.get("no", "")):
            return i
    return None


def prompt_search(data: list[dict], current: int) -> int:
    os.system("cls")
    console.print(Panel(
        Text("输入精灵名称或编号，回车确认\n空回车取消", style="dim"),
        title="[bold]搜索[/bold]",
        border_style="bright_blue",
        box=box.ROUNDED,
        width=WIDTH,
    ))
    query = input("  > ").strip()
    if not query:
        return current
    result = search(data, query)
    if result is None:
        console.print(f"[red]  未找到「{query}」[/red]")
        msvcrt.getch()
    return result if result is not None else current


# ── 主循环 ────────────────────────────────────────────────────────────────────

def load_data() -> list[dict]:
    if not DATA_PATH.exists():
        console.print("[red]找不到数据文件，请先运行爬虫[/red]")
        sys.exit(1)
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def main():
    data = load_data()
    index = 0
    total = len(data)

    while True:
        render(data[index], index, total)
        key = msvcrt.getch()

        if key in (b'\xe0', b'\x00'):
            key2 = msvcrt.getch()
            if key2 == b'M':
                index = (index + 1) % total
            elif key2 == b'K':
                index = (index - 1) % total
        elif key in (b'q', b'Q'):
            os.system("cls")
            break
        elif key == b'/':
            index = prompt_search(data, index)
        elif key in (b'd', b'D', b'n', b'N'):
            index = (index + 1) % total
        elif key in (b'a', b'A', b'p', b'P'):
            index = (index - 1) % total


if __name__ == "__main__":
    main()
