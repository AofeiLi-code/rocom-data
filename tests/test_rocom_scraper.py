from pathlib import Path

from rocom_scraper import extract_avatar_name, parse_avatar_list_html


def test_extract_avatar_name_from_link_alt():
    assert extract_avatar_name("link=迪莫}}") == "迪莫"


def test_extract_avatar_name_from_spaced_link_title():
    assert extract_avatar_name(" link=鸭吉吉（蓬松的样子）}} ") == "鸭吉吉（蓬松的样子）"


def test_extract_avatar_name_falls_back_to_raw_text():
    assert extract_avatar_name("迪莫") == "迪莫"


def test_parse_avatar_list_html_extracts_names_urls_and_types():
    html = (Path(__file__).parent / "fixtures" / "rocom_avatar_list.html").read_text(
        encoding="utf-8"
    )

    avatars = parse_avatar_list_html(html)

    assert avatars
    by_name = {avatar["name"]: avatar for avatar in avatars}
    assert by_name["迪莫"]["url"] == (
        "https://patchwiki.biligame.com/images/rocom/d/de/"
        "n2a74bd4dvdud8b4t4819y9md4t811z.png"
    )
    assert by_name["迪莫"]["primary_type"] == "光"
    assert by_name["迪莫"]["secondary_type"] == ""
    assert by_name["迪莫"]["width"] == 256
    assert by_name["迪莫"]["height"] == 256
    assert by_name["魔力猫"]["primary_type"] == "草"
    assert by_name["鸭吉吉（蓬松的样子）"]["width"] == 109
    assert all("patchwiki.biligame.com" in avatar["url"] for avatar in avatars)


def test_parse_avatar_list_html_deduplicates_by_name_and_url():
    html = """
    <div class="rocom_spirit_popup_overlay_list">
      <div class="rocom_canlearn_img_box" data-main="光" data-2="">
        <img alt="link=迪莫}}" src="https://patchwiki.biligame.com/images/rocom/a/a/a.png"
             data-file-width="256" data-file-height="256" />
      </div>
      <div class="rocom_canlearn_img_box" data-main="光" data-2="">
        <img title="link=迪莫}}" src="https://patchwiki.biligame.com/images/rocom/a/a/a.png"
             data-file-width="256" data-file-height="256" />
      </div>
      <div class="rocom_canlearn_img_box" data-main="光" data-2="">
        <img alt="link=迪莫}}" src="https://patchwiki.biligame.com/images/rocom/b/b/b.png"
             data-file-width="256" data-file-height="256" />
      </div>
    </div>
    """

    avatars = parse_avatar_list_html(html)

    assert [(avatar["name"], avatar["url"]) for avatar in avatars] == [
        ("迪莫", "https://patchwiki.biligame.com/images/rocom/a/a/a.png"),
        ("迪莫", "https://patchwiki.biligame.com/images/rocom/b/b/b.png"),
    ]


def test_download_avatar_images_uses_avatar_image_type(tmp_path, monkeypatch):
    import rocom_scraper

    calls = []

    monkeypatch.setattr(
        rocom_scraper,
        "parse_avatar_list_page",
        lambda: [
            {"name": "迪莫", "url": "https://patchwiki.biligame.com/images/rocom/a/a/a.png"},
            {"name": "魔力猫", "url": "https://patchwiki.biligame.com/images/rocom/b/b/b.png"},
        ],
    )

    def fake_add_url(name, img_type, url, data_dir, force=False):
        calls.append((name, img_type, url, data_dir, force))
        return f"images/avatars/{name}.png"

    monkeypatch.setattr(rocom_scraper, "_add_url", fake_add_url)

    stats = rocom_scraper.download_avatar_images(tmp_path, force=True)

    assert stats == {"total": 2, "saved": 2, "failed": 0, "failed_urls": []}
    assert calls == [
        (
            "迪莫",
            "avatar",
            "https://patchwiki.biligame.com/images/rocom/a/a/a.png",
            tmp_path,
            True,
        ),
        (
            "魔力猫",
            "avatar",
            "https://patchwiki.biligame.com/images/rocom/b/b/b.png",
            tmp_path,
            True,
        ),
    ]


def test_download_avatar_images_reports_failed_local_paths(tmp_path, monkeypatch):
    import rocom_scraper

    monkeypatch.setattr(
        rocom_scraper,
        "parse_avatar_list_page",
        lambda: [{"name": "迪莫", "url": "https://patchwiki.biligame.com/images/rocom/a/a/a.png"}],
    )
    monkeypatch.setattr(rocom_scraper, "_add_url", lambda *args, **kwargs: "")

    stats = rocom_scraper.download_avatar_images(tmp_path, force=False)

    assert stats == {
        "total": 1,
        "saved": 0,
        "failed": 1,
        "failed_urls": ["https://patchwiki.biligame.com/images/rocom/a/a/a.png"],
    }


def test_download_avatar_images_initializes_url_pipeline_for_direct_call(tmp_path, monkeypatch, capsys):
    import rocom_scraper

    avatar_url = "https://patchwiki.biligame.com/images/rocom/a/a/dimo.png"

    class FakeResponse:
        content = b"fake image bytes"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(rocom_scraper, "_urls_path", None)
    rocom_scraper._urls_cache.clear()
    monkeypatch.setattr(
        rocom_scraper,
        "parse_avatar_list_page",
        lambda: [{"name": "迪莫", "url": avatar_url}],
    )
    monkeypatch.setattr(rocom_scraper.SESSION, "get", lambda url, timeout=15: FakeResponse())

    stats = rocom_scraper.download_avatar_images(tmp_path, force=False)

    urls_path = tmp_path / "urls.csv"
    avatar_path = tmp_path / "images" / "avatars" / "迪莫.png"
    assert stats == {"total": 1, "saved": 1, "failed": 0, "failed_urls": []}
    assert urls_path.exists()
    assert ",avatar," in urls_path.read_text(encoding="utf-8-sig")
    assert "images/avatars/迪莫.png" in urls_path.read_text(encoding="utf-8-sig")
    assert avatar_path.exists()
    assert avatar_path.read_bytes() == b"fake image bytes"
    assert "[完成] 头像" in capsys.readouterr().out


