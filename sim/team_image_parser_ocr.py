"""
本地 OCR 队伍图片解析器（无需 API Key）

支持两种 OCR 引擎（自动检测已安装的）：
  - rapidocr-onnxruntime  轻量首选（~50MB 模型，首次运行自动下载）
      pip install rapidocr-onnxruntime
  - easyocr               精度更高，但依赖 PyTorch（~1.5GB）
      pip install easyocr

注意：OCR 识别中文游戏字体存在一定错误率，建议导入后人工核对。
"""

import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


# ============================================================
# OCR 引擎抽象层
# ============================================================
def _check_engines() -> dict:
    """返回已安装的 OCR 引擎状态"""
    status = {}
    for name, pkg in [("rapid", "rapidocr_onnxruntime"), ("easy", "easyocr")]:
        try:
            __import__(pkg)
            status[name] = True
        except ImportError:
            status[name] = False
    return status


def get_available_engines() -> list[str]:
    """返回已安装的引擎名称列表"""
    s = _check_engines()
    return [name for name, ok in s.items() if ok]


def _run_rapid(image_path: str) -> list:
    """
    rapidocr-onnxruntime 识别，返回 [(text, x_center, y_center, w, h, score), ...]
    """
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()
    result, _ = engine(image_path)
    if not result:
        return []

    items = []
    for row in result:
        box, text, score = row[0], row[1], row[2]
        # box: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        w  = max(xs) - min(xs)
        h  = max(ys) - min(ys)
        items.append((text.strip(), cx, cy, w, h, float(score or 0)))
    return items


def _run_easy(image_path: str) -> list:
    """
    easyocr 识别，返回 [(text, x_center, y_center, w, h, score), ...]
    """
    import easyocr
    reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
    result = reader.readtext(image_path)
    if not result:
        return []

    items = []
    for (box, text, score) in result:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        w  = max(xs) - min(xs)
        h  = max(ys) - min(ys)
        items.append((text.strip(), cx, cy, w, h, float(score)))
    return items


def run_ocr(image_path: str, engine: str = "auto") -> list:
    """
    运行 OCR，返回 [(text, x_center, y_center, w, h, confidence), ...]

    Parameters
    ----------
    image_path : 图片路径
    engine     : "auto" | "rapid" | "easy"
                 auto = 优先 rapid，其次 easy
    """
    available = get_available_engines()
    if not available:
        raise ImportError(
            "未找到可用的 OCR 库。请选择以下之一安装：\n"
            "  轻量（推荐）: pip install rapidocr-onnxruntime\n"
            "  高精度:       pip install easyocr"
        )

    if engine == "auto":
        engine = available[0]          # 优先 rapid（列表顺序）

    if engine == "rapid":
        if "rapid" not in available:
            raise ImportError("rapidocr-onnxruntime 未安装：pip install rapidocr-onnxruntime")
        return _run_rapid(image_path)
    elif engine == "easy":
        if "easy" not in available:
            raise ImportError("easyocr 未安装：pip install easyocr")
        return _run_easy(image_path)
    else:
        raise ValueError(f"未知引擎：{engine}")


# ============================================================
# 文本模糊匹配
# ============================================================
def _similarity(a: str, b: str) -> float:
    """综合相似度：字符覆盖 + SequenceMatcher"""
    if not a or not b:
        return 0.0
    # 字符级覆盖率
    common = sum(1 for c in a if c in b)
    coverage = common / max(len(a), len(b))
    # 序列相似度
    seq = SequenceMatcher(None, a, b).ratio()
    return max(coverage, seq)


def _best_match(text: str, candidates: list[str], threshold: float = 0.55) -> Optional[str]:
    """在候选列表里找与 text 最相似的，低于阈值返回 None"""
    best_name, best_score = None, 0.0
    for name in candidates:
        # 精确 / 包含
        if text == name:
            return name
        if text in name or name in text:
            score = len(min(text, name, key=len)) / len(max(text, name, key=len))
            if score > best_score:
                best_name, best_score = name, score + 0.1  # 包含优先
            continue
        s = _similarity(text, name)
        if s > best_score:
            best_name, best_score = name, s

    return best_name if best_score >= threshold else None


# ============================================================
# 空间布局分析
# ============================================================
def _grid_region(idx: int, img_w: float, img_h: float) -> tuple:
    """
    把图片分为 2 列 × 3 行，第 idx 个格子（0-5，行优先）的区域。
    右侧约 15% 是队伍名横幅，不计入格子。
    返回 (x_min, x_max, y_min, y_max)。
    """
    card_area_w = img_w * 0.85   # 左侧 85% 是精灵卡区域
    col = idx % 2
    row = idx // 2
    x_min = col * (card_area_w / 2)
    x_max = (col + 1) * (card_area_w / 2)
    y_min = row * (img_h / 3)
    y_max = (row + 1) * (img_h / 3)
    return x_min, x_max, y_min, y_max


def _in_region(cx: float, cy: float, region: tuple, margin: float = 0.05,
               img_w: float = 1, img_h: float = 1) -> bool:
    x_min, x_max, y_min, y_max = region
    mx, my = img_w * margin, img_h * margin
    return (x_min - mx) <= cx <= (x_max + mx) and (y_min - my) <= cy <= (y_max + my)


def _get_image_size(image_path: str) -> tuple[int, int]:
    """返回图片 (width, height)"""
    from PIL import Image
    with Image.open(image_path) as img:
        return img.size   # (width, height)


