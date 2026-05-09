# 洛克王国精灵头像爬取设计

## 背景

当前 `rocom_scraper.py` 已负责洛克王国 BWIKI 精灵图鉴数据采集，并通过 `data/urls.csv` 和 `data/images/*` 管线下载精灵大图、属性图标、技能图标、特性图标和克制表图标。已有 `data/images/sprites` 是精灵详情页中的大图，不适合混放上传阵容页使用的精灵头像。

BWIKI 上传阵容页包含一个独立的精灵头像选择列表。头像列表位于页面中的 `div.rocom_spirit_popup_overlay_list`，每个头像在 `div.rocom_canlearn_img_box img` 下，图片 URL 来自 `patchwiki.biligame.com`，精灵名称可从 `alt` 或 `title` 中的 `link=精灵名}}` 提取。

## 目标

- 在当前 `rocom_scraper.py` 图片管线中新增精灵头像下载能力。
- 实际运行时访问线上上传阵容页 `https://wiki.biligame.com/rocom/%E4%B8%8A%E4%BC%A0%E9%98%B5%E5%AE%B9`，不依赖本地样例 HTML。
- 解析页面中的全部精灵头像。
- 将头像下载到独立目录 `data/images/avatars`。
- 文件名使用精灵名称，例如 `迪莫.png`、`鸭吉吉（蓬松的样子）.png`。
- 已存在的头像文件默认跳过，不重复下载。
- 头像 URL 写入现有 `data/urls.csv`，类型为 `avatar`，复用已有 URL 记录和本地路径格式。
- 保留现有精灵图鉴爬取行为，并提供只同步头像的命令行入口。

## 非目标

- 不把头像写入 `data/sprites.json` 或 `data/sprites.csv` 的每条精灵记录。
- 不把头像和图鉴精灵编号做强绑定。
- 不替换 `data/images/sprites` 中已有精灵大图。
- 不依赖 `data/阵容上传.html` 作为生产数据源；该文件只用于测试解析器。
- 不做图片内容裁剪、压缩或格式转换。

## 输出

头像文件输出到：

```text
data/images/avatars/<精灵名称>.<扩展名>
```

扩展名从图片 URL 末段解析，通常为 `png`。精灵名经过现有 `_add_url()` 文件名清洗逻辑处理，替换 Windows 不允许的字符：

```text
\ / : * ? " < > |
```

`data/urls.csv` 新增或保留如下记录格式：

```csv
name,type,url,local_path
迪莫,avatar,https://patchwiki.biligame.com/images/rocom/d/de/n2a74bd4dvdud8b4t4819y9md4t811z.png,images/avatars/迪莫.png
```

## 架构

实现仍放在 `rocom_scraper.py`，但按页面来源拆分职责：

- 图鉴页流程：继续使用 `LIST_URL`、`parse_list_page()`、`parse_sprite_detail()`。
- 上传阵容页头像流程：新增 `AVATAR_LIST_URL`、头像 HTML 解析函数和头像同步函数。
- 图片下载：继续通过 `_add_url(name, img_type, url, data_dir, force)` 统一处理。

新增图片类型：

```python
IMAGE_DIRS = {
    "sprite": "images/sprites",
    "attribute": "images/attributes",
    "skill": "images/skills",
    "ability": "images/abilities",
    "matchup": "images/matchup",
    "avatar": "images/avatars",
}
```

## 解析设计

新增 `extract_avatar_name(raw: str) -> str`：

- 输入来自 `img["alt"]` 或 `img["title"]`。
- 支持格式 `link=迪莫}}`。
- 去掉开头 `link=`。
- 去掉末尾 `}}`。
- 去掉首尾空白。
- 如果不匹配 `link=...}}`，返回清理后的原始文本作为兜底。

新增 `parse_avatar_list_html(html: str) -> list[dict]`：

- 使用 BeautifulSoup 解析 HTML。
- 选择器范围限定在 `div.rocom_spirit_popup_overlay_list`，避免误收页面其它图片。
- 遍历每个 `div.rocom_canlearn_img_box` 下的第一张 `img`。
- 名称优先取 `alt`，缺失时取 `title`。
- URL 优先取 `src`。
- 主属性取父级 `data-main`。
- 副属性取父级 `data-2`。
- 宽高取 `data-file-width`、`data-file-height`，无法转换为整数时保留为空。
- 去重键为 `(name, url)`，避免同名不同 URL 或不同形态被错误覆盖。

返回结构：

