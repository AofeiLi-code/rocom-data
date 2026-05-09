import csv
import json
from pathlib import Path

import pytest

from lineup_scraper import (
    LINEUP_CSV_COLUMNS,
    build_api_params,
    extract_wikitext_from_api_response,
    fetch_lineup_wikitext,
    merge_lineup_records,
    parse_lineup_list_html,
    parse_lineup_template,
    run_scraper,
    save_csv,
    save_json,
    select_entries_to_fetch,
)


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
    assert result["author_link"] == ""
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


def test_parse_lineup_template_splits_author_link():
    wikitext = """{{精灵阵容
|阵容标题=链接作者阵容
|阵容作者=[https://space.bilibili.com/289211336 赛文]
|阵容类型=pvp
|阵容编号=linked-author
}}"""

    result = parse_lineup_template(wikitext, {"id": "linked-author"})

    assert result["author"] == "赛文"
    assert result["author_link"] == "https://space.bilibili.com/289211336"
    assert result["parse_status"] == {"ok": True, "warnings": []}


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
            "author_link": "",
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
    assert rows[0]["author"] == "mokuyo"
    assert rows[0]["author_link"] == ""
    assert rows[0]["pokemon_1"] == "彩蝶鲨"
    assert rows[0]["talents_1"] == "生命,魔攻,速度"
    assert rows[0]["skills_1"] == "翼击;贮藏;寒风吹;天洪"
    assert rows[0]["parse_ok"] == "False"
    assert rows[0]["warnings"] == "slot 2 missing pokemon"
    assert list(rows[0].keys()) == LINEUP_CSV_COLUMNS


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


def test_fetch_lineup_wikitext_uses_retry_request(monkeypatch):
    class FakeResponse:
        def json(self):
            return {
                "query": {
                    "pages": [
                        {
                            "revisions": [
                                {"content": "{{精灵阵容\n|阵容编号=abc\n}}"}
                            ]
                        }
                    ]
                }
            }

    calls = []

    def fake_request(url, params=None, retries=3):
        calls.append((url, params, retries))
        return FakeResponse()

    monkeypatch.setattr("lineup_scraper._request_with_retry", fake_request)

    assert fetch_lineup_wikitext("精灵阵容/abc") == "{{精灵阵容\n|阵容编号=abc\n}}"
    assert calls == [
        (
            "https://wiki.biligame.com/rocom/api.php",
            build_api_params("精灵阵容/abc"),
            3,
        )
    ]


def test_run_scraper_returns_failure_without_overwriting_when_all_details_fail(tmp_path, monkeypatch):
    output = tmp_path / "lineups.json"
    csv_output = tmp_path / "lineups.csv"
    output.write_text('[{"id":"old","type":"pvp","last_updated":"2026-5-1"}]', encoding="utf-8")
    csv_output.write_text("sentinel csv", encoding="utf-8")

    monkeypatch.setattr(
        "lineup_scraper.parse_lineup_list_page",
        lambda: [{"id": "new", "page_title": "精灵阵容/new", "last_updated": "2026-5-6"}],
    )
    monkeypatch.setattr(
        "lineup_scraper.fetch_lineup_records",
        lambda entries, delay: ([], {"new"}, ["精灵阵容/new\tfailed"]),
    )

    assert run_scraper(output, force=False, limit=0, delay=2.0) == 1
    assert json.loads(output.read_text(encoding="utf-8")) == [
        {"id": "old", "type": "pvp", "last_updated": "2026-5-1"}
    ]
    assert csv_output.read_text(encoding="utf-8") == "sentinel csv"
    assert (tmp_path / "failed_lineups.txt").read_text(encoding="utf-8") == "精灵阵容/new\tfailed"
