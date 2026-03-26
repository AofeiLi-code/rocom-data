# rocom-data

从洛克王国世界 BWIKI 爬取精灵图鉴数据，输出为 JSON 与 CSV 格式，供个人学习与分析使用。

## 数据来源

数据来自 [https://wiki.biligame.com/rocom/](https://wiki.biligame.com/rocom/)，仅供个人学习使用，请勿用于商业目的。

## 环境要求

- Python 3.10+

## 安装与使用

**1. 安装依赖**

```bash
pip install -r requirements.txt
```

**2. 运行爬虫**

- Windows 双击 `run.bat` 即可启动
- 或在命令行运行：

```bash
python rocom_scraper.py --delay 1.5
```

- VS Code 用户可按 `Ctrl+Shift+B` 直接运行"爬取精灵数据"任务

**可选参数**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--limit N` | 只爬前 N 只精灵（调试用） | 0（全部） |
| `--delay N` | 每次请求间隔秒数 | 0.8 |
| `--output path` | JSON 输出路径 | `data/sprites.json` |

**3. 输出文件**

| 文件 | 说明 |
|------|------|
| `data/sprites.json` | 完整精灵数据，嵌套 JSON 格式 |
| `data/sprites.csv` | 同上，扁平 CSV 格式，便于 Excel / pandas 分析 |

## 输出字段说明

### JSON 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `no` | int | 精灵编号 |
| `name` | str | 精灵名称 |
| `form` | str \| null | 形态名（如"蓬松的样子"），无则为 null |
| `url` | str | BWIKI 原始页面链接 |
| `has_shiny` | bool | 是否有异色图 |
| `attributes` | list[str] | 属性列表（最多两个，如 `["火", "飞行"]`） |
| `stats.total` | int | 总种族值 |
| `stats.hp` | int | 生命种族值 |
| `stats.atk` | int | 物攻种族值 |
| `stats.sp_atk` | int | 魔攻种族值 |
| `stats.def` | int | 物防种族值 |
| `stats.sp_def` | int | 魔防种族值 |
| `stats.spd` | int | 速度种族值 |
| `ability.name` | str | 特性名称 |
| `ability.description` | str | 特性描述 |
| `type_matchup.strong_against` | list[str] | 克制的属性 |
| `type_matchup.weak_to` | list[str] | 被克制的属性 |
| `type_matchup.resists` | list[str] | 抵抗的属性 |
| `type_matchup.resisted_by` | list[str] | 被抵抗的属性 |
| `skills` | list[dict] | 技能列表，见下表 |

### skills 子字段

| 字段 | 说明 |
|------|------|
| `name` | 技能名 |
| `attribute` | 技能属性 |
| `category` | 技能类别（物攻/魔攻/状态/防御） |
| `power` | 威力 |
| `cost` | 能量消耗（星数） |
| `description` | 技能描述 |

### CSV 列说明

CSV 在 JSON 基础上做了扁平化处理：

| 列名 | 说明 |
|------|------|
| `no` ~ `spd` | 同 JSON 对应字段 |
| `attributes` | 属性列表，逗号拼接，如 `火,飞行` |
| `ability_name` | 特性名 |
| `ability_desc` | 特性描述 |
| `strong_against` / `weak_to` / `resists` / `resisted_by` | 克制关系，各字段逗号拼接 |
| `skills` | 技能列表，分号拼接，每条格式为 `技能名(属性/类别/威力/能量消耗/描述)` |

## 免责声明

- 本项目仅供学习爬虫与数据分析，请勿高频请求，以免对 BWIKI 服务器造成负担
- 数据版权归 BWIKI 及洛克王国世界原作者所有，禁止商业使用
- 使用本项目产生的一切后果由使用者自行承担

## 贡献

欢迎提 PR 修复解析问题或补充缺失字段，感谢！

## 致谢

本项目由创作者负责整体架构设计与需求规划，具体代码实现由 [Claude](https://claude.ai)（Anthropic）协助完成。
