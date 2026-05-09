# BWIKI 玩家阵容爬虫设计

## 背景

当前 rocom-data 已有精灵图鉴爬虫，输出 data/sprites.json、data/sprites.csv、data/skills.csv、data/urls.csv 和本地图片。现有 data/teams.json 是模拟器使用的本地预设/自定义队伍名册，结构较轻，不适合直接承载 BWIKI 玩家分享阵容的作者、来源、上传日期、血脉魔法、性格、个体值和解析状态等归档信息。

本设计新增独立的 BWIKI 玩家阵容数据集，优先做完整文本归档，不自动混入现有 data/teams.json。

## 目标

- 访问 BWIKI 阵容一览页，解析 PVP/PVE 两个阵容列表区块。
- 对未爬取或列表页最后更新日期变化的阵容，访问详情 API 并解析 wikitext 模板。
- 详情请求之间固定间隔 2 秒，显示进度。
- 输出 data/lineups.json 和 data/lineups.csv。
- 不保存血脉魔法、精灵头像等图片 URL，也不下载阵容相关图片。
- 保留解析状态和 warning，允许单条阵容字段不完整时继续保存其它阵容。

## 非目标

- 不把玩家分享阵容自动写入 data/teams.json。
- 不生成模拟器可直接选择的队伍导入文件。
- 不保存或下载图片资源。
- 不对 BWIKI 阵容内容做游戏合法性校验。
- 不把阵容精灵名与 sprites.json 的 no/form 做强绑定。

## 输出 JSON 结构

主文件为 data/lineups.json，结构为数组。每条阵容记录如下：

```json
{
  "id": "0c4a56e20142767d1be32461465fdb0e",
  "title": "暂定",
  "type": "pvp",
  "author": "mokuyo",
  "intro": "没",
  "blood_magic": "进化之力",
  "uploaded_at": "2026-5-5",
  "last_updated": "2026-5-5",
  "source": {
    "page_title": "精灵阵容/0c4a56e20142767d1be32461465fdb0e",
    "list_section": "pvp"
  },
  "members": [
    {
      "slot": 1,
      "pokemon": "彩蝶鲨",
      "bloodline": "首领",
      "nature": "胆小",
      "talents": ["生命", "魔攻", "速度"],
      "skills": ["翼击", "贮藏", "寒风吹", "天洪"]
    }
  ],
  "parse_status": {
    "ok": true,
    "warnings": []
  }
}
```

字段说明：

- `id`：阵容编号，来自详情模板的 `阵容编号` 或列表页链接末段。
- `title`：阵容标题。
- `type`：阵容类型，优先来自详情模板的 `阵容类型`，缺失时使用列表分区。
- `author`：阵容作者。
- `intro`：阵容介绍原文。
- `blood_magic`：血脉魔法文本名，只保存文本，不保存图片 URL。
- `uploaded_at`：详情模板中的上传日期。
- `last_updated`：列表页中的最后更新日期，用于增量判断。
- `source.page_title`：MediaWiki 页面标题，用于重新构建 API 请求。
- `source.list_section`：阵容在列表页中的分区，值为 `pvp` 或 `pve`。
- `members`：按槽位排序的精灵配置。
- `parse_status`：单条解析结果。字段缺失但仍能保存时写 warning；无法解析详情模板时 `ok=false`。

## 输出 CSV 结构

主文件为 data/lineups.csv，使用 `utf-8-sig` 编码，数组字段用稳定分隔符拼接。建议列为：

```text
id,title,type,author,blood_magic,uploaded_at,last_updated,intro,
pokemon_1,bloodline_1,nature_1,talents_1,skills_1,
pokemon_2,bloodline_2,nature_2,talents_2,skills_2,
pokemon_3,bloodline_3,nature_3,talents_3,skills_3,
pokemon_4,bloodline_4,nature_4,talents_4,skills_4,
pokemon_5,bloodline_5,nature_5,talents_5,skills_5,
pokemon_6,bloodline_6,nature_6,talents_6,skills_6,
parse_ok,warnings
```

`talents_N` 使用英文逗号拼接，`skills_N` 使用分号拼接，`warnings` 使用分号拼接。

## 脚本与组件

新增独立脚本 lineup_scraper.py，不继续扩大 rocom_scraper.py。

### `parse_lineup_list_page()`

职责：访问阵容一览页并解析列表摘要。

输入：阵容一览 URL，默认线上页面。

输出：列表项数组。每个列表项包含：

- `id`
- `page_title`
- `list_section`
- `title`
- `last_updated`
- `list_members`

解析规则：