```python
{
    "name": "迪莫",
    "url": "https://patchwiki.biligame.com/images/rocom/d/de/n2a74bd4dvdud8b4t4819y9md4t811z.png",
    "primary_type": "光",
    "secondary_type": "",
    "width": 256,
    "height": 256,
}
```

新增 `parse_avatar_list_page(url: str = AVATAR_LIST_URL) -> list[dict]`：

- 使用现有 `fetch_text()` 或等价请求函数访问线上页面。
- 将响应文本传给 `parse_avatar_list_html()`。
- 如果页面无法访问，抛出和现有图鉴爬取一致的运行时错误。

## 下载流程

新增 `download_avatar_images(data_dir: Path, force: bool = False) -> dict`：

1. 访问线上上传阵容页。
2. 解析头像列表。
3. 对每个头像调用 `_add_url(avatar["name"], "avatar", avatar["url"], data_dir, force)`。
4. 统计总数、成功记录数、跳过数、失败数。
5. 打印简短进度和结果。

跳过语义：

- 如果 `force=False` 且 URL 已在 `_urls_cache` 中，沿用 `_add_url()` 当前行为，直接返回已记录的 `local_path`。
- 如果 URL 未记录但目标文件已经存在，`_add_url()` 不发起下载，仍写入 `urls.csv`。
- 如果下载失败，`_add_url()` 返回空 `local_path`，头像流程将该项计为失败。

## 命令行

`python rocom_scraper.py`：

- 默认保持完整数据采集体验：抓图鉴数据，并在同一次运行末尾同步头像。

`python rocom_scraper.py --skip-avatars`：

- 只运行现有图鉴流程，不同步头像。

`python rocom_scraper.py --avatars-only`：

- 只访问上传阵容页并同步头像，不抓图鉴详情，不重写 `sprites.json`、`sprites.csv`、`skills.csv`。

`python rocom_scraper.py --force`：

- 继续表示强制重建当前运行范围内的数据和图片记录。
- 当默认完整运行时，清空并重建 `data/urls.csv` 后会重新写入图鉴图片和头像图片记录。
- 当 `--avatars-only --force` 时，只强制头像下载和头像 URL 记录，不删除图鉴输出文件。

## 错误处理

- 上传阵容页无法访问时：
  - 默认完整运行中，图鉴数据已经完成的情况下不回滚；打印头像同步失败信息。
  - `--avatars-only` 中返回失败退出码或结束运行，不改写图鉴输出。
- 单张头像下载失败时：
  - 继续处理其它头像。
  - 在输出统计中计入失败。
  - 失败 URL 可复用现有 `failed_urls.txt`，逐行写入头像 URL。
- 解析不到头像列表时：
  - 视为失败，提示上传阵容页结构可能变化。

## 测试

新增或扩展 `tests/test_rocom_scraper.py`：

- `test_extract_avatar_name_from_link_alt`
  - 输入 `link=迪莫}}`，输出 `迪莫`。
- `test_extract_avatar_name_falls_back_to_raw_text`
  - 输入 `迪莫`，输出 `迪莫`。
- `test_parse_avatar_list_html_extracts_names_and_urls`
  - 读取 `data/阵容上传.html`。
  - 断言包含 `迪莫`、`魔力猫`。
  - 断言 URL 来自 `patchwiki.biligame.com`。
  - 断言 `primary_type` 能读到 `光`、`草`。
- `test_download_avatar_images_uses_avatar_image_type`
  - monkeypatch `parse_avatar_list_page()` 返回两条头像。
  - monkeypatch `_add_url()` 捕获调用。
  - 断言调用中的 `img_type` 为 `avatar`，`data_dir` 正确。
- `test_avatars_only_does_not_save_sprite_outputs`
  - monkeypatch 头像流程。
  - 运行头像入口函数。
  - 断言不会调用 `_save()`、`_save_csv()`、`_save_skills_csv()`。

## 验收标准

- `python rocom_scraper.py --avatars-only` 会访问线上上传阵容页并下载头像到 `data/images/avatars`。
- 已存在的头像文件不会重复下载。
- `data/urls.csv` 中出现 `type=avatar` 的记录，`local_path` 指向 `images/avatars/...`。
- `data/images/sprites` 保持作为精灵大图目录，不混入头像。
- 默认 `python rocom_scraper.py` 在原有图鉴采集完成后同步头像。
- 单元测试覆盖头像名称解析、HTML 解析和下载管线调用。
