# BWIKI Lineup Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent BWIKI player lineup scraper that archives text-only lineup data to `data/lineups.json` and `data/lineups.csv` with incremental updates and tests.

**Architecture:** Add a focused `lineup_scraper.py` script in `rocom-data` with pure parsing functions for tests, thin network wrappers for BWIKI requests, and output helpers for JSON/CSV. Keep this dataset separate from `data/teams.json` and do not save or download image URLs.

**Tech Stack:** Python 3, `requests`, `beautifulsoup4`, standard-library `argparse`, `csv`, `json`, `shutil`, `time`, `urllib.parse`, and `pytest`.

---

## File Structure

- Create: `lineup_scraper.py`
  - Owns BWIKI lineup list parsing, MediaWiki API detail fetching, wikitext template parsing, incremental selection, JSON/CSV saving, progress display, and CLI entry point.
  - Exposes pure helpers so unit tests can run without network calls.
- Create: `tests/test_lineup_scraper.py`
  - Unit tests for list HTML parsing, wikitext parsing, incremental decisions, merge behavior, and CSV output.
- Existing read-only fixture: `data/阵容一览.html`
  - Used by tests as the local sample list page. Tests must not mutate it.
- Output files created by runtime, not committed by the plan:
  - `data/lineups.json`
  - `data/lineups.csv`
  - `data/failed_lineups.txt`

---

### Task 1: Wikitext Template Parser

**Files:**
- Create: `lineup_scraper.py`
- Create: `tests/test_lineup_scraper.py`

- [ ] **Step 1: Write the failing wikitext parser test**

Create `tests/test_lineup_scraper.py` with this content:

```python
from pathlib import Path

import pytest

from lineup_scraper import parse_lineup_template


SAMPLE_WIKITEXT = """{{精灵阵容
|阵容标题=暂定
|阵容血脉魔法=进化之力
|阵容介绍=没
|阵容作者=mokuyo
|阵容类型=pvp
|阵容上传日期=2026-5-5
|阵容精灵1=彩蝶鲨
|阵容精灵1血脉=首领
|阵容精灵1性格=胆小
|阵容精灵1个体值=生命,魔攻,速度
|阵容精灵1技能1=翼击
|阵容精灵1技能2=贮藏
|阵容精灵1技能3=寒风吹
|阵容精灵1技能4=天洪
|阵容精灵2=锤头鹳
|阵容精灵2血脉=幽
|阵容精灵2性格=平和
|阵容精灵2个体值=生命,物攻,物防
|阵容精灵2技能1=潮涌
|阵容精灵2技能2=虚假破产
|阵容精灵2技能3=勾魂
|阵容精灵2技能4=取念
|阵容精灵3=叮叮恶魔
|阵容精灵3血脉=武
|阵容精灵3性格=固执
|阵容精灵3个体值=生命,物攻,速度
|阵容精灵3技能1=缠丝劲
|阵容精灵3技能2=乘风
|阵容精灵3技能3=羽化加速
|阵容精灵3技能4=撕咬
|阵容精灵4=红绒十字
|阵容精灵4血脉=地
|阵容精灵4性格=保守
|阵容精灵4个体值=生命,魔攻,速度
|阵容精灵4技能1=引燃
|阵容精灵4技能2=焚烧烙印
|阵容精灵4技能3=泥浆铠甲
|阵容精灵4技能4=除厄
|阵容精灵5=圣剑-X
|阵容精灵5血脉=首领
|阵容精灵5性格=平和
|阵容精灵5个体值=生命,物攻,速度
|阵容精灵5技能1=齿轮扭矩
|阵容精灵5技能2=啮合传递
|阵容精灵5技能3=休息回复
|阵容精灵5技能4=齿轮切开
|阵容精灵6=石冠王蜥（本来的样子）
|阵容精灵6血脉=翼
|阵容精灵6性格=平和
|阵容精灵6个体值=生命,物防,魔防
|阵容精灵6技能1=风墙
|阵容精灵6技能2=地刺
|阵容精灵6技能3=复写
|阵容精灵6技能4=冲撞
|阵容编号=0c4a56e20142767d1be32461465fdb0e
}}"""


def test_parse_lineup_template_extracts_metadata_and_members():
    result = parse_lineup_template(
        SAMPLE_WIKITEXT,
        {
            "id": "0c4a56e20142767d1be32461465fdb0e",
            "last_updated": "2026-5-5",
            "page_title": "精灵阵容/0c4a56e20142767d1be32461465fdb0e",
            "list_section": "pvp",
            "title": "暂定",
        },
    )

    assert result["id"] == "0c4a56e20142767d1be32461465fdb0e"
    assert result["title"] == "暂定"
    assert result["type"] == "pvp"
    assert result["author"] == "mokuyo"
    assert result["intro"] == "没"
    assert result["blood_magic"] == "进化之力"
    assert result["uploaded_at"] == "2026-5-5"
    assert result["last_updated"] == "2026-5-5"
    assert result["source"] == {
        "page_title": "精灵阵容/0c4a56e20142767d1be32461465fdb0e",
        "list_section": "pvp",
    }
    assert result["parse_status"] == {"ok": True, "warnings": []}

    assert len(result["members"]) == 6
    assert result["members"][0] == {
        "slot": 1,
        "pokemon": "彩蝶鲨",
        "bloodline": "首领",
        "nature": "胆小",
        "talents": ["生命", "魔攻", "速度"],
        "skills": ["翼击", "贮藏", "寒风吹", "天洪"],
    }
    assert result["members"][5]["pokemon"] == "石冠王蜥（本来的样子）"
    assert result["members"][5]["skills"] == ["风墙", "地刺", "复写", "冲撞"]


def test_parse_lineup_template_warns_for_missing_member_fields():
    wikitext = """{{精灵阵容
|阵容标题=缺字段阵容
|阵容类型=pve
|阵容编号=abc
|阵容精灵1=彩蝶鲨
|阵容精灵1技能1=翼击
}}"""

    result = parse_lineup_template(
        wikitext,
        {
            "id": "abc",
            "last_updated": "2026-5-6",
            "page_title": "精灵阵容/abc",
            "list_section": "pve",
            "title": "缺字段阵容",
        },
    )

    assert result["parse_status"]["ok"] is False
    assert result["members"] == [
        {
            "slot": 1,
            "pokemon": "彩蝶鲨",
            "bloodline": "",
            "nature": "",
            "talents": [],
            "skills": ["翼击"],
        }
    ]
    assert "slot 1 missing bloodline" in result["parse_status"]["warnings"]
    assert "slot 1 missing nature" in result["parse_status"]["warnings"]
    assert "slot 1 missing talents" in result["parse_status"]["warnings"]
    assert "slot 1 has 1 skills" in result["parse_status"]["warnings"]


def test_parse_lineup_template_handles_missing_template():
    result = parse_lineup_template(
        "not a lineup template",
        {
            "id": "missing",
            "last_updated": "2026-5-6",
            "page_title": "精灵阵容/missing",
            "list_section": "pvp",
            "title": "列表标题",
        },
    )

    assert result["id"] == "missing"
    assert result["title"] == "列表标题"
    assert result["type"] == "pvp"
    assert result["members"] == []
    assert result["parse_status"]["ok"] is False
    assert result["parse_status"]["warnings"] == ["lineup template not found"]
```

