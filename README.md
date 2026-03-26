# rocom-data

从洛克王国世界 BWIKI 爬取完整精灵图鉴数据，包含种族值、技能、特性、属性克制关系，并附带一个可在终端直接浏览的图鉴查看器。

## 功能

| 功能 | 说明 |
|------|------|
| 🕷️ 全量爬取 | 抓取 BWIKI 上全部精灵数据，保存为 JSON 和 CSV |
| 🔄 检查更新 | 对比本地与 wiki 的差异，仅增量爬取新增精灵 |
| 📖 图鉴查看器 | 在终端按页浏览每只精灵的完整信息，支持搜索 |

## 数据来源

数据来自 [BWIKI 洛克王国世界](https://wiki.biligame.com/rocom/)，仅供个人学习使用，请勿用于商业目的。

---

## 环境要求

- Python 3.10+
- 依赖库：`requests`、`beautifulsoup4`、`rich`

```bash
pip install -r requirements.txt
```

---

## 使用方法

### 方式一：双击 run.bat（推荐）

Windows 用户直接双击 `run.bat`，会出现菜单：

```
================================
  Rocom Sprite Data Tool
================================
  1. Full scrape (all sprites)   ← 全量爬取
  2. Check for updates           ← 检查更新
  3. Browse sprites (viewer)     ← 打开图鉴查看器
  4. Exit
================================
```

### 方式二：命令行

```bash
# 全量爬取所有精灵
python rocom_scraper.py

# 检查并增量更新
python rocom_scraper.py --check-update

# 打开图鉴查看器
python viewer.py
```

### 爬虫可选参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--limit N` | 只爬前 N 只精灵（调试用） | 0（全部） |
| `--delay N` | 每次请求间隔秒数，过低可能被限速 | 0.8 |
| `--output path` | 输出 JSON 的路径 | `data/sprites.json` |
| `--check-update` | 检查更新模式，不重新全量爬取 | — |

---

## 图鉴查看器

运行 `python viewer.py` 后，终端会显示类似手机图鉴的界面：

```
╭─────────────── 洛克王国图鉴 ───────────────╮
│ NO.001  迪莫                               │
│ 属性   光                                  │
│                                            │
│ ──────────────── 种族值 ───────────────── │
│ 生命 ████████░░░░  120                     │
│ 物攻 █████░░░░░░░   80                     │
│ ...                                        │
│ 合计                582                    │
│                                            │
│ ──────────────── 克制关系 ──────────────── │
│ 克制    恶  幽                             │
│ 被克制  幽  草                             │
│ ...                                        │
│                                            │
│ ──────────────── 技能 ──────────────────── │
│ 猛烈撞击  普通  物攻  ★                    │
│   对敌方精灵造成物理伤害。                 │
│ ...                                        │
╰────────────────── 1 / 427 ─────────────────╯
```

**操作键：**

| 按键 | 功能 |
|------|------|
| `←` / `→` 或 `a` / `d` | 切换上一只 / 下一只精灵 |
| `/` | 搜索（输入名称或编号） |
| `q` | 退出查看器 |

---

## 输出文件

| 文件 | 说明 |
|------|------|
| `data/sprites.json` | 完整数据，嵌套 JSON，适合程序读取 |
| `data/sprites.csv` | 扁平化 CSV，可直接用 Excel 或 pandas 打开 |
| `data/sprites.backup.json` | 每次爬取前自动备份的上一版数据 |

### JSON 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `no` | int | 精灵编号 |
| `name` | str | 精灵名称 |
| `form` | str / null | 形态名（如"蓬松的样子"），无则为 null |
| `url` | str | BWIKI 原始页面链接 |
| `has_shiny` | bool | 是否有异色图 |
| `attributes` | list[str] | 属性（最多两个，如 `["火", "水"]`） |
| `stats` | dict | 种族值，含 `hp / atk / sp_atk / def / sp_def / spd / total` |
| `ability` | dict | 特性，含 `name / description` |
| `type_matchup` | dict | 克制关系，含 `strong_against / weak_to / resists / resisted_by` |
| `skills` | list[dict] | 技能列表，见下表 |

### skills 子字段

| 字段 | 说明 |
|------|------|
| `name` | 技能名 |
| `attribute` | 技能属性（火/水/草…） |
| `category` | 类别（物攻 / 魔攻 / 状态 / 防御） |
| `power` | 威力数值 |
| `cost` | 能量消耗（星数） |
| `description` | 技能效果描述 |

---

## 免责声明

- 本项目仅供学习爬虫与数据分析，请勿高频请求，以免对 BWIKI 服务器造成负担
- 数据版权归 BWIKI 及洛克王国世界原作者所有，禁止商业使用
- 使用本项目产生的一切后果由使用者自行承担

## 贡献

欢迎提 PR 修复解析问题或补充缺失字段，感谢！

## 致谢

本项目由 [AofeiLi-code](https://github.com/AofeiLi-code) 负责整体架构设计与需求规划，具体代码实现由 [Claude](https://claude.ai)（Anthropic）协助完成。