# ============================================================
# 主解析函数
# ============================================================
def parse_team_image_ocr(image_path: str, engine: str = "auto") -> dict:
    """
    用本地 OCR 解析队伍配置图片，返回与 parse_team_image() 相同格式的 dict。

    Parameters
    ----------
    image_path : 图片路径
    engine     : "auto" | "rapid" | "easy"

    Returns
    -------
    {"team_name": str, "members": [{"pokemon": str, "skills": [...]}, ...]}
    """
    from sim.pokemon_db import get_all_pokemon_names, load_pokemon_db
    from sim.skill_db import get_all_skills, load_skills

    load_pokemon_db()
    load_skills()

    all_pokemon = get_all_pokemon_names()
    all_skills  = list(get_all_skills().keys())

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")

    # ---- 1. 获取图片尺寸 ----
    img_w, img_h = _get_image_size(image_path)

    # ---- 2. 运行 OCR ----
    ocr_items = run_ocr(image_path, engine=engine)
    # ocr_items: [(text, cx, cy, w, h, score), ...]

    # ---- 3. 匹配精灵名和技能名 ----
    pokemon_hits = []   # (matched_name, cx, cy, score)
    skill_hits   = []   # (matched_name, cx, cy, score)

    for text, cx, cy, w, h, conf in ocr_items:
        if conf < 0.3:
            continue
        cleaned = text.strip().replace(" ", "")

        # 尝试匹配精灵名
        pm = _best_match(cleaned, all_pokemon, threshold=0.65)
        if pm:
            pokemon_hits.append((pm, cx, cy, conf))

        # 尝试匹配技能名
        sm = _best_match(cleaned, all_skills, threshold=0.60)
        if sm:
            skill_hits.append((sm, cx, cy, conf))

    # ---- 4. 对精灵名去重：同名保留置信度最高的 ----
    best_pokemon: dict[str, tuple] = {}
    for name, cx, cy, conf in pokemon_hits:
        if name not in best_pokemon or conf > best_pokemon[name][2]:
            best_pokemon[name] = (cx, cy, conf)
    # 转成列表，按 (row, col) 排序（先 y 后 x）
    sorted_pokemon = sorted(
        [(name, cx, cy) for name, (cx, cy, _) in best_pokemon.items()],
        key=lambda t: (t[2], t[1])  # sort by (cy, cx)
    )

    # ---- 5. 按 2x3 网格分配精灵到格子 ----
    # 每个格子最多 1 只精灵（保留位置最中心的）
    slot_pokemon: dict[int, tuple] = {}  # slot_idx -> (name, cx, cy)
    for name, cx, cy in sorted_pokemon:
        for slot_idx in range(6):
            region = _grid_region(slot_idx, img_w, img_h)
            if _in_region(cx, cy, region, margin=0.03, img_w=img_w, img_h=img_h):
                if slot_idx not in slot_pokemon:
                    slot_pokemon[slot_idx] = (name, cx, cy)
                break
    # 没分配到格子的精灵，按顺序补到空格子里
    unslotted = [(n, cx, cy) for n, cx, cy in sorted_pokemon
                 if n not in {v[0] for v in slot_pokemon.values()}]
    for n, cx, cy in unslotted:
        for slot_idx in range(6):
            if slot_idx not in slot_pokemon:
                slot_pokemon[slot_idx] = (n, cx, cy)
                break

    # ---- 6. 按格子分配技能名 ----
    slot_skills: dict[int, list] = {i: [] for i in range(6)}
    skill_used: set[str] = set()

    for skill_name, scx, scy, sconf in skill_hits:
        for slot_idx in range(6):
            region = _grid_region(slot_idx, img_w, img_h)
            # 技能在格子的下半部分
            x_min, x_max, y_min, y_max = region
            skill_zone_y = y_min + (y_max - y_min) * 0.5  # 下半区
            if (x_min <= scx <= x_max and
                    skill_zone_y <= scy <= y_max + img_h * 0.02 and
                    skill_name not in skill_used):
                slot_skills[slot_idx].append((skill_name, scx, sconf))
                break

    # 每个格子：按 x 坐标排序取前 4 个（从左到右 = 4 个技能槽）
    for slot_idx in range(6):
        sorted_s = sorted(slot_skills[slot_idx], key=lambda t: t[1])  # 按 x 排序
        # 去重同名技能
        seen, deduped = set(), []
        for name, scx, sconf in sorted_s:
            if name not in seen:
                seen.add(name)
                deduped.append(name)
        slot_skills[slot_idx] = deduped[:4]

    # ---- 7. 提取队伍名（右侧横幅区域） ----
    team_name = "导入队伍"
    banner_x_start = img_w * 0.85
    team_name_candidates = []
    for text, cx, cy, w, h, conf in ocr_items:
        if cx >= banner_x_start and cy > img_h * 0.5:
            team_name_candidates.append((text.strip(), cy))
    if team_name_candidates:
        # 取 y 最大（最靠下）的非空文本
        team_name_candidates.sort(key=lambda t: -t[1])
        for txt, _ in team_name_candidates:
            if txt and re.search(r'队|team|Team', txt, re.IGNORECASE):
                team_name = txt
                break
        if team_name == "导入队伍" and team_name_candidates:
            team_name = team_name_candidates[0][0] or "导入队伍"

    # ---- 8. 组装结果 ----
    members = []
    for slot_idx in range(6):
        pname = slot_pokemon.get(slot_idx, ("", 0, 0))[0]
        skills = slot_skills.get(slot_idx, [])
        # 补足到 4 个空槽
        while len(skills) < 4:
            skills.append("")
        members.append({"pokemon": pname, "skills": skills[:4]})

    return {"team_name": team_name, "members": members}
