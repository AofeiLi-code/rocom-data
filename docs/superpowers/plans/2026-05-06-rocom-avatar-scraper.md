# Rocom Avatar Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add精灵头像同步到 `rocom_scraper.py` so the existing image URL pipeline can download upload-lineup page avatars into `data/images/avatars`.

**Architecture:** Keep the feature in `rocom_scraper.py`, but isolate upload-lineup avatar parsing from the existing sprite encyclopedia parsing. Reuse `_init_urls()`, `_add_url()`, `_flush_urls()`, and `data/urls.csv` by adding an `avatar` image type and a small avatar-only execution path.

**Tech Stack:** Python, requests, BeautifulSoup, pytest, existing CSV/JSON file helpers.

---

## File Structure

- Modify: `rocom_scraper.py`
  - Add `AVATAR_LIST_URL`.
  - Add `IMAGE_DIRS["avatar"] = "images/avatars"`.
  - Add avatar parsing helpers near the list-page parser section.
  - Add `download_avatar_images()`.
  - Extract the current sprite scrape body into `run_sprite_scraper(args)`.
  - Add `run_avatar_scraper(output: Path, force: bool)`.
  - Add CLI flags `--skip-avatars` and `--avatars-only`.
- Create: `tests/test_rocom_scraper.py`
  - Cover avatar name extraction, local sample HTML parsing, download pipeline calls, avatar-only flow, and default flow.
- Use existing fixture file: `data/阵容上传.html`
  - Read-only test input.

---

### Task 1: Add Avatar Parser Tests

**Files:**
- Create: `tests/test_rocom_scraper.py`

- [ ] **Step 1: Write failing tests for avatar name extraction and HTML parsing**

Create `tests/test_rocom_scraper.py` with this content:

```python
from pathlib import Path

from rocom_scraper import extract_avatar_name, parse_avatar_list_html


def test_extract_avatar_name_from_link_alt():
    assert extract_avatar_name("link=迪莫}}") == "迪莫"


def test_extract_avatar_name_from_spaced_link_title():
    assert extract_avatar_name(" link=鸭吉吉（蓬松的样子）}} ") == "鸭吉吉（蓬松的样子）"


def test_extract_avatar_name_falls_back_to_raw_text():
    assert extract_avatar_name("迪莫") == "迪莫"


def test_parse_avatar_list_html_extracts_names_urls_and_types():
    html = Path("data/阵容上传.html").read_text(encoding="utf-8")

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_rocom_scraper.py -q
```

Expected: FAIL with import errors for `extract_avatar_name` and `parse_avatar_list_html`.

---

### Task 2: Implement Avatar HTML Parsing

**Files:**
- Modify: `rocom_scraper.py`
- Test: `tests/test_rocom_scraper.py`

- [ ] **Step 1: Add avatar URL constant and image directory**

In `rocom_scraper.py`, update constants near `BASE_URL` and `LIST_URL`:

```python
BASE_URL = "https://wiki.biligame.com"
LIST_URL = "https://wiki.biligame.com/rocom/%E7%B2%BE%E7%81%B5%E5%9B%BE%E9%89%B4"
AVATAR_LIST_URL = "https://wiki.biligame.com/rocom/%E4%B8%8A%E4%BC%A0%E9%98%B5%E5%AE%B9"
```

Update `IMAGE_DIRS`:

```python
IMAGE_DIRS = {
    "sprite":    "images/sprites",    # 精灵立绘
    "attribute": "images/attributes", # 属性图标
    "skill":     "images/skills",     # 技能图标
    "ability":   "images/abilities",  # 特性图标
    "matchup":   "images/matchup",    # 克制表属性图标
    "avatar":    "images/avatars",    # 上传阵容页精灵头像
}
```

- [ ] **Step 2: Add avatar parser helpers**

Add these helpers after `img_alt_to_attr()` and before `parse_list_page()`:

```python
def fetch_text(url: str, retries: int = 3) -> str:
    """Fetch a page and return response text with the same retry behavior as fetch()."""
    return str(fetch(url, retries=retries))


def extract_avatar_name(raw: str) -> str:
    """Extract a sprite name from upload-lineup avatar alt/title text."""
    text = (raw or "").strip()
    match = re.fullmatch(r"link=(.+?)\}\}", text)
    if match:
        return match.group(1).strip()
    if text.startswith("link="):
        text = text[len("link="):]
    return text.removesuffix("}}").strip()


def _to_optional_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_avatar_list_html(html: str) -> list[dict]:
    """Parse upload-lineup page HTML and return avatar image records."""
    soup = BeautifulSoup(html, "html.parser")
    avatars: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for list_node in soup.find_all("div", class_="rocom_spirit_popup_overlay_list"):
        for box in list_node.find_all("div", class_="rocom_canlearn_img_box"):
            img = box.find("img")
            if not img:
                continue
            url = (img.get("src") or "").strip()
            if not url:
                continue
            name = extract_avatar_name(img.get("alt") or img.get("title") or "")
            if not name:
                continue
            key = (name, url)
            if key in seen:
                continue
            seen.add(key)
            avatars.append(
                {
                    "name": name,
                    "url": url,
                    "primary_type": (box.get("data-main") or "").strip(),
                    "secondary_type": (box.get("data-2") or "").strip(),
                    "width": _to_optional_int(img.get("data-file-width")),
                    "height": _to_optional_int(img.get("data-file-height")),
                }
            )

    return avatars


def parse_avatar_list_page(url: str = AVATAR_LIST_URL) -> list[dict]:
    """Fetch and parse the upload-lineup avatar list page."""
    print(f"[*] 抓取头像列表页: {url}")
    return parse_avatar_list_html(fetch_text(url))
```

- [ ] **Step 3: Run parser tests**

Run:

```bash
pytest tests/test_rocom_scraper.py -q
```

Expected: PASS for all tests in `tests/test_rocom_scraper.py`.

- [ ] **Step 4: Run existing lineup tests for quick regression signal**

Run:

```bash
pytest tests/test_lineup_scraper.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit parser work**

Run:

```bash
git add rocom_scraper.py tests/test_rocom_scraper.py
git commit -m "feat: parse rocom avatar list"
```

---

### Task 3: Add Avatar Download Pipeline

**Files:**
- Modify: `rocom_scraper.py`
- Modify: `tests/test_rocom_scraper.py`

- [ ] **Step 1: Add failing tests for download pipeline**

Append these tests to `tests/test_rocom_scraper.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_rocom_scraper.py -q
```

Expected: FAIL with missing `download_avatar_images`.

- [ ] **Step 3: Implement `download_avatar_images()`**

Add this function after `parse_avatar_list_page()`:

```python
def download_avatar_images(data_dir: Path, force: bool = False) -> dict:
    """Download upload-lineup avatar images through the shared URL pipeline."""
    avatars = parse_avatar_list_page()
    if not avatars:
        raise RuntimeError("avatar list not found")

    stats = {"total": len(avatars), "saved": 0, "failed": 0, "failed_urls": []}
    for index, avatar in enumerate(avatars, 1):
        print_progress(index, len(avatars), avatar["name"])
        local_path = _add_url(avatar["name"], "avatar", avatar["url"], data_dir, force)
        if local_path:
            stats["saved"] += 1
        else:
            stats["failed"] += 1
            stats["failed_urls"].append(avatar["url"])

    print(
        f"[*] 头像同步完成: 总数 {stats['total']}，"
        f"成功 {stats['saved']}，失败 {stats['failed']}"
    )
    return stats
```

- [ ] **Step 4: Run avatar tests**

Run:

```bash
pytest tests/test_rocom_scraper.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit download pipeline work**

Run:

```bash
git add rocom_scraper.py tests/test_rocom_scraper.py
git commit -m "feat: download rocom avatars"
```

---

### Task 4: Refactor CLI Into Testable Run Functions

**Files:**
- Modify: `rocom_scraper.py`
- Modify: `tests/test_rocom_scraper.py`

- [ ] **Step 1: Add failing CLI flow tests**

Append these tests to `tests/test_rocom_scraper.py`:

```python
def test_run_avatar_scraper_initializes_urls_and_writes_failures(tmp_path, monkeypatch):
    import rocom_scraper

    calls = []
    output = tmp_path / "sprites.json"

    monkeypatch.setattr(rocom_scraper, "_init_urls", lambda path: calls.append(("init", path)))
    monkeypatch.setattr(
        rocom_scraper,
        "download_avatar_images",
        lambda data_dir, force: {
            "total": 1,
            "saved": 0,
            "failed": 1,
            "failed_urls": ["https://patchwiki.biligame.com/images/rocom/a/a/a.png"],
        },
    )

    assert rocom_scraper.run_avatar_scraper(output, force=True) == 1

    assert calls == [("init", output)]
    assert (tmp_path / "failed_urls.txt").read_text(encoding="utf-8") == (
        "https://patchwiki.biligame.com/images/rocom/a/a/a.png"
    )
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
    monkeypatch.setattr(rocom_scraper, "_backfill_evolution_ids", lambda results: calls.append(("backfill", len(results))))
    monkeypatch.setattr(rocom_scraper, "_save", lambda results, path: calls.append(("save", path, len(results))))
    monkeypatch.setattr(rocom_scraper, "_save_csv", lambda results, path: calls.append(("csv", path, len(results))))
    monkeypatch.setattr(rocom_scraper, "_save_skills_csv", lambda results, path: calls.append(("skills", path, len(results))))
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
    monkeypatch.setattr(rocom_scraper, "download_avatar_images", lambda data_dir, force: calls.append("avatars"))

    assert rocom_scraper.run_sprite_scraper(args) == 0

    assert calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_rocom_scraper.py -q
```

Expected: FAIL with missing `run_avatar_scraper` and `run_sprite_scraper`.

- [ ] **Step 3: Extract current `main()` body into `run_sprite_scraper(args)`**

In `rocom_scraper.py`, replace the current `main()` body with a call to a new run function. The new `run_sprite_scraper(args) -> int` should contain the existing sprite scrape logic and return `0` on successful completion, `1` when list page access fails.

Use this structure:

```python
def _write_failed_urls(path: Path, failed_urls: list[str]) -> None:
    if not failed_urls:
        return
    path.write_text("\n".join(failed_urls), encoding="utf-8")


def run_sprite_scraper(args) -> int:
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data_dir = out_path.parent

    _init_urls(out_path)

    if args.force:
        for p in [data_dir / "skills.csv", data_dir / "urls.csv"]:
            if p.exists():
                p.unlink()
        _urls_cache.clear()

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
        return 1

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

    avatar_failed: list[str] = []
    if not getattr(args, "skip_avatars", False):
        try:
            avatar_stats = download_avatar_images(data_dir, args.force)
            avatar_failed = avatar_stats.get("failed_urls", [])
        except RuntimeError as exc:
            print(f"\n[!] 头像同步失败: {exc}")

    all_failed = failed + avatar_failed

    print(f"\n[完成] 成功: {len(results)-skipped}, 跳过: {skipped}, 失败: {len(failed)}")
    print(f"[完成] JSON 已保存至: {out_path.resolve()}")
    print(f"[完成] CSV  已保存至: {csv_path.resolve()}")
    print(f"[完成] 技能 已保存至: {(data_dir / 'skills.csv').resolve()}")
    print(f"[完成] URLs 已保存至: {(data_dir / 'urls.csv').resolve()}")

    if all_failed:
        fail_path = out_path.with_name("failed_urls.txt")
        _write_failed_urls(fail_path, all_failed)
        print(f"[完成] 失败URL已记录至: {fail_path}")

    return 0
```

Keep existing mojibake strings if preferred to reduce churn, but preserve the behavior and return values.

- [ ] **Step 4: Add `run_avatar_scraper()`**

Add this function before `main()`:

```python
def run_avatar_scraper(output: Path, force: bool) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    data_dir = output.parent
    _init_urls(output)

    try:
        stats = download_avatar_images(data_dir, force)
    except RuntimeError as exc:
        print(f"\n[!] 头像同步失败: {exc}")
        return 1

    failed_urls = stats.get("failed_urls", [])
    if failed_urls:
        fail_path = output.with_name("failed_urls.txt")
        _write_failed_urls(fail_path, failed_urls)
        print(f"[完成] 失败URL已记录至: {fail_path}")

    print(f"[完成] URLs 已保存至: {(data_dir / 'urls.csv').resolve()}")
    return 1 if failed_urls else 0
```

- [ ] **Step 5: Update `main()` CLI flags and dispatch**

Replace `main()` with:

```python
def main():
    parser = argparse.ArgumentParser(description="洛克王国精灵数据爬虫")
    parser.add_argument("--limit", type=int, default=0, help="只爬前 N 只(0=全部)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="请求间隔下限(秒)，实际为 delay~(delay+1.5) 随机值，默认 1.5")
    parser.add_argument("--output", default="data/sprites.json", help="输出路径")
    parser.add_argument("--force", action="store_true", help="强制重爬当前运行范围内的数据和图片")
    parser.add_argument("--skip-avatars", action="store_true", help="跳过上传阵容页精灵头像同步")
    parser.add_argument("--avatars-only", action="store_true", help="只同步上传阵容页精灵头像")
    args = parser.parse_args()

    out_path = Path(args.output)
    if args.avatars_only:
        raise SystemExit(run_avatar_scraper(out_path, args.force))
    raise SystemExit(run_sprite_scraper(args))
```

- [ ] **Step 6: Run CLI flow tests**

Run:

```bash
pytest tests/test_rocom_scraper.py -q
```

Expected: PASS.

- [ ] **Step 7: Run existing focused tests**

Run:

```bash
pytest tests/test_lineup_scraper.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit CLI refactor**

Run:

```bash
git add rocom_scraper.py tests/test_rocom_scraper.py
git commit -m "feat: add avatar scraper cli modes"
```

---

### Task 5: Verify Real Avatar Sync

**Files:**
- Runtime outputs expected:
  - `data/images/avatars/*`
  - `data/urls.csv`
  - Possibly `data/failed_urls.txt`

- [ ] **Step 1: Run all focused unit tests**

Run:

```bash
pytest tests/test_rocom_scraper.py tests/test_lineup_scraper.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the avatar-only scraper against the live page**

Run:

```bash
python rocom_scraper.py --avatars-only
```

Expected:

- Console prints the upload-lineup avatar list URL.
- Console prints avatar progress.
- `data/images/avatars` exists.
- `data/urls.csv` contains rows with `type` equal to `avatar`.

- [ ] **Step 3: Inspect avatar outputs**

Run:

```bash
Get-ChildItem -LiteralPath 'data/images/avatars' | Select-Object -First 10 Name,Length
```

Expected: At least one PNG file named after a sprite, such as `迪莫.png` if the live page still contains that avatar.

Run:

```bash
Select-String -LiteralPath 'data/urls.csv' -Pattern ',avatar,'
```

Expected: At least one matching `avatar` row with `images/avatars/` in `local_path`.

- [ ] **Step 4: Verify skip behavior by running avatar-only again**

Run:

```bash
python rocom_scraper.py --avatars-only
```

Expected:

- Existing files are not downloaded again.
- Command completes without duplicate rows for the same URL in `data/urls.csv`.

- [ ] **Step 5: Run final syntax check**

Run:

```bash
python -m py_compile rocom_scraper.py lineup_scraper.py
```

Expected: no output and exit code 0.

- [ ] **Step 6: Review diff**

Run:

```bash
git diff --stat HEAD~3..HEAD
git status --short
```

Expected:

- Commits include parser, download pipeline, and CLI mode changes.
- Working tree only includes expected runtime data changes from live sync.

Do not commit downloaded avatar images unless the project intentionally versions image assets. If the existing repo already versions `data/images/*`, stage them only after checking current project practice with:

```bash
git ls-files data/images | Select-Object -First 5
```

---

## Self-Review Checklist

- Spec coverage:
  - `data/images/avatars` handled by `IMAGE_DIRS["avatar"]`.
  - Live upload-lineup page handled by `AVATAR_LIST_URL` and `parse_avatar_list_page()`.
  - Existing URL pipeline reused via `_add_url()`.
  - Existing files skipped by unchanged `_add_url()` behavior.
  - `--skip-avatars` and `--avatars-only` included.
  - Avatar-only flow avoids writing sprite JSON/CSV/skills outputs.
- Completeness scan:
  - No task contains unresolved fill-in language.
- Type consistency:
  - Avatar records use `name`, `url`, `primary_type`, `secondary_type`, `width`, `height`.
  - Download stats use `total`, `saved`, `failed`, `failed_urls`.
  - CLI functions use `run_sprite_scraper(args)` and `run_avatar_scraper(output, force)`.