- PVP 区块来自 class `rocom_lineup_list_box_pvp_content`。
- PVE 区块来自 class `rocom_lineup_list_box_pve_content`。
- 每条阵容来自 class `rocom_lineup_line_pet_list_box`。
- 阵容标题来自 `rocom_lineup_line_pet_edit`。
- 更新日期来自 `rocom_lineup_list_date` 中的 `最后更新日期:` 后文本。
- 页面标题从链接 title 或 href 解码得到。
- 精灵名从带槽位编号的 `rocom_lineup_line_pet_item` 中读取；血脉魔法只由详情页字段决定。
- 不读取、不保存图片 URL。

### `fetch_lineup_wikitext(entry)`

职责：通过 MediaWiki API 读取单个阵容详情 wikitext。

请求使用 `action=query&format=json&prop=revisions&rvprop=content&formatversion=2`，`titles` 由 `page_title` 构建。

详情请求节流：每个详情请求结束后等待 2 秒。

### `parse_lineup_template(wikitext)`

职责：解析 `{{精灵阵容 ... }}` 模板为结构化字段。

规则：

- 逐行解析 `|key=value`。
- 读取 `阵容标题`、`阵容血脉魔法`、`阵容介绍`、`阵容作者`、`阵容类型`、`阵容上传日期`、`阵容编号`。
- 对 1 到 6 号槽位读取：
  - `阵容精灵N`
  - `阵容精灵N血脉`
  - `阵容精灵N性格`
  - `阵容精灵N个体值`
  - `阵容精灵N技能1` 到 `阵容精灵N技能4`
- `阵容精灵N个体值` 按英文逗号拆成数组，去除空白。
- 技能按 1 到 4 顺序保存，缺失时跳过并生成 warning。
- 缺少精灵名的槽位不输出 member，并生成 warning。

### `merge_existing_lineups(entries, existing)`

职责：执行增量判断并合并新旧结果。

规则：

- 主键为 `id`。
- 本地不存在：抓取详情。
- 本地存在且列表页 `last_updated` 与本地不同：抓取详情并覆盖。
- 本地存在且 `last_updated` 相同：跳过并保留旧记录。
- `--force`：所有列表项都抓取详情并覆盖。
- 单条详情抓取失败时，如果已有旧记录则保留旧记录；否则记录失败并不写入不完整详情。

日期比较只比较字符串是否相同，不做复杂日期解析。

### 保存函数

- `_save_json(data, path)`：写入前备份已有 JSON 为 `.backup.json`。
- `_save_csv(data, path)`：写入前备份已有 CSV 为 `.backup.csv`。
- 失败详情 URL 或 page title 写入 `data/failed_lineups.txt`。

## CLI

建议参数：

```powershell
python lineup_scraper.py
python lineup_scraper.py --force
python lineup_scraper.py --limit 5
python lineup_scraper.py --delay 2
python lineup_scraper.py --output data/lineups.json
```

参数语义：

- `--output`：JSON 输出路径，默认 `data/lineups.json`；CSV 输出为同名 `.csv`。
- `--force`：忽略本地缓存，全部重抓。
- `--limit`：调试用，只处理列表页前 N 条。
- `--delay`：详情请求间隔，默认 2 秒；不建议低于 2 秒。

## 进度展示

- 列表页解析完成后打印总阵容数、待抓取数、跳过数。
- 详情抓取时显示 `[current/total]` 进度条，标签包含阵容类型、标题或 id。
- 完成后打印成功、跳过、失败、JSON/CSV 路径。

## 错误处理

- 列表页失败：终止，不覆盖旧数据。
- 单个详情失败：记录失败，继续后续条目。
- API 返回缺页或无 revision：视为单条失败。
- wikitext 无法解析模板：保留基础列表信息，`parse_status.ok=false`，warning 写明原因。
- 成员字段不完整：不失败，写入 warning。
- 输出写入前先完成内存合并，避免中途失败破坏旧文件。

## 测试计划

新增 tests/test_lineup_scraper.py。

测试覆盖：

1. 列表页解析
   - 使用本地 data/阵容一览.html。
   - 验证能解析 PVP/PVE 分区。
   - 验证能提取 `id`、`page_title`、`last_updated`、`list_members`。
   - 验证结果中没有图片 URL 字段。

2. 详情模板解析
   - 使用样例 wikitext。
   - 验证阵容元数据正确。
   - 验证 6 个成员正确。
   - 验证个体值拆成数组。
   - 验证 4 个技能按顺序保留。

3. 增量判断
   - 已存在且 `last_updated` 相同会跳过。
   - 已存在但 `last_updated` 不同会重抓。
   - `--force` 会重抓全部。

4. CSV 输出
   - 验证固定列存在。
   - 验证数组字段拼接稳定。
   - 验证 warning 字段可读。

## 后续可扩展方向

- 额外生成模拟器导入文件，但不在本次实现范围内。
- 使用 sprites.json 校验精灵名和技能名，并将异常写入 warnings。
- 给 Flutter 或 viewer 增加阵容浏览页面。
