"""
洛克王国 BWIKI 精灵数据爬虫
目标: https://wiki.biligame.com/rocom/精灵图鉴
输出: data/sprites.json  (精灵基础数据 + 技能 + 克制关系)
      data/sprites.csv   (同上，CSV 格式，技能列用分号拼接)

使用方法:
    pip install requests beautifulsoup4
    python rocom_scraper.py

可选参数:
    --limit N     只爬前N只精灵 (调试用)
    --delay 0.8   每次请求间隔秒数 (默认0.8, 请勿设太低)
    --output xxx  输出文件路径 (默认 data/sprites.json)
"""

import re
import csv
import json
import time
import random
import argparse
import os
from pathlib import Path
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://wiki.biligame.com"
LIST_URL = "https://wiki.biligame.com/rocom/%E7%B2%BE%E7%81%B5%E5%9B%BE%E9%89%B4"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://wiki.biligame.com/rocom/",
}

# 请求间隔：每次随机 1.5~3 秒（--delay 参数覆盖下限）
_DELAY_MIN = 1.5
_DELAY_MAX = 3.0

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ── 进度条 ────────────────────────────────────────────────────────────────────

def print_progress(current: int, total: int, label: str = "", width: int = 28):
    """用 \\r 在同一行覆写进度条"""
    filled = int(width * current / total) if total > 0 else 0
    bar = "#" * filled + "-" * (width - filled)
    pct = current / total * 100 if total > 0 else 0
    label = (label[:32] + "…") if len(label) > 33 else label
    print(f"\r[{current:>4}/{total}] {bar} {pct:5.1f}%  {label}    ", end="", flush=True)
    if current >= total:
        print()


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def fetch(url: str, retries: int = 3) -> BeautifulSoup:
    """
    抓取页面并返回 BeautifulSoup 对象。
    失败时采用递增等待：第1次10s，第2次20s，第3次30s。
    567（反爬限制）单独提示。
    """
    # 每次重试前等待时间（秒）
    retry_waits = [10, 20, 30]

    for attempt in range(retries):
        try:
            resp = SESSION.get(url, timeout=15)
            if resp.status_code == 567:
                wait = retry_waits[min(attempt, len(retry_waits) - 1)]
                print(f"\n  [!] 触发反爬限制 (567)，等待 {wait}s 后重试 "
                      f"({attempt+1}/{retries})...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.HTTPError as e:
            wait = retry_waits[min(attempt, len(retry_waits) - 1)]
            print(f"\n  [!] HTTP 错误 ({attempt+1}/{retries}): {e}，等待 {wait}s...")
            time.sleep(wait)
        except requests.RequestException as e:
            wait = retry_waits[min(attempt, len(retry_waits) - 1)]
            print(f"\n  [!] 请求失败 ({attempt+1}/{retries}): {e}，等待 {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"无法抓取（已重试 {retries} 次）: {url}")


def img_alt_to_attr(alt: str) -> str:
    """从图片 alt 文本提取属性名, 如 '图标 宠物 属性 光.png' -> '光'"""
    m = re.search(r'属性\s+(\S+?)(?:\.png)?$', alt)
    return m.group(1) if m else alt.strip()


# ── 列表页解析 ────────────────────────────────────────────────────────────────

def parse_list_page() -> list[dict]:
    """解析精灵图鉴列表页, 返回 [{no, name, form, url, has_shiny}, ...]"""
    print(f"[*] 抓取列表页: {LIST_URL}")
    soup = fetch(LIST_URL)

    entries = []
    content = soup.find("div", id="mw-content-text") or soup
    for card in content.select("div.rocom_prop_img"):
        # NO编号
        no_span = card.find("span", style=re.compile(r'font-size:10px'))
        if not no_span:
            continue
        no_m = re.search(r'NO\.(\d+)', no_span.get_text())
        if not no_m:
            continue
        no = int(no_m.group(1))

        # 主链接
        a = card.find("a", href=re.compile(r'^/rocom/'))
        if not a:
            continue
        href = a["href"]
        url = urljoin(BASE_URL, href)

        # 名字从 block_2，形态从 block_3
        name_p = card.find("p", class_="block_2")
        name = name_p.get_text(strip=True) if name_p else unquote(href.split("/rocom/")[-1])
        form_p = card.find("p", class_="block_3")
        form = form_p.get_text(strip=True) or None if form_p else None

        has_shiny = "异色" in card.get_text()

        entries.append({
            "no": no,
            "name": name,
            "form": form,
            "url": url,
            "has_shiny": has_shiny,
        })

    print(f"[*] 共找到 {len(entries)} 条精灵记录")
    return entries


# ── 详情页解析 ────────────────────────────────────────────────────────────────

def parse_stat_block(soup: BeautifulSoup) -> dict:
    """解析种族值"""
    stats = {}
    stat_map = {
        "生命": "hp", "物攻": "atk", "魔攻": "sp_atk",
        "物防": "def", "魔防": "sp_def", "速度": "spd",
    }
    # 每个种族值在 <li> 里，包含 <p class="rocom_sprite_info_qualification_name">名称</p> 和数字
    seen = set()
    for li in soup.find_all("li"):
        name_p = li.find("p", attrs={"class": "rocom_sprite_info_qualification_name"})
        if not name_p:
            continue
        stat_name = name_p.get_text(strip=True)
        if stat_name in stat_map and stat_name not in seen:
            nums = re.findall(r'\d+', li.get_text())
            if nums:
                stats[stat_map[stat_name]] = int(nums[-1])
                seen.add(stat_name)
    if len(stats) == 6:
        stats["total"] = sum(stats.values())
    return stats


def parse_ability(soup: BeautifulSoup) -> dict | None:
    """解析特性"""
    ability_header = soup.find(string=re.compile(r'^特性$'))
    if not ability_header:
        return None
    container = ability_header.find_parent()
    if not container:
        return None
    # 特性名在下一个有内容的节点
    texts = [t.strip() for t in container.find_next_siblings(string=True) if t.strip()][:2]
    imgs = container.find_next_sibling()
    if not imgs:
        return None
    ability_name = imgs.get_text(strip=True) if imgs else ""
    ability_desc_node = imgs.find_next_sibling() if imgs else None
    ability_desc = ability_desc_node.get_text(strip=True) if ability_desc_node else ""
    # 备选: 直接从图片 alt
    img = container.find_next("img", alt=re.compile(r'^(?!图标|界面|页面)'))
    if img:
        ability_name = img.get("alt", ability_name).replace(".png", "")
    return {"name": ability_name, "description": ability_desc} if ability_name else None


def parse_type_matchup(soup: BeautifulSoup) -> dict:
    """解析克制关系"""
    matchup = {
        "strong_against": [],   # 克制 (我的属性技能对这些属性有效果)
        "weak_to": [],          # 被克制
        "resists": [],          # 抵抗
        "resisted_by": [],      # 被抵抗
    }
    label_map = {
        "克制": "strong_against",
        "被克制": "weak_to",
        "抵抗": "resists",
        "被抵抗": "resisted_by",
    }
    for label_cn, key in label_map.items():
        node = soup.find(string=re.compile(f'^{label_cn}$'))
        if not node:
            continue
        p = node.find_parent()
        if not p:
            continue
        # 属性图片是 <p> 的兄弟节点，同在一个 <div> 内
        container = p.find_parent()
        if not container:
            continue
        for img in container.find_all("img"):
            alt = img.get("alt", "")
            if "属性" in alt:
                matchup[key].append(img_alt_to_attr(alt))
    return matchup


def parse_skills(soup: BeautifulSoup) -> list[dict]:
    """解析技能列表"""
    skills = []
    # 每个技能块包含: 属性图标, 技能名, 星数(能量消耗), 类别, 威力, 描述
    # 结构: 技能区域在克制表之后

    # 找所有包含技能信息的行
    # 技能的特征: 有"图标 技能 星星背景"图片 (能量消耗标识)
    skill_cost_imgs = soup.find_all("img", alt=re.compile(r'图标 技能 星星背景'))
    
    for cost_img in skill_cost_imgs:
        try:
            # 向上找技能容器块
            container = cost_img.find_parent()
            for _ in range(5):  # 最多向上找5层
                if container and container.find("img", alt=re.compile(r'图标 宠物 属性')):
                    break
                container = container.find_parent() if container else None
            if not container:
                continue

            # 属性
            attr_img = container.find("img", alt=re.compile(r'图标 宠物 属性'))
            skill_attr = img_alt_to_attr(attr_img.get("alt", "")) if attr_img else "未知"

            # 技能名 (通常是第一个非图标的文本或img alt)
            # 技能图标 alt 格式: "技能图标 技能名.png"
            skill_icon = container.find("img", alt=re.compile(r'^技能图标'))
            if skill_icon:
                skill_name = skill_icon.get("alt", "").replace("技能图标 ", "").replace(".png", "")
            else:
                skill_name = ""

            # 能量消耗 (星数): cost_img 后的第一个数字文本
            cost_text = cost_img.find_next_sibling(string=True)
            cost = int(cost_text.strip()) if cost_text and cost_text.strip().isdigit() else 0

            # 类别 (物攻/魔攻/状态/防御)
            category_img = container.find("img", alt=re.compile(r'图标 技能 类别'))
            if category_img:
                cat_alt = category_img.get("alt", "")
                cat_m = re.search(r'类别\s+(\S+?)(?:\.png)?$', cat_alt)
                category = cat_m.group(1) if cat_m else ""
            else:
                category = ""

            # 威力: 类别图后的数字
            power = 0
            if category_img:
                sib = category_img.find_next_sibling(string=True)
                if sib and sib.strip().lstrip('-').isdigit():
                    power = int(sib.strip())

            # 描述: ✦ 开头的文本
            full_text = container.get_text(" ", strip=True)
            desc_m = re.search(r'✦(.+?)(?:$)', full_text)
            description = desc_m.group(1).strip() if desc_m else ""

            if skill_name:
                skills.append({
                    "name": skill_name,
                    "attribute": skill_attr,
                    "category": category,
                    "cost": cost,
                    "power": power,
                    "description": description,
                })
        except Exception:
            continue

    return skills


def parse_attributes_from_detail(soup: BeautifulSoup) -> list[str]:
    """从详情页解析精灵属性 (可能有双属性)"""
    # 详情页顶部有属性图标
    header_area = soup.find("div", id="mw-content-text") or soup
    attrs = []
    # 找标题附近的属性图标 (排除克制表里的)
    # 策略: 找第一组属性图标 (在种族值之前)
    stat_node = soup.find(string=re.compile(r'种族值'))
    if stat_node:
        before_stats = stat_node.find_parent()
        # 找在这之前出现的属性图标
        for img in soup.find_all("img", alt=re.compile(r'^图标 宠物 属性')):
            if before_stats and img in before_stats.find_all_previous("img"):
                continue
            attr = img_alt_to_attr(img.get("alt", ""))
            if attr and attr not in attrs:
                attrs.append(attr)
            if len(attrs) >= 2:
                break
    return attrs


def parse_evolution_chain(soup: BeautifulSoup) -> list[dict] | None:
    """解析进化链，返回 [{name, id, condition}, ...] 或 None"""
    box = soup.find("div", class_="rocom_spirit_evolution_box")
    if not box:
        return None

    # 收集各阶段精灵
    stages = []
    for i in range(1, 4):
        div = box.find("div", class_=f"rocom_spirit_evolution_{i}")
        if not div:
            break
        a = div.find("a")
        if not a:
            break
        name = a.get("title", "")
        href = a.get("href", "")
        sprite_id = unquote(href.split("/rocom/")[-1]) if "/rocom/" in href else name
        stages.append({"name": name, "id": sprite_id})

    if len(stages) <= 1:
        return None

    # 进化等级：在 evolution_1 和 evolution_2 之间，evolution_2 和 evolution_3 之间
    level_divs = box.find_all("div", class_="rocom_spirit_evolution_level")
    levels = []
    for ld in level_divs:
        p = ld.find("p", class_="rocom_spirit_evolution_level_num")
        levels.append(p.get_text(strip=True) if p else None)

    # 进化条件（整个 rightBox 范围内）
    rightbox = soup.find("div", class_="rocom_sprite_temp_evolve_rightBox")
    condition = None
    if rightbox:
        cond_p = rightbox.find("p", class_="rocom_evolution_data")
        if cond_p:
            condition = cond_p.get_text(strip=True)

    # 组装：每个非首阶段附上进化到它的等级/条件
    result = [{"name": stages[0]["name"], "no": None, "evolves_from": None, "level": None, "condition": None}]
    for i, stage in enumerate(stages[1:]):
        level = levels[i] if i < len(levels) else None
        cond = condition if i == len(stages) - 2 else None
        result.append({"name": stage["name"], "no": None, "evolves_from": stages[i]["name"], "level": level, "condition": cond})

    return result


def parse_sprite_detail(entry: dict) -> dict:
    """爬取并解析单个精灵的详情页"""
    soup = fetch(entry["url"])
    content = soup.find("div", id="mw-content-text") or soup

    # 种族值
    stats = parse_stat_block(content)

    # 属性 (从页面顶部的属性图标)
    # 简单方式: 找页面title区域附近的属性图
    attrs = []
    # 在 h1 标题附近找属性
    h1 = soup.find("h1")
    if h1:
        # 找h1之后的前几个属性图标
        for img in h1.find_all_next("img", limit=10):
            alt = img.get("alt", "")
            if "图标 宠物 属性" in alt:
                a = img_alt_to_attr(alt)
                if a and a not in attrs:
                    attrs.append(a)
            if len(attrs) >= 2:
                break

    # 特性
    ability_section = content.find(string=re.compile(r'^特性$'))
    ability = None
    if ability_section:
        p = ability_section.find_parent()
        if p:
            # 找特性图片的alt作为名字
            nxt = p.find_next("img", alt=re.compile(r'^(?!图标|界面|页面)'))
            if nxt:
                ability_name = nxt.get("alt", "").replace(".png", "")
                # 特性描述: 该图片后的文字
                desc_node = nxt.find_next(string=re.compile(r'.{5,}'))
                ability_desc = desc_node.strip() if desc_node else ""
                ability = {"name": ability_name, "description": ability_desc}

    # 克制关系
    matchup = parse_type_matchup(content)

    # 进化链
    evolution_chain = parse_evolution_chain(content)

    # 技能
    skills = parse_skills(content)

    return {
        **entry,
        "attributes": attrs,
        "stats": stats,
        "ability": ability,
        "type_matchup": matchup,
        "evolution_chain": evolution_chain,
        "skills": skills,
    }


# ── 检查更新 ──────────────────────────────────────────────────────────────────

def check_update(out_path: Path, delay: float = 1.5):
    """对比本地数据与 wiki 列表，按需增量爬取"""
    if not out_path.exists():
        print("[!] 本地数据不存在，请先执行全量爬取")
        return

    with open(out_path, encoding="utf-8") as f:
        local_data = json.load(f)

    local_keys = {(d["no"], d["name"], d.get("form")) for d in local_data}
    print(f"[*] 本地共有 {len(local_data)} 条记录")
    print(f"[*] 正在获取 wiki 精灵列表...")

    try:
        wiki_entries = parse_list_page()
    except RuntimeError as e:
        print(f"\n[!] 无法连接 wiki: {e}")
        print("[!] 可能是网络问题或服务器限速，请稍后重试")
        return
    wiki_map = {(e["no"], e["name"], e.get("form")): e for e in wiki_entries}

    new_keys = sorted(set(wiki_map) - local_keys, key=lambda x: (x[0], x[1], x[2] or ""))

    if not new_keys:
        print("\n[✓] 数据已是最新版本，无需更新")
        print("    3 秒后自动关闭...")
        time.sleep(3)
        return

    print(f"\n[+] 发现 {len(new_keys)} 条新精灵:")
    for no, name, form in new_keys:
        form_str = f"（{form}）" if form else ""
        print(f"    NO.{no:03d} {name}{form_str}")

    print()
    answer = input(f"是否爬取这 {len(new_keys)} 条新数据？[Y/n]: ").strip().lower()
    if answer not in ("", "y", "yes"):
        print("已取消")
        return

    new_entries = [wiki_map[k] for k in new_keys]
    results = list(local_data)
    failed = []

    print()
    for i, entry in enumerate(new_entries, 1):
        name_display = f"{entry['name']}{'（'+entry['form']+'）' if entry['form'] else ''}"
        print_progress(i, len(new_entries), f"NO.{entry['no']:03d} {name_display}")
        try:
            data = parse_sprite_detail(entry)
            results.append(data)
        except Exception as e:
            print(f"\n  [!] 失败: {e}")
            failed.append(entry["url"])
        time.sleep(random.uniform(delay, delay + 1.5))

    _save(results, out_path)
    csv_path = out_path.with_suffix(".csv")
    _save_csv(results, csv_path)

    print(f"\n[完成] 已更新，本地共 {len(results)} 条，本次失败 {len(failed)} 条")
    if failed:
        fail_path = out_path.with_name("failed_urls.txt")
        fail_path.write_text("\n".join(failed))
        print(f"[完成] 失败URL已记录至: {fail_path}")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="洛克王国精灵数据爬虫")
    parser.add_argument("--limit", type=int, default=0, help="只爬前N只 (0=全部)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="请求间隔下限(秒)，实际为 delay~(delay+1.5) 随机值，默认 1.5")
    parser.add_argument("--output", default="data/sprites.json", help="输出路径")
    parser.add_argument("--check-update", action="store_true", help="检查并增量更新数据")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.check_update:
        check_update(out_path, delay=args.delay)
        return

    # 1. 获取精灵列表
    try:
        entries = parse_list_page()
    except RuntimeError as e:
        print(f"\n[!] 无法连接 wiki: {e}")
        print("[!] 可能是网络问题或服务器限速，请稍后重试")
        return
    if args.limit > 0:
        entries = entries[:args.limit]
        print(f"[*] 限制模式: 只处理前 {args.limit} 只")

    # 2. 逐一爬取详情
    results = []
    failed = []

    for i, entry in enumerate(entries, 1):
        name_display = f"{entry['name']}{'（'+entry['form']+'）' if entry['form'] else ''}"
        print_progress(i, len(entries), f"NO.{entry['no']:03d} {name_display}")

        try:
            data = parse_sprite_detail(entry)
            results.append(data)
            if i % 10 == 0:
                _save(results, out_path)
        except Exception as e:
            print(f"\n  [!] 失败: {e}")
            failed.append(entry["url"])

        time.sleep(random.uniform(args.delay, args.delay + 1.5))

    # 3. 回填进化链 id（名字 → no）
    _backfill_evolution_ids(results)

    # 4. 最终保存
    _save(results, out_path)
    csv_path = out_path.with_suffix(".csv")
    _save_csv(results, csv_path)

    print(f"\n[完成] 成功: {len(results)}, 失败: {len(failed)}")
    print(f"[完成] JSON 已保存至: {out_path.resolve()}")
    print(f"[完成] CSV  已保存至: {csv_path.resolve()}")

    if failed:
        fail_path = out_path.with_name("failed_urls.txt")
        fail_path.write_text("\n".join(failed))
        print(f"[完成] 失败URL已记录至: {fail_path}")


def _backfill_evolution_ids(results: list):
    """用名字→no映射回填进化链中的no字段"""
    name_to_no = {s["name"]: s["no"] for s in results if s.get("name")}
    for s in results:
        for stage in (s.get("evolution_chain") or []):
            stage["no"] = name_to_no.get(stage["name"])


def _save(data: list, path: Path):
    # 写入前先备份原文件
    if path.exists():
        import shutil
        shutil.copy2(path, path.with_suffix(".backup.json"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


CSV_COLUMNS = [
    "no", "name", "form", "url", "has_shiny",
    "attributes", "total_stats",
    "hp", "atk", "sp_atk", "def", "sp_def", "spd",
    "ability_name", "ability_desc",
    "strong_against", "weak_to", "resists", "resisted_by",
    "evolution_chain",
    "skills",
]


def _sprite_to_csv_row(d: dict) -> dict:
    stats = d.get("stats") or {}
    ability = d.get("ability") or {}
    matchup = d.get("type_matchup") or {}

    def skill_str(s: dict) -> str:
        return (
            f"{s.get('name', '')}("
            f"{s.get('attribute', '')}/"
            f"{s.get('category', '')}/"
            f"{s.get('power', '')}/"
            f"{s.get('cost', '')}/"
            f"{s.get('description', '')})"
        )

    return {
        "no":             d.get("no", ""),
        "name":           d.get("name", ""),
        "form":           d.get("form", "") or "",
        "url":            d.get("url", ""),
        "has_shiny":      d.get("has_shiny", False),
        "attributes":     ",".join(d.get("attributes") or []),
        "total_stats":    stats.get("total", ""),
        "hp":             stats.get("hp", ""),
        "atk":            stats.get("atk", ""),
        "sp_atk":         stats.get("sp_atk", ""),
        "def":            stats.get("def", ""),
        "sp_def":         stats.get("sp_def", ""),
        "spd":            stats.get("spd", ""),
        "ability_name":   ability.get("name", ""),
        "ability_desc":   ability.get("description", ""),
        "strong_against": ",".join(matchup.get("strong_against") or []),
        "weak_to":        ",".join(matchup.get("weak_to") or []),
        "resists":        ",".join(matchup.get("resists") or []),
        "resisted_by":    ",".join(matchup.get("resisted_by") or []),
        "evolution_chain": ";".join(
            f"{e['name']}({e.get('level') or ''}/{e.get('condition') or ''})"
            for e in (d.get("evolution_chain") or [])
        ),
        "skills":         ";".join(skill_str(s) for s in (d.get("skills") or [])),
    }


def _save_csv(data: list, path: Path):
    if path.exists():
        import shutil
        shutil.copy2(path, path.with_suffix(".backup.csv"))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for d in data:
            writer.writerow(_sprite_to_csv_row(d))


if __name__ == "__main__":
    main()
