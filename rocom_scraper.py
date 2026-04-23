"""
洛克王国 BWIKI 精灵数据爬虫
目标: https://wiki.biligame.com/rocom/精灵图鉴
输出: data/sprites.json  (精灵基础数据 + 技能 + 克制关系)
      data/sprites.csv   (同上，CSV 格式，技能列用分号拼接)
      data/skills.csv    (全技能去重列表)
      data/urls.csv      (图片URL列表，边爬边更新)
      data/images/       (下载的图片，按类型分子目录)

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
import shutil
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

# ── URL 收集 & 图片下载 ────────────────────────────────────────────────────────

# 图片类型 -> 子目录名
IMAGE_DIRS = {
    "sprite":    "images/sprites",    # 精灵立绘
    "attribute": "images/attributes", # 属性图标
    "skill":     "images/skills",     # 技能图标
    "ability":   "images/abilities",  # 特性图标
    "matchup":   "images/matchup",    # 克制表属性图标
}

_urls_cache: dict[str, dict] = {}   # url -> row, 去重用
_urls_path: Path | None = None

URL_COLUMNS = ["name", "type", "url", "local_path"]


def _init_urls(out_path: Path):
    global _urls_path, _urls_cache
    _urls_path = out_path.parent / "urls.csv"
    _urls_cache = {}
    if _urls_path.exists():
        with open(_urls_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                _urls_cache[row["url"]] = row


def _add_url(name: str, img_type: str, url: str, data_dir: Path, force: bool = False) -> str:
    """记录一条图片URL，若未下载则立即下载，返回本地相对路径。"""
    if url in _urls_cache and not force:
        return _urls_cache[url]["local_path"]

    subdir = data_dir / IMAGE_DIRS[img_type]
    subdir.mkdir(parents=True, exist_ok=True)

    ext = url.split(".")[-1].split("?")[0] or "png"
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
    local_path = f"{IMAGE_DIRS[img_type]}/{safe_name}.{ext}"
    abs_path = data_dir / local_path

    if not abs_path.exists():
        try:
            r = SESSION.get(url, timeout=15)
            r.raise_for_status()
            abs_path.write_bytes(r.content)
        except Exception as e:
            print(f"\n  [!] 图片下载失败 {url}: {e}")
            local_path = ""

    row = {"name": name, "type": img_type, "url": url, "local_path": local_path}
    _urls_cache[url] = row
    _flush_urls()
    return local_path


def _flush_urls():
    if _urls_path is None:
        return
    with open(_urls_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=URL_COLUMNS)
        writer.writeheader()
        writer.writerows(_urls_cache.values())


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
    # 每个精灵是 <a href="/rocom/NAME"><span>NO.xxx</span>...</a>
    for a in content.find_all("a", href=re.compile(r'^/rocom/')):
        span = a.find("span", string=re.compile(r'^NO\.\d+'))
        if not span:
            continue
        no_m = re.search(r'NO\.(\d+)', span.get_text())
        if not no_m:
            continue
        no = int(no_m.group(1))

        href = a["href"]
        url = urljoin(BASE_URL, href)
        name_raw = unquote(href.split("/rocom/")[-1])

        form_m = re.match(r'^(.+?)（(.+)）$', name_raw)
        if form_m:
            name = form_m.group(1)
            form = form_m.group(2)
        else:
            name = name_raw
            form = None

        has_shiny = "异色" in a.get_text()

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


def parse_skills(soup: BeautifulSoup, data_dir: Path | None = None, force: bool = False) -> list[dict]:
    """解析技能列表，含等级要求和图标URL"""
    skills = []
    skill_cost_imgs = soup.find_all("img", alt=re.compile(r'图标 技能 星星背景'))

    for cost_img in skill_cost_imgs:
        try:
            # 向上找技能容器块 (rocom_sprite_skill_box)
            container = cost_img.find_parent()
            for _ in range(6):
                if container and container.get("class") and "rocom_sprite_skill_box" in container.get("class", []):
                    break
                if container and container.find("img", alt=re.compile(r'图标 宠物 属性')):
                    break
                container = container.find_parent() if container else None
            if not container:
                continue

            # 等级要求: rocom_sprite_skill_level div
            level = 0
            level_div = container.find(class_="rocom_sprite_skill_level")
            if level_div:
                lv_m = re.search(r'LV\s*(\d+)', level_div.get_text())
                if lv_m:
                    level = int(lv_m.group(1))

            # 属性图标
            attr_img = container.find("img", class_="rocom_sprite_skill_attr")
            if not attr_img:
                attr_img = container.find("img", alt=re.compile(r'图标 宠物 属性'))
            skill_attr = img_alt_to_attr(attr_img.get("alt", "")) if attr_img else "未知"

            # 技能图标 & 名称
            skill_icon = container.find("img", alt=re.compile(r'^技能图标'))
            if skill_icon:
                skill_name = skill_icon.get("alt", "").replace("技能图标 ", "").replace(".png", "")
                skill_icon_url = skill_icon.get("src", "")
            else:
                skill_name = ""
                skill_icon_url = ""

            # 属性图标URL (取原图，不用缩略图)
            attr_icon_url = ""
            if attr_img:
                src = attr_img.get("src", "")
                # 从 srcset 取最大分辨率，或直接用 src
                srcset = attr_img.get("srcset", "")
                if srcset:
                    parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
                    attr_icon_url = parts[-1] if parts else src
                else:
                    attr_icon_url = src

            # 能量消耗
            cost_text = cost_img.find_next_sibling(string=True)
            cost = int(cost_text.strip()) if cost_text and cost_text.strip().isdigit() else 0

            # 类别
            category_img = container.find("img", alt=re.compile(r'图标 技能 类别'))
            if category_img:
                cat_m = re.search(r'类别\s+(\S+?)(?:\.png)?$', category_img.get("alt", ""))
                category = cat_m.group(1) if cat_m else ""
            else:
                category = ""

            # 威力
            power = 0
            power_div = container.find(class_="rocom_sprite_skill_power")
            if power_div:
                pt = power_div.get_text(strip=True)
                if pt.lstrip('-').isdigit():
                    power = int(pt)

            # 描述
            full_text = container.get_text(" ", strip=True)
            desc_m = re.search(r'✦(.+?)(?:$)', full_text)
            description = desc_m.group(1).strip() if desc_m else ""

            if not skill_name:
                continue

            # 下载图标
            if data_dir and skill_icon_url:
                _add_url(skill_name, "skill", skill_icon_url, data_dir, force)
            if data_dir and attr_icon_url:
                _add_url(skill_attr, "attribute", attr_icon_url, data_dir, force)

            skills.append({
                "name": skill_name,
                "attribute": skill_attr,
                "category": category,
                "cost": cost,
                "power": power,
                "level": level,
                "description": description,
            })
        except Exception:
            continue

    seen = set()
    deduped = []
    for sk in skills:
        if sk["name"] not in seen:
            seen.add(sk["name"])
            deduped.append(sk)
    return deduped


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

    level_divs = box.find_all("div", class_="rocom_spirit_evolution_level")
    levels = []
    for ld in level_divs:
        p = ld.find("p", class_="rocom_spirit_evolution_level_num")
        levels.append(p.get_text(strip=True) if p else None)

    rightbox = soup.find("div", class_="rocom_sprite_temp_evolve_rightBox")
    condition = None
    if rightbox:
        cond_p = rightbox.find("p", class_="rocom_evolution_data")
        if cond_p:
            condition = cond_p.get_text(strip=True)

    result = [{"name": stages[0]["name"], "no": None, "evolves_from": None, "level": None, "condition": None}]
    for i, stage in enumerate(stages[1:]):
        level = levels[i] if i < len(levels) else None
        cond = condition if i == len(stages) - 2 else None
        result.append({"name": stage["name"], "no": None, "evolves_from": stages[i]["name"], "level": level, "condition": cond})

    return result


def parse_sprite_detail(entry: dict, data_dir: Path | None = None, force: bool = False) -> dict:
    """爬取并解析单个精灵的详情页"""
    soup = fetch(entry["url"])
    content = soup.find("div", id="mw-content-text") or soup

    stats = parse_stat_block(content)

    # 属性图标 (h1 之后前几个)
    attrs = []
    h1 = soup.find("h1")
    if h1:
        for img in h1.find_all_next("img", limit=10):
            alt = img.get("alt", "")
            if "图标 宠物 属性" in alt:
                a = img_alt_to_attr(alt)
                if a and a not in attrs:
                    attrs.append(a)
            if len(attrs) >= 2:
                break

    # 特性
    ability = None
    ability_section = content.find(string=re.compile(r'^特性$'))
    if ability_section:
        p = ability_section.find_parent()
        if p:
            nxt = p.find_next("img", alt=re.compile(r'^(?!图标|界面|页面)'))
            if nxt:
                ability_name = nxt.get("alt", "").replace(".png", "")
                desc_node = nxt.find_next(string=re.compile(r'.{5,}'))
                ability_desc = desc_node.strip() if desc_node else ""
                ability_icon_url = nxt.get("src", "")
                if data_dir and ability_icon_url and ability_name:
                    _add_url(ability_name, "ability", ability_icon_url, data_dir, force)
                ability = {"name": ability_name, "description": ability_desc}

    # 精灵立绘 (rocom_sprite_grament_img 内第一个可见 img)
    if data_dir:
        grament_div = content.find("div", class_="rocom_sprite_grament_img")
        if grament_div:
            sprite_img = grament_div.find("img")
            if sprite_img:
                sprite_url = sprite_img.get("src", "")
                sprite_label = f"{entry['name']}{'_'+entry['form'] if entry.get('form') else ''}"
                if sprite_url:
                    _add_url(sprite_label, "sprite", sprite_url, data_dir, force)

        # 克制表属性图标
        matchup_section = content.find(string=re.compile(r'^克制$'))
        if matchup_section:
            matchup_container = matchup_section.find_parent()
            if matchup_container:
                outer = matchup_container.find_parent()
                if outer:
                    for img in outer.find_all("img"):
                        alt = img.get("alt", "")
                        if "属性" in alt:
                            attr_name = img_alt_to_attr(alt)
                            src = img.get("src", "")
                            if src and attr_name:
                                _add_url(attr_name, "matchup", src, data_dir, force)

    # 进化链
    evolution_chain = parse_evolution_chain(content)

    matchup = parse_type_matchup(content)
    skills = parse_skills(content, data_dir, force)

    return {
        **entry,
        "attributes": attrs,
        "stats": stats,
        "ability": ability,
        "type_matchup": matchup,
        "evolution_chain": evolution_chain,
        "skills": skills,
    }


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="洛克王国精灵数据爬虫")
    parser.add_argument("--limit", type=int, default=0, help="只爬前N只 (0=全部)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="请求间隔下限(秒)，实际为 delay~(delay+1.5) 随机值，默认 1.5")
    parser.add_argument("--output", default="data/sprites.json", help="输出路径")
    parser.add_argument("--force", action="store_true", help="强制重爬所有精灵（含图片）")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data_dir = out_path.parent

    _init_urls(out_path)

    if args.force:
        for p in [data_dir / "skills.csv", data_dir / "urls.csv"]:
            if p.exists():
                p.unlink()
        _urls_cache.clear()

    # 加载已有数据，按 (no, name, form) 建索引
    existing: dict[tuple, dict] = {}
    if out_path.exists() and not args.force:
        with open(out_path, encoding="utf-8") as f:
            for d in json.load(f):
                existing[(d["no"], d["name"], d.get("form"))] = d

    try:
        entries = parse_list_page()
    except RuntimeError as e:
        print(f"\n[!] 无法连接 wiki: {e}")
        print("[!] 可能是网络问题或服务器限速，请稍后重试")
        return
    if args.limit > 0:
        entries = entries[:args.limit]
        print(f"[*] 限制模式: 只处理前 {args.limit} 只")

    results = []
    failed = []
    skipped = 0

    for i, entry in enumerate(entries, 1):
        key = (entry["no"], entry["name"], entry.get("form"))
        name_display = f"{entry['name']}{'（'+entry['form']+'）' if entry['form'] else ''}"
        print_progress(i, len(entries), f"NO.{entry['no']:03d} {name_display}")

        if key in existing:
            results.append(existing[key])
            skipped += 1
            continue

        try:
            data = parse_sprite_detail(entry, data_dir, args.force)
            results.append(data)
            if i % 10 == 0:
                _save(results, out_path)
        except Exception as e:
            print(f"\n  [!] 失败: {e}")
            failed.append(entry["url"])

        time.sleep(random.uniform(args.delay, args.delay + 1.5))

    _backfill_evolution_ids(results)
    _save(results, out_path)
    csv_path = out_path.with_suffix(".csv")
    _save_csv(results, csv_path)
    _save_skills_csv(results, data_dir / "skills.csv")

    print(f"\n[完成] 成功: {len(results)-skipped}, 跳过: {skipped}, 失败: {len(failed)}")
    print(f"[完成] JSON 已保存至: {out_path.resolve()}")
    print(f"[完成] CSV  已保存至: {csv_path.resolve()}")
    print(f"[完成] 技能 已保存至: {(data_dir / 'skills.csv').resolve()}")
    print(f"[完成] URLs 已保存至: {(data_dir / 'urls.csv').resolve()}")

    if failed:
        fail_path = out_path.with_name("failed_urls.txt")
        fail_path.write_text("\n".join(failed))
        print(f"[完成] 失败URL已记录至: {fail_path}")


def _backfill_evolution_ids(results: list):
    """用名字→no映射回填进化链中的no字段，支持有form的精灵"""
    name_to_no = {}
    for s in results:
        if not s.get("name"):
            continue
        name_to_no[s["name"]] = s["no"]
        if s.get("form"):
            name_to_no[f"{s['name']}（{s['form']}）"] = s["no"]
    for s in results:
        for stage in (s.get("evolution_chain") or []):
            stage["no"] = name_to_no.get(stage["name"])


def _save(data: list, path: Path):
    if path.exists():
        shutil.copy2(path, path.with_suffix(".backup.json"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


SKILLS_CSV_COLUMNS = ["技能名", "属性", "类型", "威力", "耗能", "效果描述"]


def _save_skills_csv(data: list, path: Path):
    seen = set()
    rows = []
    for sprite in data:
        for sk in (sprite.get("skills") or []):
            name = sk.get("name", "")
            if name and name not in seen:
                seen.add(name)
                rows.append({
                    "技能名": name,
                    "属性":   sk.get("attribute", ""),
                    "类型":   sk.get("category", ""),
                    "威力":   sk.get("power", ""),
                    "耗能":   sk.get("cost", ""),
                    "效果描述": sk.get("description", ""),
                })
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SKILLS_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)



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
            f"LV{s.get('level', 0)}/"
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
        shutil.copy2(path, path.with_suffix(".backup.csv"))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for d in data:
            writer.writerow(_sprite_to_csv_row(d))


if __name__ == "__main__":
    main()