- [ ] **Step 2: Run the parser tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k parse_lineup_template -v
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'lineup_scraper'` or FAIL because `parse_lineup_template` is not defined.

- [ ] **Step 3: Implement the minimal parser**

Create `lineup_scraper.py` with this content:

```python
"""
洛克王国 BWIKI 玩家阵容爬虫。

输出: data/lineups.json 和 data/lineups.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import time
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

import requests
from bs4 import BeautifulSoup

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


def _empty_lineup_from_entry(entry: dict, warning: str) -> dict:
    return {
        "id": entry.get("id", ""),
        "title": entry.get("title", ""),
        "type": entry.get("list_section", ""),
        "author": "",
        "intro": "",
        "blood_magic": "",
        "uploaded_at": "",
        "last_updated": entry.get("last_updated", ""),
        "source": {
            "page_title": entry.get("page_title", ""),
            "list_section": entry.get("list_section", ""),
        },
        "members": [],
        "parse_status": {"ok": False, "warnings": [warning]},
    }


def _parse_template_fields(wikitext: str) -> dict[str, str] | None:
    if "{{精灵阵容" not in wikitext:
        return None

    fields: dict[str, str] = {}
    for raw_line in wikitext.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "=" not in line:
            continue
        key, value = line[1:].split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def _split_csv_text(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_lineup_template(wikitext: str, entry: dict | None = None) -> dict:
    entry = entry or {}
    fields = _parse_template_fields(wikitext)
    if fields is None:
        return _empty_lineup_from_entry(entry, "lineup template not found")

    warnings: list[str] = []
    members: list[dict] = []

    for slot in range(1, 7):
        pokemon = fields.get(f"阵容精灵{slot}", "").strip()
        if not pokemon:
            continue

        bloodline = fields.get(f"阵容精灵{slot}血脉", "").strip()
        nature = fields.get(f"阵容精灵{slot}性格", "").strip()
        talents = _split_csv_text(fields.get(f"阵容精灵{slot}个体值", ""))
        skills = [
            fields.get(f"阵容精灵{slot}技能{skill_index}", "").strip()
            for skill_index in range(1, 5)
        ]
        skills = [skill for skill in skills if skill]

        if not bloodline:
            warnings.append(f"slot {slot} missing bloodline")
        if not nature:
            warnings.append(f"slot {slot} missing nature")
        if not talents:
            warnings.append(f"slot {slot} missing talents")
        if len(skills) != 4:
            warnings.append(f"slot {slot} has {len(skills)} skills")

        members.append(
            {
                "slot": slot,
                "pokemon": pokemon,
                "bloodline": bloodline,
                "nature": nature,
                "talents": talents,
                "skills": skills,
            }
        )

    lineup_id = fields.get("阵容编号", "").strip() or entry.get("id", "")
    lineup_type = fields.get("阵容类型", "").strip() or entry.get("list_section", "")

    return {
        "id": lineup_id,
        "title": fields.get("阵容标题", "").strip() or entry.get("title", ""),
        "type": lineup_type,
        "author": fields.get("阵容作者", "").strip(),
        "intro": fields.get("阵容介绍", "").strip(),
        "blood_magic": fields.get("阵容血脉魔法", "").strip(),
        "uploaded_at": fields.get("阵容上传日期", "").strip(),
        "last_updated": entry.get("last_updated", ""),
        "source": {
            "page_title": entry.get("page_title", f"精灵阵容/{lineup_id}" if lineup_id else ""),
            "list_section": entry.get("list_section", lineup_type),
        },
        "members": members,
        "parse_status": {"ok": not warnings, "warnings": warnings},
    }
```

- [ ] **Step 4: Run the parser tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k parse_lineup_template -v
```

Expected: PASS for the three `parse_lineup_template` tests.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add "lineup_scraper.py" "tests/test_lineup_scraper.py"
git commit -m @'
feat: parse BWIKI lineup templates
'@
```

---

### Task 2: List Page Parser

**Files:**
- Modify: `lineup_scraper.py`
- Modify: `tests/test_lineup_scraper.py`

- [ ] **Step 1: Add failing list parser tests**

Append this content to `tests/test_lineup_scraper.py`:

```python
from lineup_scraper import parse_lineup_list_html


def test_parse_lineup_list_html_extracts_sections_and_text_fields():
    html = Path("data/阵容一览.html").read_text(encoding="utf-8")

    entries = parse_lineup_list_html(html)

    assert entries
    assert {entry["list_section"] for entry in entries} <= {"pvp", "pve"}
    assert {entry["list_section"] for entry in entries}

    first = entries[0]
    assert first["id"]
    assert first["page_title"].startswith("精灵阵容/")
    assert first["title"]
    assert first["last_updated"]
    assert isinstance(first["list_members"], list)
    assert len(first["list_members"]) <= 6


def test_parse_lineup_list_html_does_not_store_image_urls():
    html = Path("data/阵容一览.html").read_text(encoding="utf-8")

    entries = parse_lineup_list_html(html)

    serialized = json.dumps(entries, ensure_ascii=False)
    assert "patchwiki.biligame.com" not in serialized
    assert "src" not in entries[0]
    assert "image" not in entries[0]
    assert "img" not in entries[0]
```

Also change the imports at the top of `tests/test_lineup_scraper.py` to include `json`:

```python
import json
from pathlib import Path

import pytest

from lineup_scraper import parse_lineup_template
```

- [ ] **Step 2: Run the list parser tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k parse_lineup_list_html -v
```

Expected: FAIL with `ImportError` or `NameError` for `parse_lineup_list_html`.

- [ ] **Step 3: Implement list parser helpers**

Append this code to `lineup_scraper.py` after `parse_lineup_template`:

```python

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


def _parse_lineup_box(box, list_section: str) -> dict | None:
    line_node = box.find("div", class_="rocom_lineup_line_pet_list")
    if not line_node:
        return None

    anchor = line_node.find("a", href=re.compile(r"/rocom/%E7%B2%BE%E7%81%B5%E9%98%B5%E5%AE%B9/"))
    if not anchor:
        anchor = line_node.find("a", href=re.compile(r"/rocom/精灵阵容/"))
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
```

- [ ] **Step 4: Run the list parser tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k parse_lineup_list_html -v
```

Expected: PASS for both list parser tests.

- [ ] **Step 5: Run all current lineup scraper tests**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -v
```

Expected: PASS for all current tests.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add "lineup_scraper.py" "tests/test_lineup_scraper.py"
git commit -m @'
feat: parse BWIKI lineup list page
'@
```

---

### Task 3: Incremental Selection and Merge Behavior

**Files:**
- Modify: `lineup_scraper.py`
- Modify: `tests/test_lineup_scraper.py`

- [ ] **Step 1: Add failing incremental tests**

Append this content to `tests/test_lineup_scraper.py`:

```python
from lineup_scraper import merge_lineup_records, select_entries_to_fetch


def test_select_entries_to_fetch_skips_unchanged_existing_records():
    entries = [
        {"id": "same", "last_updated": "2026-5-5"},
        {"id": "new", "last_updated": "2026-5-6"},
        {"id": "changed", "last_updated": "2026-5-7"},
    ]
    existing = {
        "same": {"id": "same", "last_updated": "2026-5-5"},
        "changed": {"id": "changed", "last_updated": "2026-5-1"},
    }

    to_fetch, skipped = select_entries_to_fetch(entries, existing, force=False)

    assert [entry["id"] for entry in to_fetch] == ["new", "changed"]
    assert [record["id"] for record in skipped] == ["same"]


def test_select_entries_to_fetch_force_fetches_everything():
    entries = [
        {"id": "same", "last_updated": "2026-5-5"},
        {"id": "new", "last_updated": "2026-5-6"},
    ]
    existing = {"same": {"id": "same", "last_updated": "2026-5-5"}}

    to_fetch, skipped = select_entries_to_fetch(entries, existing, force=True)

    assert [entry["id"] for entry in to_fetch] == ["same", "new"]
    assert skipped == []


def test_merge_lineup_records_replaces_changed_records_and_keeps_old_failures():
    existing_records = [
        {"id": "same", "type": "pvp", "last_updated": "2026-5-5"},
        {"id": "changed", "type": "pvp", "last_updated": "2026-5-1", "title": "old"},
        {"id": "failed", "type": "pve", "last_updated": "2026-5-1", "title": "kept"},
    ]
    fetched_records = [
        {"id": "changed", "type": "pvp", "last_updated": "2026-5-7", "title": "new"},
        {"id": "brand-new", "type": "pve", "last_updated": "2026-5-8", "title": "added"},
    ]
    failed_ids = {"failed"}

    merged = merge_lineup_records(existing_records, fetched_records, failed_ids)

    assert [record["id"] for record in merged] == ["changed", "same", "brand-new", "failed"]
    assert next(record for record in merged if record["id"] == "changed")["title"] == "new"
    assert next(record for record in merged if record["id"] == "failed")["title"] == "kept"
```

- [ ] **Step 2: Run incremental tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k "select_entries_to_fetch or merge_lineup_records" -v
```

Expected: FAIL with missing imports for `select_entries_to_fetch` and `merge_lineup_records`.

- [ ] **Step 3: Implement incremental helpers**

Append this code to `lineup_scraper.py`:

```python

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


def _lineup_sort_key(record: dict) -> tuple[str, str, str]:
    type_order = {"pvp": "0", "pve": "1"}
    record_type = record.get("type") or record.get("source", {}).get("list_section", "")
    return (type_order.get(record_type, "9"), record.get("last_updated", ""), record.get("id", ""))


def merge_lineup_records(
    existing_records: list[dict], fetched_records: list[dict], failed_ids: set[str]
) -> list[dict]:
    merged = index_lineups(existing_records)
    for record in fetched_records:
        if record.get("id"):
            merged[record["id"]] = record

    for failed_id in failed_ids:
        if failed_id not in merged:
            continue

    return sorted(merged.values(), key=_lineup_sort_key)
```

- [ ] **Step 4: Run incremental tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k "select_entries_to_fetch or merge_lineup_records" -v
```

Expected: PASS for all incremental tests.

- [ ] **Step 5: Run all current lineup scraper tests**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -v
```

Expected: PASS for all current tests.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add "lineup_scraper.py" "tests/test_lineup_scraper.py"
git commit -m @'
feat: add lineup incremental merge logic
'@
```

---

### Task 4: CSV and JSON Output Helpers

**Files:**
- Modify: `lineup_scraper.py`
- Modify: `tests/test_lineup_scraper.py`

- [ ] **Step 1: Add failing output tests**

Append this content to `tests/test_lineup_scraper.py`:

```python
from lineup_scraper import LINEUP_CSV_COLUMNS, save_csv, save_json


def test_save_json_writes_utf8_indented_file(tmp_path):
    output = tmp_path / "lineups.json"
    records = [{"id": "abc", "title": "中文阵容"}]

    save_json(records, output)

    text = output.read_text(encoding="utf-8")
    assert "中文阵容" in text
    assert text.startswith("[\n  {")


def test_save_json_creates_backup_when_overwriting(tmp_path):
    output = tmp_path / "lineups.json"
    output.write_text('[{"id":"old"}]', encoding="utf-8")

    save_json([{"id": "new"}], output)

    assert (tmp_path / "lineups.backup.json").exists()
    assert json.loads((tmp_path / "lineups.backup.json").read_text(encoding="utf-8")) == [{"id": "old"}]
    assert json.loads(output.read_text(encoding="utf-8")) == [{"id": "new"}]


def test_save_csv_flattens_members_and_warnings(tmp_path):
    output = tmp_path / "lineups.csv"
    records = [
        {
            "id": "abc",
            "title": "暂定",
            "type": "pvp",
            "author": "mokuyo",
            "intro": "没",
            "blood_magic": "进化之力",
            "uploaded_at": "2026-5-5",
            "last_updated": "2026-5-5",
            "members": [
                {
                    "slot": 1,
                    "pokemon": "彩蝶鲨",
                    "bloodline": "首领",
                    "nature": "胆小",
                    "talents": ["生命", "魔攻", "速度"],
                    "skills": ["翼击", "贮藏", "寒风吹", "天洪"],
                }
            ],
            "parse_status": {"ok": False, "warnings": ["slot 2 missing pokemon"]},
        }
    ]

    save_csv(records, output)

    with open(output, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["id"] == "abc"
    assert rows[0]["pokemon_1"] == "彩蝶鲨"
    assert rows[0]["talents_1"] == "生命,魔攻,速度"
    assert rows[0]["skills_1"] == "翼击;贮藏;寒风吹;天洪"
    assert rows[0]["parse_ok"] == "False"
    assert rows[0]["warnings"] == "slot 2 missing pokemon"
    assert list(rows[0].keys()) == LINEUP_CSV_COLUMNS
```

Also change the imports at the top of `tests/test_lineup_scraper.py` to include `csv`:

```python
import csv
import json
from pathlib import Path
```

- [ ] **Step 2: Run output tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k "save_json or save_csv" -v
```

Expected: FAIL with missing imports for `save_json`, `save_csv`, or `LINEUP_CSV_COLUMNS`.

- [ ] **Step 3: Implement output helpers**

Append this code to `lineup_scraper.py`:

```python

LINEUP_CSV_COLUMNS = [
    "id",
    "title",
    "type",
    "author",
    "blood_magic",
    "uploaded_at",
    "last_updated",
    "intro",
    "pokemon_1",
    "bloodline_1",
    "nature_1",
    "talents_1",
    "skills_1",
    "pokemon_2",
    "bloodline_2",
    "nature_2",
    "talents_2",
    "skills_2",
    "pokemon_3",
    "bloodline_3",
    "nature_3",
    "talents_3",
    "skills_3",
    "pokemon_4",
    "bloodline_4",
    "nature_4",
    "talents_4",
    "skills_4",
    "pokemon_5",
    "bloodline_5",
    "nature_5",
    "talents_5",
    "skills_5",
    "pokemon_6",
    "bloodline_6",
    "nature_6",
    "talents_6",
    "skills_6",
    "parse_ok",
    "warnings",
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
```

- [ ] **Step 4: Run output tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k "save_json or save_csv" -v
```

Expected: PASS for all output helper tests.

- [ ] **Step 5: Run all current lineup scraper tests**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -v
```

Expected: PASS for all current tests.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add "lineup_scraper.py" "tests/test_lineup_scraper.py"
git commit -m @'
feat: save lineup archives as json and csv
'@
```

---

### Task 5: Network Fetching, Progress, and CLI

**Files:**
- Modify: `lineup_scraper.py`
- Modify: `tests/test_lineup_scraper.py`

- [ ] **Step 1: Add failing network wrapper tests without real network calls**

Append this content to `tests/test_lineup_scraper.py`:

```python
from lineup_scraper import build_api_params, extract_wikitext_from_api_response


def test_build_api_params_uses_page_title():
    params = build_api_params("精灵阵容/abc")

    assert params == {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "titles": "精灵阵容/abc",
        "rvprop": "content",
        "formatversion": "2",
    }


def test_extract_wikitext_from_api_response_reads_revision_content():
    payload = {
        "query": {
            "pages": [
                {
                    "pageid": 1,
                    "title": "精灵阵容/abc",
                    "revisions": [{"content": "{{精灵阵容\n|阵容编号=abc\n}}"}],
                }
            ]
        }
    }

    assert extract_wikitext_from_api_response(payload) == "{{精灵阵容\n|阵容编号=abc\n}}"


def test_extract_wikitext_from_api_response_rejects_missing_revision():
    with pytest.raises(RuntimeError, match="missing revision content"):
        extract_wikitext_from_api_response({"query": {"pages": [{"title": "精灵阵容/abc"}]}})
```

- [ ] **Step 2: Run network wrapper tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k "build_api_params or extract_wikitext" -v
```

Expected: FAIL with missing imports for `build_api_params` and `extract_wikitext_from_api_response`.

- [ ] **Step 3: Implement network wrappers and CLI orchestration**

Append this code to `lineup_scraper.py`:

```python

def print_progress(current: int, total: int, label: str = "", width: int = 28) -> None:
    filled = int(width * current / total) if total > 0 else 0
    bar = "#" * filled + "-" * (width - filled)
    pct = current / total * 100 if total > 0 else 0
    label = (label[:32] + "…") if len(label) > 33 else label
    print(f"\r[{current:>4}/{total}] {bar} {pct:5.1f}%  {label}    ", end="", flush=True)
    if current >= total:
        print()


def fetch_text(url: str, retries: int = 3) -> str:
    waits = [10, 20, 30]
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, timeout=15)
            if resp.status_code == 567:
                wait = waits[min(attempt, len(waits) - 1)]
                print(f"\n  [!] 触发反爬限制 (567)，等待 {wait}s 后重试 ({attempt + 1}/{retries})...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            wait = waits[min(attempt, len(waits) - 1)]
            print(f"\n  [!] 请求失败 ({attempt + 1}/{retries}): {exc}，等待 {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"无法抓取（已重试 {retries} 次）: {url}")


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
    resp = SESSION.get(API_URL, params=build_api_params(page_title), timeout=15)
    if resp.status_code == 567:
        raise RuntimeError("anti-scraping response 567")
    resp.raise_for_status()
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
```

- [ ] **Step 4: Run network wrapper tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -k "build_api_params or extract_wikitext" -v
```

Expected: PASS for all network wrapper tests.

- [ ] **Step 5: Run all unit tests for lineup scraper**

Run:

```powershell
python -m pytest tests/test_lineup_scraper.py -v
```

Expected: PASS for all tests in `tests/test_lineup_scraper.py`.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add "lineup_scraper.py" "tests/test_lineup_scraper.py"
git commit -m @'
feat: add BWIKI lineup scraper CLI
'@
```

---

### Task 6: Local Smoke Run and Full Test Check

**Files:**
- Runtime output: `data/lineups.json`
- Runtime output: `data/lineups.csv`
- Runtime output when failures occur: `data/failed_lineups.txt`

- [ ] **Step 1: Run a limited live scrape**

Run:

```powershell
python lineup_scraper.py --limit 1 --delay 2
```

Expected: The command prints the list count, fetches one lineup detail, waits at least 2 seconds after the detail request, and writes `data/lineups.json` plus `data/lineups.csv`.

- [ ] **Step 2: Inspect the generated JSON shape**

Run:

```powershell
python -c "import json; d=json.load(open('data/lineups.json', encoding='utf-8')); assert isinstance(d, list) and d; r=d[0]; assert {'id','title','type','author','intro','blood_magic','uploaded_at','last_updated','source','members','parse_status'} <= set(r); print(r['id'], r['title'], len(r['members']))"
```

Expected: Prints one lineup id, title, and member count without assertion errors.

- [ ] **Step 3: Verify image URLs were not saved**

Run:

```powershell
python -c "from pathlib import Path; text=Path('data/lineups.json').read_text(encoding='utf-8'); assert 'patchwiki.biligame.com' not in text; assert 'data-file-width' not in text; print('no image urls saved')"
```

Expected: Prints `no image urls saved`.

- [ ] **Step 4: Run all rocom-data tests**

Run:

```powershell
python -m pytest tests
```

Expected: Existing tests plus `tests/test_lineup_scraper.py` pass. If pre-existing tests fail outside `tests/test_lineup_scraper.py`, capture the failing test names and error messages before changing any code.

- [ ] **Step 5: Commit generated scraper outputs only if the user wants data files tracked**

Ask the user whether to track the generated files from the smoke run.

If the user says not to track generated outputs, do not commit `data/lineups.json`, `data/lineups.csv`, or `data/failed_lineups.txt`.

If the user says to track generated outputs, run:

```powershell
git add "data/lineups.json" "data/lineups.csv"
if (Test-Path "data/failed_lineups.txt") { git add "data/failed_lineups.txt" }
git commit -m @'
data: add scraped BWIKI lineup archive
'@
```

Expected: A data commit is created only when explicitly approved.

---

## Self-Review

- Spec coverage: The plan covers independent `lineup_scraper.py`, text-only JSON/CSV, list parsing, details API parsing, 2-second delay, progress display, incremental skipping/updating, warning preservation, failed detail records, backups, and tests.
- Placeholder scan: The plan contains concrete file paths, commands, expected results, and code snippets for each implementation step.
- Type consistency: The plan consistently uses `id`, `title`, `type`, `author`, `intro`, `blood_magic`, `uploaded_at`, `last_updated`, `source`, `members`, `parse_status`, `list_section`, `page_title`, and `list_members`.
