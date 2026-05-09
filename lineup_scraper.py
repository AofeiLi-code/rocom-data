"""BWIKI player lineup scraper.

Outputs text-only lineup archives to data/lineups.json and data/lineups.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import time
from pathlib import Path
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup



LINEUP_CSV_COLUMNS = [
    "id", "title", "type", "author", "author_link", "blood_magic", "uploaded_at", "last_updated", "intro",
    "pokemon_1", "bloodline_1", "nature_1", "talents_1", "skills_1",
    "pokemon_2", "bloodline_2", "nature_2", "talents_2", "skills_2",
    "pokemon_3", "bloodline_3", "nature_3", "talents_3", "skills_3",
    "pokemon_4", "bloodline_4", "nature_4", "talents_4", "skills_4",
    "pokemon_5", "bloodline_5", "nature_5", "talents_5", "skills_5",
    "pokemon_6", "bloodline_6", "nature_6", "talents_6", "skills_6",
    "parse_ok", "warnings",
]


def save_json(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(".backup.json"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def _member_by_slot(record: dict, slot: int) -> dict:
    for member in record.get("members", []):
        if member.get("slot") == slot:
            return member
    return {}


def _lineup_to_csv_row(record: dict) -> dict:
    row = {
        "id": record.get("id", ""),
        "title": record.get("title", ""),
        "type": record.get("type", ""),
        "author": record.get("author", ""),
        "author_link": record.get("author_link", ""),
        "blood_magic": record.get("blood_magic", ""),
        "uploaded_at": record.get("uploaded_at", ""),
        "last_updated": record.get("last_updated", ""),
        "intro": record.get("intro", ""),
    }
    for slot in range(1, 7):
        member = _member_by_slot(record, slot)
        row[f"pokemon_{slot}"] = member.get("pokemon", "")
        row[f"bloodline_{slot}"] = member.get("bloodline", "")
        row[f"nature_{slot}"] = member.get("nature", "")
        row[f"talents_{slot}"] = ",".join(member.get("talents") or [])
        row[f"skills_{slot}"] = ";".join(member.get("skills") or [])
    parse_status = record.get("parse_status") or {}
    row["parse_ok"] = parse_status.get("ok", False)
    row["warnings"] = ";".join(parse_status.get("warnings") or [])
    return row


def save_csv(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(".backup.csv"))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LINEUP_CSV_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(_lineup_to_csv_row(record))


def load_existing_lineups(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def index_lineups(records: list[dict]) -> dict[str, dict]:
    return {record.get("id", ""): record for record in records if record.get("id")}


def select_entries_to_fetch(
    entries: list[dict], existing_by_id: dict[str, dict], force: bool = False
) -> tuple[list[dict], list[dict]]:
    to_fetch: list[dict] = []
    skipped: list[dict] = []

    for entry in entries:
        entry_id = entry.get("id", "")
        existing = existing_by_id.get(entry_id)
        if force or existing is None:
            to_fetch.append(entry)
            continue
        if existing.get("last_updated", "") != entry.get("last_updated", ""):
            to_fetch.append(entry)
            continue
        skipped.append(existing)

    return to_fetch, skipped


def _lineup_sort_key(record: dict) -> tuple[str, tuple[int, int, int], str]:
    type_order = {"pvp": "0", "pve": "1"}
    record_type = record.get("type") or record.get("source", {}).get("list_section", "")
    date_parts = tuple(int(part) for part in record.get("last_updated", "0-0-0").split("-"))
    padded_date_parts = (date_parts + (0, 0, 0))[:3]
    return (type_order.get(record_type, "9"), tuple(-part for part in padded_date_parts), record.get("id", ""))


def merge_lineup_records(
    existing_records: list[dict], fetched_records: list[dict], failed_ids: set[str]
) -> list[dict]:
    del failed_ids
    merged = index_lineups(existing_records)
    for record in fetched_records:
        if record.get("id"):
            merged[record["id"]] = record

    return sorted(merged.values(), key=_lineup_sort_key)

BASE_URL = "https://wiki.biligame.com"
LIST_URL = "https://wiki.biligame.com/rocom/%E9%98%B5%E5%AE%B9%E4%B8%80%E8%A7%88"
API_URL = "https://wiki.biligame.com/rocom/api.php"

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

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _empty_lineup_from_entry(entry: dict | None = None) -> dict:
    entry = entry or {}
    return {
        "id": entry.get("id", ""),
        "title": entry.get("title", ""),
        "type": entry.get("list_section", ""),
        "author": "",
        "author_link": "",
        "intro": "",
        "blood_magic": "",
        "uploaded_at": "",
        "last_updated": entry.get("last_updated", ""),
        "source": {
            "page_title": entry.get("page_title", ""),
            "list_section": entry.get("list_section", ""),
        },
        "members": [],
        "parse_status": {"ok": False, "warnings": []},
    }


def _parse_template_fields(wikitext: str) -> dict[str, str] | None:
    match = re.search(r"\{\{\s*精灵阵容\s*(.*?)\n\s*\}\}", wikitext, re.DOTALL)
    if not match:
        return None

    fields: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "=" not in line:
            continue
        key, value = line[1:].split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def _split_csv_text(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _split_author(author: str) -> tuple[str, str]:
    match = re.fullmatch(r"\[(\S+)\s+(.+?)\]", author.strip())
    if not match:
        return author, ""
    return match.group(2).strip(), match.group(1).strip()


def parse_lineup_template(wikitext: str, entry: dict | None = None) -> dict:
    result = _empty_lineup_from_entry(entry)
    fields = _parse_template_fields(wikitext)
    if fields is None:
        result["parse_status"]["warnings"].append("lineup template not found")
        return result

    author, author_link = _split_author(fields.get("阵容作者", ""))
    result.update(
        {
            "id": fields.get("阵容编号", result["id"]),
            "title": fields.get("阵容标题", result["title"]),
            "type": fields.get("阵容类型", result["type"]),
            "author": author,
            "author_link": author_link,
            "intro": fields.get("阵容介绍", ""),
            "blood_magic": fields.get("阵容血脉魔法", ""),
            "uploaded_at": fields.get("阵容上传日期", ""),
        }
    )

    warnings: list[str] = []
    slots = sorted(
        {
            int(match.group(1))
            for key in fields
            if (match := re.fullmatch(r"阵容精灵(\d+)", key))
        }
    )

    for slot in slots:
        prefix = f"阵容精灵{slot}"
        pokemon = fields.get(prefix, "")
        if not pokemon:
            continue

        bloodline = fields.get(f"{prefix}血脉", "")
        nature = fields.get(f"{prefix}性格", "")
        talents = _split_csv_text(fields.get(f"{prefix}个体值", ""))
        skills = [
            skill
            for skill in (
                fields.get(f"{prefix}技能{skill_no}", "").strip()
                for skill_no in range(1, 5)
            )
            if skill
        ]

        result["members"].append(
            {
                "slot": slot,
                "pokemon": pokemon,
                "bloodline": bloodline,
                "nature": nature,
                "talents": talents,
                "skills": skills,
            }
        )

        if not bloodline:
            warnings.append(f"slot {slot} missing bloodline")
        if not nature:
            warnings.append(f"slot {slot} missing nature")
        if not talents:
            warnings.append(f"slot {slot} missing talents")
        if len(skills) != 4:
            warnings.append(f"slot {slot} has {len(skills)} skills")

    result["parse_status"] = {"ok": not warnings, "warnings": warnings}
    return result


def _extract_lineup_id(page_title: str, href: str) -> str:
    source = page_title or unquote(href)
    return source.rstrip("/").split("/")[-1]


def _extract_page_title(anchor) -> str:
    title = anchor.get("title", "").strip()
    if title:
        return title

    href = anchor.get("href", "")
    if "/rocom/" in href:
        return unquote(href.split("/rocom/", 1)[1])
    return unquote(href.strip("/"))


def _extract_last_updated(box) -> str:
    date_node = box.find("div", class_="rocom_lineup_list_date")
    if not date_node:
        return ""
    text = date_node.get_text(strip=True)
    return re.sub(r"^最后更新日期[:：]", "", text).strip()


def _extract_list_members(line_node) -> list[str]:
    members: list[tuple[int, str]] = []
    for item in line_node.find_all("div", class_="rocom_lineup_line_pet_item"):
        num_node = item.find("div", class_="rocom_lineup_line_pet_num")
        if not num_node:
            continue
        num_match = re.search(r"\d+", num_node.get_text(strip=True))
        if not num_match:
            continue
        name_node = item.find("div", class_="rocom_lineup_line_pet_name")
        if not name_node:
            continue
        members.append((int(num_match.group()), name_node.get_text(strip=True)))
    return [name for _, name in sorted(members)]


def _is_lineup_anchor(anchor) -> bool:
    href = unquote(anchor.get("href", ""))
    title = anchor.get("title", "")
    return "精灵阵容/" in href or "精灵阵容/" in title


def _parse_lineup_box(box, list_section: str) -> dict | None:
    line_node = box.find("div", class_="rocom_lineup_line_pet_list")
    if not line_node:
        return None

    anchor = line_node.find("a", href=re.compile(r"/rocom/%E7%B2%BE%E7%81%B5%E9%98%B5%E5%AE%B9/"))
    if not anchor:
        anchor = line_node.find("a", href=re.compile(r"/rocom/精灵阵容/"))
    if not anchor:
        anchor = line_node.find("a", href=True, title=True)
        if anchor and not _is_lineup_anchor(anchor):
            anchor = None
    if not anchor:
        return None

    page_title = _extract_page_title(anchor)
    href = anchor.get("href", "")
    title_node = line_node.find("div", class_="rocom_lineup_line_pet_edit")

    return {
        "id": _extract_lineup_id(page_title, href),
        "page_title": page_title,
        "list_section": list_section,
        "title": title_node.get_text(strip=True) if title_node else "",
        "last_updated": _extract_last_updated(box),
        "list_members": _extract_list_members(line_node),
    }


def parse_lineup_list_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    entries: list[dict] = []
    sections = {
        "pvp": "rocom_lineup_list_box_pvp_content",
        "pve": "rocom_lineup_list_box_pve_content",
    }

    for list_section, class_name in sections.items():
        section_node = soup.find("div", class_=class_name)
        if not section_node:
            continue
        for box in section_node.find_all("div", class_="rocom_lineup_line_pet_list_box"):
            entry = _parse_lineup_box(box, list_section)
            if entry:
                entries.append(entry)

    return entries


def print_progress(current: int, total: int, label: str = "", width: int = 28) -> None:
    filled = int(width * current / total) if total > 0 else 0
    bar = "#" * filled + "-" * (width - filled)
    pct = current / total * 100 if total > 0 else 0
    label = (label[:32] + "…") if len(label) > 33 else label
    print(f"\r[{current:>4}/{total}] {bar} {pct:5.1f}%  {label}    ", end="", flush=True)
    if current >= total:
        print()


def _request_with_retry(url: str, params: dict[str, str] | None = None, retries: int = 3) -> requests.Response:
    waits = [10, 20, 30]
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, params=params, timeout=15)
            if resp.status_code == 567:
                wait = waits[min(attempt, len(waits) - 1)]
                print(f"\n  [!] 触发反爬限制 (567)，等待 {wait}s 后重试 ({attempt + 1}/{retries})...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            wait = waits[min(attempt, len(waits) - 1)]
            print(f"\n  [!] 请求失败 ({attempt + 1}/{retries}): {exc}，等待 {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"无法抓取（已重试 {retries} 次）: {url}")


def fetch_text(url: str, retries: int = 3) -> str:
    return _request_with_retry(url, retries=retries).text


def parse_lineup_list_page(url: str = LIST_URL) -> list[dict]:
    print(f"[*] 抓取阵容列表页: {url}")
    return parse_lineup_list_html(fetch_text(url))


def build_api_params(page_title: str) -> dict[str, str]:
    return {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "titles": page_title,
        "rvprop": "content",
        "formatversion": "2",
    }


def extract_wikitext_from_api_response(payload: dict) -> str:
    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        raise RuntimeError("missing revision content")
    revisions = pages[0].get("revisions", [])
    if not revisions or "content" not in revisions[0]:
        raise RuntimeError("missing revision content")
    return revisions[0]["content"]


def fetch_lineup_wikitext(page_title: str) -> str:
    resp = _request_with_retry(API_URL, params=build_api_params(page_title))
    return extract_wikitext_from_api_response(resp.json())


def fetch_lineup_records(entries: list[dict], delay: float) -> tuple[list[dict], set[str], list[str]]:
    fetched: list[dict] = []
    failed_ids: set[str] = set()
    failed_labels: list[str] = []

    for index, entry in enumerate(entries, 1):
        label = f"{entry.get('list_section', '')} {entry.get('title') or entry.get('id', '')}"
        print_progress(index, len(entries), label)
        try:
            wikitext = fetch_lineup_wikitext(entry["page_title"])
            fetched.append(parse_lineup_template(wikitext, entry))
        except Exception as exc:
            failed_ids.add(entry.get("id", ""))
            failed_labels.append(f"{entry.get('page_title', entry.get('id', ''))}\t{exc}")
            print(f"\n  [!] 阵容详情失败 {entry.get('page_title', entry.get('id', ''))}: {exc}")
        time.sleep(delay)

    return fetched, failed_ids, failed_labels


def save_failed_lineups(failed_labels: list[str], path: Path) -> None:
    if not failed_labels:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(failed_labels), encoding="utf-8")


def run_scraper(output: Path, force: bool, limit: int, delay: float) -> int:
    existing_records = load_existing_lineups(output)
    existing_by_id = index_lineups(existing_records)

    try:
        entries = parse_lineup_list_page()
    except RuntimeError as exc:
        print(f"\n[!] 无法连接 wiki: {exc}")
        print("[!] 未覆盖旧数据")
        return 1

    if limit > 0:
        entries = entries[:limit]
        print(f"[*] 限制模式: 只处理前 {limit} 个阵容")

    to_fetch, skipped = select_entries_to_fetch(entries, existing_by_id, force=force)
    print(f"[*] 列表阵容: {len(entries)}，待抓取: {len(to_fetch)}，跳过: {len(skipped)}")

    fetched, failed_ids, failed_labels = fetch_lineup_records(to_fetch, delay)
    if to_fetch and not fetched:
        save_failed_lineups(failed_labels, output.parent / "failed_lineups.txt")
        print("\n[!] 所有待抓取阵容详情都失败了，已保留现有输出")
        return 1

    merged = merge_lineup_records(existing_records, fetched, failed_ids)

    save_json(merged, output)
    csv_path = output.with_suffix(".csv")
    save_csv(merged, csv_path)
    save_failed_lineups(failed_labels, output.parent / "failed_lineups.txt")

    print(f"\n[完成] 成功抓取: {len(fetched)}，跳过: {len(skipped)}，失败: {len(failed_ids)}")
    print(f"[完成] JSON 已保存至: {output.resolve()}")
    print(f"[完成] CSV  已保存至: {csv_path.resolve()}")
    if failed_labels:
        print(f"[完成] 失败记录已保存至: {(output.parent / 'failed_lineups.txt').resolve()}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="洛克王国 BWIKI 玩家阵容爬虫")
    parser.add_argument("--output", default="data/lineups.json", help="输出 JSON 路径")
    parser.add_argument("--force", action="store_true", help="强制重爬所有阵容")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个阵容，0 表示全部")
    parser.add_argument("--delay", type=float, default=2.0, help="详情请求间隔秒数，默认 2")
    args = parser.parse_args()

    raise SystemExit(run_scraper(Path(args.output), args.force, args.limit, max(args.delay, 2.0)))


if __name__ == "__main__":
    main()