def test_download_avatar_images_preserves_existing_url_pipeline(tmp_path, monkeypatch):
    import rocom_scraper

    custom_urls_path = tmp_path / "custom" / "urls.csv"
    calls = []

    def fail_init_urls(out_path):
        raise AssertionError("_init_urls should not be called when _urls_path is already set")

    def fake_add_url(name, img_type, url, data_dir, force=False):
        calls.append((name, img_type, url, data_dir, force))
        return "images/avatars/迪莫.png"

    monkeypatch.setattr(rocom_scraper, "_urls_path", custom_urls_path)
    monkeypatch.setattr(rocom_scraper, "_init_urls", fail_init_urls)
    monkeypatch.setattr(
        rocom_scraper,
        "parse_avatar_list_page",
        lambda: [{"name": "迪莫", "url": "https://patchwiki.biligame.com/images/rocom/a/a/dimo.png"}],
    )
    monkeypatch.setattr(rocom_scraper, "_add_url", fake_add_url)

    stats = rocom_scraper.download_avatar_images(tmp_path, force=False)

    assert stats == {"total": 1, "saved": 1, "failed": 0, "failed_urls": []}
    assert rocom_scraper._urls_path == custom_urls_path
    assert calls == [
        (
            "迪莫",
            "avatar",
            "https://patchwiki.biligame.com/images/rocom/a/a/dimo.png",
            tmp_path,
            False,
        )
    ]


def test_run_avatar_scraper_initializes_urls_and_writes_failures(tmp_path, monkeypatch):
    import rocom_scraper

    calls = []
    output = tmp_path / "sprites.json"
    failed_url = "https://patchwiki.biligame.com/images/rocom/a/a/a.png"

    monkeypatch.setattr(rocom_scraper, "_urls_path", None)
    monkeypatch.setattr(rocom_scraper, "_init_urls", lambda path: calls.append(("init", path)))
    monkeypatch.setattr(
        rocom_scraper,
        "download_avatar_images",
        lambda data_dir, force: {
            "total": 1,
            "saved": 0,
            "failed": 1,
            "failed_urls": [failed_url],
        },
    )

    assert rocom_scraper.run_avatar_scraper(output, force=True) == 1

    assert calls == [("init", output)]
    assert (tmp_path / "failed_urls.txt").read_text(encoding="utf-8") == failed_url
    assert not output.exists()


def test_run_sprite_scraper_syncs_avatars_by_default(tmp_path, monkeypatch):
    import argparse
    import rocom_scraper

    output = tmp_path / "sprites.json"
    calls = []
    args = argparse.Namespace(
        limit=0,
        delay=1.5,
        output=str(output),
        force=False,
        skip_avatars=False,
    )

    monkeypatch.setattr(rocom_scraper, "_init_urls", lambda path: calls.append(("init", path)))
    monkeypatch.setattr(rocom_scraper, "parse_list_page", lambda: [])
    monkeypatch.setattr(
        rocom_scraper,
        "_backfill_evolution_ids",
        lambda results: calls.append(("backfill", len(results))),
    )
    monkeypatch.setattr(
        rocom_scraper,
        "_save",
        lambda results, path: calls.append(("save", path, len(results))),
    )
    monkeypatch.setattr(
        rocom_scraper,
        "_save_csv",
        lambda results, path: calls.append(("csv", path, len(results))),
    )
    monkeypatch.setattr(
        rocom_scraper,
        "_save_skills_csv",
        lambda results, path: calls.append(("skills", path, len(results))),
    )
    monkeypatch.setattr(
        rocom_scraper,
        "download_avatar_images",
        lambda data_dir, force: calls.append(("avatars", data_dir, force))
        or {"total": 0, "saved": 0, "failed": 0, "failed_urls": []},
    )

    assert rocom_scraper.run_sprite_scraper(args) == 0

    assert ("avatars", tmp_path, False) in calls
    assert ("save", output, 0) in calls


def test_run_sprite_scraper_can_skip_avatars(tmp_path, monkeypatch):
    import argparse
    import rocom_scraper

    output = tmp_path / "sprites.json"
    calls = []
    args = argparse.Namespace(
        limit=0,
        delay=1.5,
        output=str(output),
        force=False,
        skip_avatars=True,
    )

    monkeypatch.setattr(rocom_scraper, "_init_urls", lambda path: None)
    monkeypatch.setattr(rocom_scraper, "parse_list_page", lambda: [])
    monkeypatch.setattr(rocom_scraper, "_backfill_evolution_ids", lambda results: None)
    monkeypatch.setattr(rocom_scraper, "_save", lambda results, path: None)
    monkeypatch.setattr(rocom_scraper, "_save_csv", lambda results, path: None)
    monkeypatch.setattr(rocom_scraper, "_save_skills_csv", lambda results, path: None)
    monkeypatch.setattr(
        rocom_scraper,
        "download_avatar_images",
        lambda data_dir, force: calls.append("avatars"),
    )

    assert rocom_scraper.run_sprite_scraper(args) == 0

    assert calls == []
