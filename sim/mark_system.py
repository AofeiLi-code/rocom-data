"""
印记系统 (Mark System)

规则：
  - 印记挂在整个队伍上，换人不消失
  - 每队同时最多存在 1 种正面印记 + 1 种负面印记
  - 同类别的新印记会直接顶替旧印记（叠层叠到同一印记上，异种则覆盖）
  - 只有清除类技能或被顶替才会消失

正面印记（POSITIVE）：
  湿润印记  — 全技能能耗 -1（每层）
  龙噬印记  — 使用 3 能耗技能时，自身双攻 +30%（每层）
  蓄势印记  — 全攻击技能威力 +30%×层数，但能耗 +1×层数
  风起印记  — 先手时本次技能威力 +20%（每层）
  蓄电印记  — 攻击技能威力平坦 +10×层数
  光合印记  — 回合结束获得 1 能量（每层）
  攻击印记  — 全技能威力 +10%×层数

负面印记（NEGATIVE）：
  减速印记  — 速度 -10×层数
  降灵印记  — 入场时失去 1 能量（每层）
  星陨印记  — 受到非幻系攻击时，消耗全部层数造成额外幻系伤害
  中毒印记  — 回合结束扣 3%×层数 HP
  棘刺印记  — 入场时失去 6%×层数 HP
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class MarkCategory(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class MarkType(Enum):
    # ---- 正面印记 ----
    WET      = "湿润印记"   # 能耗 -1/层
    DRAGON   = "龙噬印记"   # 3费技能 → 双攻+30%/层
    CHARGE   = "蓄势印记"   # 攻击威力+30%/层，能耗+1/层
    WIND     = "风起印记"   # 先手时威力+20%/层
    ELECTRIC = "蓄电印记"   # 攻击技能平坦+10威力/层
    PHOTO    = "光合印记"   # 回合结束+1能量/层
    ATTACK   = "攻击印记"   # 全技能威力+10%/层
    # ---- 负面印记 ----
    SLOW     = "减速印记"   # 速度-10/层
    SPIRIT   = "降灵印记"   # 入场-1能量/层
    METEOR   = "星陨印记"   # 受非幻系攻击触发，消耗全层数造额外幻系伤害
    POISON   = "中毒印记"   # 回合结束-3%HP/层
    THORN    = "棘刺印记"   # 入场-6%HP/层


# 印记所属类别映射
MARK_CATEGORY: Dict[MarkType, MarkCategory] = {
    MarkType.WET:      MarkCategory.POSITIVE,
    MarkType.DRAGON:   MarkCategory.POSITIVE,
    MarkType.CHARGE:   MarkCategory.POSITIVE,
    MarkType.WIND:     MarkCategory.POSITIVE,
    MarkType.ELECTRIC: MarkCategory.POSITIVE,
    MarkType.PHOTO:    MarkCategory.POSITIVE,
    MarkType.ATTACK:   MarkCategory.POSITIVE,
    MarkType.SLOW:     MarkCategory.NEGATIVE,
    MarkType.SPIRIT:   MarkCategory.NEGATIVE,
    MarkType.METEOR:   MarkCategory.NEGATIVE,
    MarkType.POISON:   MarkCategory.NEGATIVE,
    MarkType.THORN:    MarkCategory.NEGATIVE,
}


@dataclass
class TeamMark:
    """
    队伍印记。

    Attributes
    ----------
    mark_type : 印记种类
    stacks    : 当前层数（正整数）
    """
    mark_type: MarkType
    stacks:    int = 1

    @property
    def category(self) -> MarkCategory:
        return MARK_CATEGORY[self.mark_type]

    def copy(self) -> "TeamMark":
        return TeamMark(mark_type=self.mark_type, stacks=self.stacks)
