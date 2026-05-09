"""
精灵特性系统 (Ability Engine)

实现五支预设队伍中全部 24 种精灵特性效果。

Hook 接入点（由 battle_engine.py 调用）：
  on_battle_start      — 设置初始出战精灵的入场回合
  on_turn_start        — 回合开始（预警 / 哨兵：预测敌方威胁，赋予临时速度）
  on_switch_in         — 换入时效果（下黑手 / 降灵印记 / 棘刺印记 / 慢热型加能量）
  on_switch_out        — 换出时效果（洁癖传递 buff/debuff）
  on_faint             — 倒下时效果（诈死 / 飓风 / 虚假宝箱 / 不朽）
  get_priority_bonus   — 迅捷特性（飓风 / 翼轴 / 暴食 / 野性感官）
  get_attack_mods      — 攻击修正（威力加成/倍率/印记加成/先手判断）
  get_defense_mods     — 防御修正（绝对秩序减伤）
  on_post_attack       — 攻击后效果（溶解扩散 / 渗透 / 助燃 / 灵魂灼伤 / 浸润 / 氧循环 / 龙噬印记 / 星陨印记 / 捉迷藏冻结标记）
  on_use_status_skill  — 状态技能使用后（泛音列）
  on_use_defense_skill — 使用防御技能时（身经百练计数 / 野性感官 / 慢热型计数）
  intercept_burn_decay — 燃薪虫：烧伤增长而非衰减
  get_extra_hit_count  — 嫁祸：HP 里程碑触发额外连击
  on_defender_damaged  — 嫁祸：HP 里程碑检测
  apply_mark_damage    — 印记回合伤害（中毒印记）
  on_turn_end          — 回合结束效果（蚀刻 / 特殊清洁场景 / 光合印记 / 吸积盘 / 不朽 / 印记伤害 / 泛音列倒计时 / 捉迷藏维护）
  on_turn_end_switches — 回合结束换人（星地善良 / 哨兵脱离）
  get_mark_energy_cost_mod — 印记能耗修正（湿润 / 蓄势 / 对流取反）
  get_mark_speed_penalty   — 印记速度惩罚（减速）
  on_freeze_applied    — 捉迷藏：标记冻结来源
  is_falling_star_active — 陨落：跳过回合结束伤害效果
  get_temp_speed_bonus — 预警/哨兵：临时速度加成

已实现特性（24个）：
  ── 毒队 ──────────────────────────────────────────────────────────────────
  溶解扩散  千棘盔     使用水系技能时，每携带 1 个毒系技能 → 敌方中毒 +1 层
  蚀刻      裘卡       回合结束：敌方每 2 层中毒转化为 1 层中毒印记
  扩散侵蚀  琉璃水母   水系技能命中后，敌方中毒 +(当前层数 × 2)
  下黑手    影狸       己方在场时，敌方换入精灵立刻获得 5 层中毒
  向心力    声波缇塔   前两个有伤技能威力 +30（平坦加成）
  壮胆      巨噬针鼹   队伍存在虫系精灵时，双攻 +50%

  ── 翼王队 ───────────────────────────────────────────────────────────────
  翼轴      帕帕斯卡   1 号位技能获得先手
  悲悯      恶魔狼     每有 1 只力竭队友，双攻 +30%
  渗透      棋绮后     使用武/地系技能后，永久攻防 +5%（累积）
  身经百练  海豹船长   己方每次应对，水/武技能威力 +20%/次（累积）
  洁癖      翠顶夫人   换出时将全部 buff/debuff 传递给换入精灵
  飓风      圣羽翼王   ①有翼系队友携带相同技能时该技能获先手；②被击败时己方额外 -1 魔力

  ── 其他预设队 ───────────────────────────────────────────────────────────
  煤渣草    燃薪虫     在场时，全场烧伤回合结束增长而非衰减
  变形活画  画间沉铁兽 对手每有 10% buff 时，己方威力 +10%（累积）
  目空      白金独角兽 非光系技能威力 +25%
  绝对秩序  秩序鱿墨   受到非自身属性攻击时，伤害 -50%
  暴食      翼龙       龙系技能获得先手
  虚假宝箱  迷迷箱怪   力竭时，场上敌方攻防 +20%
  专注力    音速犬     入场首回合，物攻技能威力 +100%
  魔法增效  黑猫巫师   魔攻技能威力 +70%
  诈死      卡瓦重     己方精灵倒下时，少扣 1 格生命（补回）
  嫁祸      朔夜伊芙   HP 穿越 75%/50%/25% 里程碑时，技能连击次数各 +2
  特殊清洁场景 食尘短绒 回合结束偷取敌方 1 层印记（优先正面）转移至己方
  星地善良  小皮球     回合结束时，若当前己方精灵能量归 0，自动换入

  ── BWIKI 玩家配队补充（Top 18 缺失中已实现）────────────────────────────
  冰钻      冰钻布鲁斯 敌方所有技能 base_cost 总和 ×10% → 攻击威力加成
  助燃      火神等     使用火系技能后，自身双攻 +20%（永久叠加）
  灵魂灼伤  九尾狐等   冰系技能命中 → 4 层灼烧；火系技能命中 → 2 层冻结
  氧循环    魔力猫等   使用草系技能后，回复 10% 最大 HP
  吸积盘    怖哭菇等   回合结束敌方获得 2 层星陨印记
  野性感官  针叶巡林等 应对成功后，下次自己攻击 priority +1（一次性）
  浸润      水蓝蓝等   使用水系技能后，全技能能耗 -1（永久叠加，可至 0）
  月牙雪糕  月牙雪熊   使用攻击技能时，星陨印记反击额外加上敌方冻结层数
  不朽      大头骨龙等 力竭后 3 回合复活（满血满能量，不补 lives，不强制上场）

  ── BWIKI C 组（需新 hook + 助手）──────────────────────────────────────
  对流      利灯鱼     自身印记能耗修正取反（+变-，-变+）
  石头大餐  阿米亚特   能量不足时，每缺 1 点消耗 5% maxHP 代替（HP 可到 0）
  慢热型    瞌睡王     初始能量 0；不在场时己方应对累计计数（cap 2），
                       入场时加 5×counter 能量并清零计数
  捉迷藏    大耳帽兜   己方造成的冻结期间，敌方全技能能耗 +1
  陨落      落陨星兔   在场时跳过双方回合结束的伤害类效果
                       （烧伤伤害/中毒伤害/印记伤害；不跳特性触发与冻毙）
  泛音列    号儿鱼     使用状态技能后，敌方 3 回合内全技能能耗 +3（再触发刷新）
  预警      黑猫巫师   回合开始时若敌方任一技能能击败自己，本回合速度 +50
  哨兵      优优       同预警，且行动后强制脱离（最后一只时不脱离）
"""

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from sim.types import Type, SkillCategory

if TYPE_CHECKING:
    from sim.battle_state import BattleState
    from sim.pokemon import Pokemon
    from sim.skill import Skill


# ============================================================
# 攻击修正上下文
# ============================================================

@dataclass
class AttackModContext:
    """
    _apply_attack_skill 调用 get_attack_mods 后的修正参数。

    power_mult       : 技能威力乘数（与 counter_power_mult 合并使用）
    power_flat_bonus : 威力平坦加成（加到 calculate_damage 的 extra_power_bonus）
    """
    power_mult:       float = 1.0
    power_flat_bonus: int   = 0


# ============================================================
# 辅助
# ============================================================

def _get_ability_name(pokemon: "Pokemon") -> str:
    """从 'name:description' 格式中提取特性名称，并去掉已知前缀"""
    ability = pokemon.ability or ""
    # 去掉爬虫带来的前缀（如 "技能图标 "）
    ability = ability.replace("技能图标 ", "").strip()
    if ":" in ability:
        return ability.split(":")[0].strip()
    return ability


# ============================================================
# AbilityHooks — 所有特性逻辑集中于此
# ============================================================

class AbilityHooks:
    """
    所有特性 Hook 的统一实现。
    由 BattleEngine 在各关键节点调用，不持有自身状态。
    """

    # ------------------------------------------------------------------
    # 战斗开始
    # ------------------------------------------------------------------

    def on_battle_start(self, state: "BattleState", engine) -> None:
        """回合1时为初始出战精灵设置入场回合（仅 entry_turn==-1 时设置）"""
        if state.turn == 1:
            for team in ("a", "b"):
                p = state.get_current(team)
                if p.entry_turn < 0:
                    p.entry_turn = 1

    # ------------------------------------------------------------------
    # 换入
    # ------------------------------------------------------------------

    def on_switch_in(self, state: "BattleState", engine, team: str, new_idx: int) -> None:
        """精灵换入时：记录入场回合 + 下黑手 + 印记入场效果"""
        from sim.mark_system import MarkType
        new_p = state.get_team(team)[new_idx]
        new_p.entry_turn = state.turn

        # 影狸 [下黑手]：己方在场时，敌方换入精灵立刻获得 5 层中毒
        enemy_team = "b" if team == "a" else "a"
        enemy_on_field = state.get_current(enemy_team)
        if _get_ability_name(enemy_on_field) == "下黑手" and not enemy_on_field.is_fainted:
            new_p.poison_stacks += 5
            engine._log(f"  [{enemy_on_field.name}的下黑手] {new_p.name} 换入获得 5 层中毒")

        # 降灵印记：入场时失去 1 能量/层
        neg_mark = state.get_negative_mark(team)
        if neg_mark and neg_mark.mark_type == MarkType.SPIRIT:
            new_p.lose_energy(neg_mark.stacks)
            engine._log(
                f"  [降灵印记×{neg_mark.stacks}] {new_p.name} 入场失去 {neg_mark.stacks} 能量"
            )

        # 棘刺印记：入场时失去 6%HP/层
        if neg_mark and neg_mark.mark_type == MarkType.THORN:
            dmg = int(new_p.hp * 0.06 * neg_mark.stacks)
            if dmg > 0:
                new_p.take_damage(dmg)
                engine._log(
                    f"  [棘刺印记×{neg_mark.stacks}] {new_p.name} 入场失去 {dmg} HP"
                )

        # 瞌睡王 [慢热型]：入场时获得 5×累计应对计数 的能量，并清零计数
        if _get_ability_name(new_p) == "慢热型":
            counter_key = f"slow_heat_{team}"
            cnt = state.ability_counters.get(counter_key, 0)
            if cnt > 0:
                gain = 5 * cnt
                new_p.gain_energy(gain)
                state.ability_counters[counter_key] = 0
                engine._log(
                    f"  [{new_p.name}的慢热型] 入场积累 {cnt} 次应对 → 能量 +{gain}"
                )

    # ------------------------------------------------------------------
    # 换出
    # ------------------------------------------------------------------

    def on_switch_out(
        self,
        state: "BattleState",
        engine,
        team: str,
        old_idx: int,
        new_idx: int,
    ) -> None:
        """精灵换出时：翠顶夫人[洁癖]将 buff/debuff 传给换入精灵"""
        old_p = state.get_team(team)[old_idx]
        new_p = state.get_team(team)[new_idx]

        if _get_ability_name(old_p) == "洁癖":
            # 传递所有攻防速度 buff/debuff
            new_p.atk_boost    += old_p.atk_boost
            new_p.def_boost    += old_p.def_boost
            new_p.spatk_boost  += old_p.spatk_boost
            new_p.spdef_boost  += old_p.spdef_boost
            new_p.speed_boost  += old_p.speed_boost
            new_p.atk_reduce   += old_p.atk_reduce
            new_p.def_reduce   += old_p.def_reduce
            new_p.spatk_reduce += old_p.spatk_reduce
            new_p.spdef_reduce += old_p.spdef_reduce
            new_p.speed_reduce += old_p.speed_reduce
            engine._log(
                f"  [{old_p.name}的洁癖] 增益/减益传递给 {new_p.name}"
            )

    # ------------------------------------------------------------------
    # 倒下
    # ------------------------------------------------------------------

    def on_faint(
        self,
        state: "BattleState",
        engine,
        team: str,
        fainted_p: "Pokemon",
    ) -> None:
        """精灵倒下时特性效果（在 lives 扣减之后调用）"""
        if fainted_p is None:
            return
        ability      = _get_ability_name(fainted_p)
        enemy_team   = "b" if team == "a" else "a"

        # 卡瓦重 [诈死]：己方少扣 1 格生命（已扣，此处补回）
        if ability == "诈死":
            if team == "a":
                state.lives_a = min(state.lives_a + 1, 4)
            else:
                state.lives_b = min(state.lives_b + 1, 4)
            engine._log(
                f"  [{fainted_p.name}的诈死] 力竭不扣魔力！"
                f"  A:{state.lives_a}  B:{state.lives_b}"
            )

        # 圣羽翼王 [飓风]：被击败时，己方额外损失 1 格生命（共 -2）
        elif ability == "飓风":
            if team == "a":
                state.lives_a = max(0, state.lives_a - 1)
            else:
                state.lives_b = max(0, state.lives_b - 1)
            engine._log(
                f"  [{fainted_p.name}的飓风] 己方额外损失 1 格魔力！"
                f"  A:{state.lives_a}  B:{state.lives_b}"
            )

        # 迷迷箱怪 [虚假宝箱]：力竭时，场上敌方攻防 +20%
        elif ability == "虚假宝箱":
            enemy = state.get_current(enemy_team)
            if not enemy.is_fainted:
                enemy.atk_boost   += 0.2
                enemy.def_boost   += 0.2
                engine._log(
                    f"  [{fainted_p.name}的虚假宝箱] {enemy.name} 攻防 +20%"
                )

        # 大头骨龙等 [不朽]：力竭后 3 回合复活（满血满能量；不补 lives，不强制上场）
        elif ability == "不朽":
            fainted_p.revive_timer = 3
            engine._log(
                f"  [{fainted_p.name}的不朽] 力竭进入复活倒计时（3 回合后复活）"
            )

    # ------------------------------------------------------------------
    # 先手加成
    # ------------------------------------------------------------------

    def get_priority_bonus(
        self,
        state: "BattleState",
        team: str,
        skill_idx: int,
        skill: "Skill",
    ) -> float:
        """
        返回先手修正附加值（加到 skill.priority_mod * 0.1 之上）。
        999.0 确保绝对先手。
        """
        current = state.get_current(team)
        ability = _get_ability_name(current)

        # 圣羽翼王 [飓风]：若其他翼系队友携带相同技能，该技能获得迅捷
        if ability == "飓风":
            current = state.get_current(team)
            skill_name = skill.name
            team_list  = state.get_team(team)
            for teammate in team_list:
                if teammate is current or teammate.is_fainted:
                    continue
                if teammate.pokemon_type != Type.FLYING and teammate.secondary_type != Type.FLYING:
                    continue
                if any(s.name == skill_name for s in teammate.skills):
                    return 999.0

        # 帕帕斯卡 [翼轴]：1 号位技能获得先手
        if ability == "翼轴" and skill_idx == 0:
            return 999.0

        # 翼龙 [暴食]：龙系技能获得先手
        if ability == "暴食" and skill.skill_type == Type.DRAGON:
            return 999.0

        # 针叶巡林等 [野性感官]：应对成功后下次攻击 priority +1（一次性，由 on_post_attack 清除 flag）
        if ability == "野性感官" and current.feral_senses_priority:
            return 1.0

        return 0.0

    # ------------------------------------------------------------------
    # 攻击修正
    # ------------------------------------------------------------------

    def get_attack_mods(
        self,
        state: "BattleState",
        engine,
        attacker: "Pokemon",
        defender: "Pokemon",
        skill: "Skill",
        skill_idx: int,
        team: str,
        is_first: bool = False,
    ) -> AttackModContext:
        """
        返回攻击端的威力修正。
        power_mult 与 counter_power_mult 相乘；
        power_flat_bonus 传给 calculate_damage 的 extra_power_bonus。
        """
        ctx    = AttackModContext()
        ability = _get_ability_name(attacker)

        # ---- 声波缇塔 [向心力]：前两个有伤技能威力 +30 ----
        if ability == "向心力":
            skills = attacker.skills
            # 找出有威力的技能索引（跳过传动/状态技）
            dmg_indices = [i for i, s in enumerate(skills) if s.power > 0]
            boosted = set(dmg_indices[:2])
            if skill_idx in boosted:
                ctx.power_flat_bonus += 30

        # ---- 巨噬针鼹 [壮胆]：队伍存在虫系则双攻 +50% ----
        if ability == "壮胆":
            team_list = state.get_team(team)
            has_bug = any(
                (p.pokemon_type == Type.BUG or p.secondary_type == Type.BUG)
                for p in team_list
                if not p.is_fainted
            )
            if has_bug:
                ctx.power_mult *= 1.5

        # ---- 恶魔狼 [悲悯]：每有 1 只力竭队友，双攻 +30% ----
        if ability == "悲悯":
            team_list = state.get_team(team)
            fainted_count = sum(
                1 for p in team_list
                if p.is_fainted and p is not attacker
            )
            if fainted_count > 0:
                ctx.power_mult *= (1.0 + 0.3 * fainted_count)

        # ---- 棋绮后 [渗透]：每次武/地技能使用后 +5% 攻防（累计）----
        # 实际攻防提升已写入 attacker.atk_boost 等，此处不额外乘
        # （on_post_attack 中直接修改 boost，damage_calc 会自动应用）

        # ---- 海豹船长 [身经百练]：每次应对，水/武技能威力 +20% ----
        if ability == "身经百练":
            counter = state.ability_counters.get(attacker.name, 0)
            if counter > 0 and skill.skill_type in (Type.WATER, Type.FIGHTING):
                ctx.power_mult *= (1.0 + 0.2 * counter)

        # ---- 画间沉铁兽 [变形活画]：敌方每 10% buff，威力 +10% ----
        if ability == "变形活画":
            # 累计敌方增益层数（以 0.1 为单位取整）
            total_boost = (
                max(0.0, defender.atk_boost)
                + max(0.0, defender.def_boost)
                + max(0.0, defender.spatk_boost)
                + max(0.0, defender.spdef_boost)
                + max(0.0, defender.speed_boost)
            )
            stacks = int(total_boost / 0.1)
            if stacks > 0:
                ctx.power_mult *= (1.0 + 0.1 * stacks)

        # ---- 白金独角兽 [目空]：非光系技能威力 +25% ----
        if ability == "目空" and skill.skill_type != Type.PSYCHIC:
            ctx.power_mult *= 1.25

        # ---- 音速犬 [专注力]：入场首回合，物攻 +100% ----
        if ability == "专注力":
            if attacker.entry_turn >= 0 and state.turn == attacker.entry_turn:
                if skill.category == SkillCategory.PHYSICAL:
                    ctx.power_mult *= 2.0

        # ---- 黑猫巫师 [魔法增效]：魔攻 +70% ----
        if ability == "魔法增效":
            if skill.category == SkillCategory.MAGICAL:
                ctx.power_mult *= 1.7

        # ---- 冰钻布鲁斯 [冰钻]：敌方技能总能耗每 1 点 → 攻击威力 +10% ----
        if ability == "冰钻":
            total_cost = sum(s.energy_cost for s in defender.skills)
            if total_cost > 0:
                ctx.power_mult *= (1.0 + 0.1 * total_cost)

        # ---- 正面印记修正（攻击技能才计算威力加成）----
        if skill.power > 0:
            from sim.mark_system import MarkType
            pos_mark = state.get_positive_mark(team)
            if pos_mark:
                if pos_mark.mark_type == MarkType.CHARGE:
                    # 蓄势印记：攻击威力 +30%/层（能耗 +1/层 由引擎处理）
                    ctx.power_mult *= (1.0 + 0.3 * pos_mark.stacks)
                elif pos_mark.mark_type == MarkType.ELECTRIC:
                    # 蓄电印记：攻击技能平坦威力 +10/层
                    ctx.power_flat_bonus += 10 * pos_mark.stacks
                elif pos_mark.mark_type == MarkType.ATTACK:
                    # 攻击印记：全技能威力 +10%/层
                    ctx.power_mult *= (1.0 + 0.1 * pos_mark.stacks)
                elif pos_mark.mark_type == MarkType.WIND and is_first:
                    # 风起印记：先手时威力 +20%/层
                    ctx.power_mult *= (1.0 + 0.2 * pos_mark.stacks)

        return ctx

    # ------------------------------------------------------------------
    # 防御修正
    # ------------------------------------------------------------------

    def get_defense_mods(
        self,
        state: "BattleState",
        engine,
        attacker: "Pokemon",
        defender: "Pokemon",
        skill: "Skill",
        attacker_team: str,
    ) -> List[float]:
        """
        返回防御端的减伤列表（每项 0~1，多项乘算）。
        """
        reductions: List[float] = []
        ability = _get_ability_name(defender)

        # 秩序鱿墨 [绝对秩序]：受非自身属性技能攻击时伤害 -50%
        if ability == "绝对秩序":
            skill_type = skill.skill_type
            if (skill_type != defender.pokemon_type
                    and (defender.secondary_type is None
                         or skill_type != defender.secondary_type)):
                reductions.append(0.5)

        return reductions

    # ------------------------------------------------------------------
    # 攻击后效果
    # ------------------------------------------------------------------

    def on_post_attack(
        self,
        state: "BattleState",
        engine,
        attacker: "Pokemon",
        defender: "Pokemon",
        skill: "Skill",
        skill_idx: int,
        actual_damage: int,
        team: str,
        counter_applied: bool,
    ) -> None:
        """
        攻击技能命中并造成伤害后触发。
        counter_applied = True 表示本次攻击的 counter_power_mult > 1（应对成功）。
        """
        if defender.is_fainted:
            return
        ability = _get_ability_name(attacker)

        # 千棘盔 [溶解扩散]：使用水系技能时，每携带 1 个毒系技能 → 中毒 +1 层
        if ability == "溶解扩散" and skill.skill_type == Type.WATER:
            poison_skill_count = sum(
                1 for s in attacker.skills if s.skill_type == Type.POISON
            )
            if poison_skill_count > 0:
                defender.poison_stacks += poison_skill_count
                engine._log(
                    f"  [{attacker.name}的溶解扩散] "
                    f"{defender.name} 中毒 +{poison_skill_count} 层"
                )

        # 琉璃水母 [扩散侵蚀]：水系技能命中后，敌方中毒 +(当前层数×2)
        if ability == "扩散侵蚀" and skill.skill_type == Type.WATER:
            current_poison = defender.poison_stacks
            if current_poison > 0:
                extra = current_poison * 2
                defender.poison_stacks += extra
                engine._log(
                    f"  [{attacker.name}的扩散侵蚀] "
                    f"{defender.name} 中毒 +{extra} 层（{current_poison}×2）"
                )

        # 棋绮后 [渗透]：使用武/地系技能后，自身攻防 +5%（永久累积）
        if ability == "渗透" and skill.skill_type in (Type.FIGHTING, Type.GROUND):
            attacker.atk_boost   += 0.05
            attacker.def_boost   += 0.05
            attacker.spatk_boost += 0.05
            attacker.spdef_boost += 0.05
            cnt = state.ability_counters.get(attacker.name, 0) + 1
            state.ability_counters[attacker.name] = cnt
            engine._log(
                f"  [{attacker.name}的渗透] 攻防 +5%（累计第 {cnt} 次）"
            )

        # 海豹船长 [身经百练] 的计数由 on_use_defense_skill 处理

        # 火神等 [助燃]：使用火系技能后，自身双攻 +20%（永久叠加）
        if ability == "助燃" and skill.skill_type == Type.FIRE:
            attacker.atk_boost   += 0.2
            attacker.spatk_boost += 0.2
            engine._log(f"  [{attacker.name}的助燃] 双攻 +20%")

        # 九尾狐等 [灵魂灼伤]：冰系→烧伤×4；火系→冻结×2
        if ability == "灵魂灼伤":
            if skill.skill_type == Type.ICE:
                defender.burn_stacks += 4
                engine._log(f"  [{attacker.name}的灵魂灼伤] {defender.name} 烧伤 +4 层")
            elif skill.skill_type == Type.FIRE:
                defender.freeze_stacks += 2
                engine._log(f"  [{attacker.name}的灵魂灼伤] {defender.name} 冻结 +2 层")

        # 魔力猫等 [氧循环]：使用草系技能后，回复 10% HP
        if ability == "氧循环" and skill.skill_type == Type.GRASS:
            heal = int(attacker.hp * 0.10)
            actual_heal = attacker.heal(heal)
            if actual_heal > 0:
                engine._log(f"  [{attacker.name}的氧循环] 回复 {actual_heal} HP")

        # 水蓝蓝等 [浸润]：使用水系技能后，全技能能耗 -1（永久叠加）
        if ability == "浸润" and skill.skill_type == Type.WATER:
            attacker.energy_cost_reduction += 1
            engine._log(
                f"  [{attacker.name}的浸润] 能耗减免累计 {attacker.energy_cost_reduction}"
            )

        # 针叶巡林等 [野性感官]：自己攻击后清除一次性先手 flag
        if ability == "野性感官" and attacker.feral_senses_priority:
            attacker.feral_senses_priority = False

        # ---- 龙噬印记：使用 3 能耗技能 → 自身双攻 +30%/层 ----
        from sim.mark_system import MarkType, MarkCategory
        pos_mark = state.get_positive_mark(team)
        if pos_mark and pos_mark.mark_type == MarkType.DRAGON:
            if skill.energy_cost == 3:
                boost = 0.3 * pos_mark.stacks
                attacker.atk_boost   += boost
                attacker.spatk_boost += boost
                engine._log(
                    f"  [龙噬印记×{pos_mark.stacks}] {attacker.name} 双攻 +{int(boost*100)}%"
                )

        # ---- 星陨印记：受到非幻系攻击 → 消耗全层造成额外幻系伤害 ----
        if not defender.is_fainted and skill.skill_type != Type.PSYCHIC:
            enemy_team = state.enemy_team_id(team)
            neg_mark_def = state.get_negative_mark(enemy_team)
            if neg_mark_def and neg_mark_def.mark_type == MarkType.METEOR:
                stacks = neg_mark_def.stacks
                # 月牙雪熊 [月牙雪糕]：敌方每层冻结视为 1 层额外星陨
                if _get_ability_name(attacker) == "月牙雪糕" and defender.freeze_stacks > 0:
                    stacks += defender.freeze_stacks
                state.clear_mark(enemy_team, MarkCategory.NEGATIVE)
                extra_dmg = int(
                    (defender.sp_attack / max(1, attacker.sp_defense)) * 0.9 * 30 * stacks
                )
                if extra_dmg > 0:
                    attacker.take_damage(extra_dmg)
                    engine._log(
                        f"  [星陨印记×{stacks}] {defender.name} 反击！"
                        f"额外幻系伤害 {extra_dmg} → {attacker.name}"
                    )

    # ------------------------------------------------------------------
    # 使用防御技能时
    # ------------------------------------------------------------------

    def on_use_defense_skill(
        self,
        state: "BattleState",
        engine,
        user: "Pokemon",
        team: str,
    ) -> None:
        """
        使用防御技能后触发。
        海豹船长 [身经百练]：己方任意精灵每应对1次，累计计数，
        身经百练持有者的水/武技能威力 +20%/次。
        """
        # 在当前队伍中查找携带 身经百练 的精灵并累积计数
        team_list = state.get_team(team)
        for p in team_list:
            if _get_ability_name(p) == "身经百练" and not p.is_fainted:
                cnt = state.ability_counters.get(p.name, 0) + 1
                state.ability_counters[p.name] = cnt
                engine._log(
                    f"  [{p.name}的身经百练] 队友应对！"
                    f"水/武技能威力 +20%（累计 {cnt} 次）"
                )
                break  # 每队只有一个 身经百练

        # 针叶巡林等 [野性感官]：自身使用防御技能即视为应对成功，下次攻击 priority+1
        if _get_ability_name(user) == "野性感官":
            user.feral_senses_priority = True
            engine._log(f"  [{user.name}的野性感官] 下次行动获得先手 +1")

        # 瞌睡王 [慢热型]：在场之外的队友每应对 1 次，累计计数（cap 2）
        # 仅当瞌睡王在队伍中且不在场时生效
        sleep_king = next(
            (p for p in team_list
             if _get_ability_name(p) == "慢热型" and not p.is_fainted),
            None,
        )
        if sleep_king is not None:
            cur_idx = state.get_current_idx(team)
            on_field = team_list[cur_idx] is sleep_king
            if not on_field:
                key = f"slow_heat_{team}"
                cnt = state.ability_counters.get(key, 0)
                if cnt < 2:
                    state.ability_counters[key] = cnt + 1
                    engine._log(
                        f"  [{sleep_king.name}的慢热型] 队友应对累计 {cnt + 1}/2"
                    )

    # ------------------------------------------------------------------
    # 冻结附加（捉迷藏）
    # ------------------------------------------------------------------

    def on_freeze_applied(
        self,
        state: "BattleState",
        engine,
        attacker: "Pokemon",
        defender: "Pokemon",
        stacks_added: int,
    ) -> None:
        """
        敌方被附加冻结层数后触发。
        大耳帽兜 [捉迷藏]：自己造成的冻结期间，敌方全技能能耗 +1。
        """
        if stacks_added <= 0 or defender.is_fainted:
            return
        if _get_ability_name(attacker) == "捉迷藏":
            defender.hideseek_freeze_active = True
            defender.extra_energy_cost = 1
            engine._log(
                f"  [{attacker.name}的捉迷藏] {defender.name} 冻结期间能耗 +1"
            )

    # ------------------------------------------------------------------
    # 状态技能使用后（泛音列）
    # ------------------------------------------------------------------

    def on_use_status_skill(
        self,
        state: "BattleState",
        engine,
        user: "Pokemon",
        target: "Pokemon",
        skill: "Skill",
        team: str,
    ) -> None:
        """
        状态技能使用后触发。
        号儿鱼 [泛音列]：使用状态技能后，敌方 3 回合内全技能能耗 +3（再触发刷新）。
        """
        if _get_ability_name(user) == "泛音列" and not target.is_fainted:
            target.quiet_debuff_turns = 3
            target.quiet_debuff_extra = 3
            engine._log(
                f"  [{user.name}的泛音列] {target.name} 全技能能耗 +3（3 回合）"
            )

    # ------------------------------------------------------------------
    # 回合开始（预警 / 哨兵：威胁预测）
    # ------------------------------------------------------------------

    def on_turn_start(
        self,
        state: "BattleState",
        engine,
    ) -> None:
        """
        回合开始时触发，在 _determine_order 之前调用。
        预警 / 哨兵：若敌方任一技能能击败自己，本回合速度 +50。
        """
        for team in ("a", "b"):
            current = state.get_current(team)
            if current.is_fainted:
                continue
            ability = _get_ability_name(current)
            if ability not in ("预警", "哨兵"):
                continue
            enemy_team = "b" if team == "a" else "a"
            enemy = state.get_current(enemy_team)
            if enemy.is_fainted:
                continue
            # 预测敌方任一攻击技能造成的最大伤害（不考虑能耗/CD/应对）
            from sim.damage_calc import calculate_damage
            max_dmg = 0
            for s in enemy.skills:
                if s.power <= 0:
                    continue
                try:
                    dmg = calculate_damage(
                        enemy, current, s, weather=state.weather
                    )
                except Exception:
                    dmg = 0
                if dmg > max_dmg:
                    max_dmg = dmg
            if max_dmg >= current.current_hp:
                current.temp_speed_bonus = 50.0
                if ability == "哨兵":
                    current.sentinel_must_switch = True
                engine._log(
                    f"  [{current.name}的{ability}] 预警敌方威胁({max_dmg}≥{current.current_hp})，速度+50"
                )

    def get_temp_speed_bonus(
        self, state: "BattleState", team: str
    ) -> float:
        """
        返回当前精灵的临时速度加成（预警/哨兵），由引擎在 _determine_order 中使用。
        """
        current = state.get_current(team)
        return current.temp_speed_bonus

    def clear_temp_speed_bonus(self, state: "BattleState") -> None:
        """回合结束时清空所有精灵的临时速度加成。"""
        for p in state.team_a + state.team_b:
            p.temp_speed_bonus = 0.0

    # ------------------------------------------------------------------
    # 陨落（落陨星兔）：跳过回合结束伤害类效果
    # ------------------------------------------------------------------

    def is_falling_star_active(self, state: "BattleState") -> bool:
        """
        若双方任一在场精灵带 [陨落]，返回 True；
        引擎据此跳过烧伤伤害 / 中毒伤害 / 印记伤害（不含特性触发与冻毙）。
        """
        for team in ("a", "b"):
            p = state.get_current(team)
            if not p.is_fainted and _get_ability_name(p) == "陨落":
                return True
        return False

    # ------------------------------------------------------------------
    # 烧伤衰减拦截
    # ------------------------------------------------------------------

    def intercept_burn_decay(
        self,
        state: "BattleState",
        engine,
        pokemon: "Pokemon",
    ) -> bool:
        """
        返回 True 时，该精灵的烧伤层数本回合增长 +1，而非减半。
        燃薪虫 [煤渣草]：在场时，场上所有精灵的烧伤增长而非衰减。
        """
        for on_field in (
            state.team_a[state.current_a] if state.team_a else None,
            state.team_b[state.current_b] if state.team_b else None,
        ):
            if on_field and not on_field.is_fainted:
                if _get_ability_name(on_field) == "煤渣草":
                    return True
        return False

    # ------------------------------------------------------------------
    # 嫁祸：连击加成查询 + 受伤里程碑检查
    # ------------------------------------------------------------------

    def get_extra_hit_count(
        self,
        state: "BattleState",
        attacker: "Pokemon",
        skill: "Skill",
        skill_idx: int,
    ) -> int:
        """朔夜伊芙 [嫁祸]：穿越 HP 里程碑后，技能获得连击加成"""
        if _get_ability_name(attacker) == "嫁祸" and attacker.hit_count_bonus > 0:
            return attacker.hit_count_bonus
        return 0

    def on_defender_damaged(
        self,
        state: "BattleState",
        engine,
        defender: "Pokemon",
        old_hp: int,
        new_hp: int,
    ) -> None:
        """
        防守方受伤后检查 嫁祸 的 HP 里程碑。
        每次 HP 从某里程碑（75% / 50% / 25%）以上降至以下时，连击 +2。
        已触发的里程碑不会重复触发（即使回血后再次下降也不触发）。
        """
        if _get_ability_name(defender) != "嫁祸":
            return
        max_hp = defender.hp
        # bit0=75%  bit1=50%  bit2=25%
        thresholds = [(0, 0.75), (1, 0.50), (2, 0.25)]
        for bit, pct in thresholds:
            if (defender.hp_milestone_flags >> bit) & 1:
                continue  # 已触发，跳过
            threshold_hp = int(max_hp * pct)
            if old_hp > threshold_hp >= new_hp:
                defender.hit_count_bonus    += 2
                defender.hp_milestone_flags |= (1 << bit)
                engine._log(
                    f"  [{defender.name}的嫁祸] HP 降至 {int(pct*100)}% 以下，"
                    f"连击 +2（累计加成 +{defender.hit_count_bonus}）"
                )

    # ------------------------------------------------------------------
    # 印记伤害（每回合结束统一结算）
    # ------------------------------------------------------------------

    def apply_mark_damage(self, state: "BattleState", engine) -> None:
        """
        对双方当前场上精灵施加负面印记的回合结算伤害。
        中毒印记：每层每回合扣场上精灵 3% HP。
        """
        from sim.mark_system import MarkType
        for team in ("a", "b"):
            neg_mark = state.get_negative_mark(team)
            if not neg_mark or neg_mark.stacks <= 0:
                continue
            current = state.get_current(team)
            if current.is_fainted:
                continue
            if neg_mark.mark_type == MarkType.POISON:
                dmg = int(current.hp * 0.03 * neg_mark.stacks)
                if dmg > 0:
                    current.take_damage(dmg)
                    engine._log(
                        f"  {current.name} 中毒印记伤害 {dmg}"
                        f" ({neg_mark.stacks}层，HP:{current.current_hp}/{current.hp})"
                    )

    # ------------------------------------------------------------------
    # 回合结束特性效果：蚀刻 / 特殊清洁场景 / 印记伤害
    # ------------------------------------------------------------------

    def on_turn_end(self, state: "BattleState", engine) -> None:
        """
        回合结束时的特性效果，在状态伤害之后、冷却递减之前调用。
        顺序：蚀刻转化 → 食尘短绒偷印记 → 光合印记回能 → 印记伤害
        """
        from sim.mark_system import MarkType, TeamMark

        # ---- 裘卡 [蚀刻]：敌方每 2 层中毒转化为 1 层中毒印记 ----
        for team in ("a", "b"):
            current = state.get_current(team)
            if current.is_fainted or _get_ability_name(current) != "蚀刻":
                continue
            enemy_team = "b" if team == "a" else "a"
            enemy      = state.get_current(enemy_team)
            if enemy.is_fainted or enemy.poison_stacks < 2:
                continue
            converted = enemy.poison_stacks // 2
            enemy.poison_stacks -= converted * 2
            state.set_mark(enemy_team, TeamMark(MarkType.POISON, converted))
            total_stacks = state.get_negative_mark(enemy_team).stacks
            engine._log(
                f"  [{current.name}的蚀刻] {enemy.name} 中毒{converted*2}层 → "
                f"中毒印记+{converted}层（{enemy_team}队共{total_stacks}层）"
            )

        # ---- 食尘短绒 [特殊清洁场景]：偷取敌方 1 层印记（优先正面印记）----
        for team in ("a", "b"):
            current = state.get_current(team)
            if current.is_fainted or _get_ability_name(current) != "特殊清洁场景":
                continue
            enemy_team  = "b" if team == "a" else "a"
            enemy_pos   = state.get_positive_mark(enemy_team)
            enemy_neg   = state.get_negative_mark(enemy_team)
            # 优先偷正面印记
            target_mark = enemy_pos if (enemy_pos and enemy_pos.stacks > 0) else (
                enemy_neg if (enemy_neg and enemy_neg.stacks > 0) else None
            )
            if not target_mark:
                continue
            stolen_type = target_mark.mark_type
            target_mark.stacks -= 1
            if target_mark.stacks == 0:
                state.clear_mark(enemy_team, target_mark.category)
            state.set_mark(team, TeamMark(stolen_type, 1))
            engine._log(
                f"  [{current.name}的特殊清洁场景] 偷取敌方 1 层{stolen_type.value}"
            )

        # ---- 光合印记：回合结束获得 1 能量/层 ----
        for team in ("a", "b"):
            pos_mark = state.get_positive_mark(team)
            if not pos_mark or pos_mark.mark_type != MarkType.PHOTO:
                continue
            current = state.get_current(team)
            if current.is_fainted:
                continue
            current.gain_energy(pos_mark.stacks)
            engine._log(
                f"  [光合印记×{pos_mark.stacks}] {current.name} 回合结束获得 {pos_mark.stacks} 能量"
            )

        # ---- 怖哭菇等 [吸积盘]：回合结束敌方获得 2 层星陨印记 ----
        for team in ("a", "b"):
            current = state.get_current(team)
            if current.is_fainted or _get_ability_name(current) != "吸积盘":
                continue
            enemy_team = "b" if team == "a" else "a"
            existing = state.get_negative_mark(enemy_team)
            if existing and existing.mark_type == MarkType.METEOR:
                existing.stacks += 2
                total = existing.stacks
            else:
                state.set_mark(enemy_team, TeamMark(MarkType.METEOR, 2))
                total = 2
            engine._log(
                f"  [{current.name}的吸积盘] {enemy_team} 队星陨印记 +2（共{total}层）"
            )

        # ---- 不朽：力竭后倒计时复活；归零时满血满能量复活（不补 lives，不强制上场）----
        from sim.pokemon import ENERGY_MAX
        from sim.types import StatusType
        for team in ("a", "b"):
            for p in state.get_team(team):
                if p.revive_timer <= 0:
                    continue
                p.revive_timer -= 1
                if p.revive_timer == 0:
                    p.current_hp        = p.hp
                    p.energy            = ENERGY_MAX
                    p.status            = StatusType.NORMAL
                    p.burn_stacks       = 0
                    p.poison_stacks     = 0
                    p.freeze_stacks     = 0
                    p.atk_boost = p.def_boost = p.spatk_boost = p.spdef_boost = p.speed_boost = 0.0
                    p.atk_reduce = p.def_reduce = p.spatk_reduce = p.spdef_reduce = p.speed_reduce = 0.0
                    p.entry_turn        = -1
                    engine._log(f"  [{p.name}的不朽] 复活！满血满能量回到队伍")
                else:
                    engine._log(
                        f"  [{p.name}的不朽] 复活倒计时 {p.revive_timer} 回合"
                    )

        # ---- 印记伤害（对双方当前场上精灵；陨落生效时跳过） ----
        if not self.is_falling_star_active(state):
            self.apply_mark_damage(state, engine)

        # ---- 捉迷藏：冻结归零时清除 hideseek 标记 + 额外能耗 ----
        for p in state.team_a + state.team_b:
            if p.hideseek_freeze_active and p.freeze_stacks <= 0:
                p.hideseek_freeze_active = False
                p.extra_energy_cost = 0

        # ---- 泛音列：倒计时递减；归零时清除 ----
        for p in state.team_a + state.team_b:
            if p.quiet_debuff_turns > 0:
                p.quiet_debuff_turns -= 1
                if p.quiet_debuff_turns == 0:
                    p.quiet_debuff_extra = 0

        # ---- 预警/哨兵：清空本回合临时速度加成 ----
        self.clear_temp_speed_bonus(state)

    # ------------------------------------------------------------------
    # 印记：能耗修正 / 速度惩罚（由 battle_engine 查询）
    # ------------------------------------------------------------------

    def get_mark_energy_cost_mod(
        self, state: "BattleState", team: str, skill: "Skill"
    ) -> int:
        """
        返回印记对技能能耗的修正值（正数=增加，负数=减少）。
        湿润印记：能耗 -1/层；蓄势印记：能耗 +1/层。
        利灯鱼 [对流]：自身印记能耗修正取反。
        """
        from sim.mark_system import MarkType
        pos_mark = state.get_positive_mark(team)
        mod = 0
        if pos_mark:
            if pos_mark.mark_type == MarkType.WET:
                mod = -pos_mark.stacks
            elif pos_mark.mark_type == MarkType.CHARGE and skill.power > 0:
                # 蓄势印记只对攻击技能增加能耗
                mod = pos_mark.stacks
        # 利灯鱼 [对流]：自身印记能耗修正取反
        current = state.get_current(team)
        if _get_ability_name(current) == "对流" and mod != 0:
            mod = -mod
        return mod

    def get_mark_speed_penalty(self, state: "BattleState", team: str) -> float:
        """
        返回减速印记带来的速度惩罚（扁平值，从有效速度中减去）。
        减速印记：速度 -10/层。
        """
        from sim.mark_system import MarkType
        neg_mark = state.get_negative_mark(team)
        if neg_mark and neg_mark.mark_type == MarkType.SLOW:
            return float(neg_mark.stacks * 10)
        return 0.0

    # ------------------------------------------------------------------
    # 星地善良：回合结束自动换入
    # ------------------------------------------------------------------

    def on_turn_end_switches(self, state: "BattleState", engine) -> None:
        """
        小皮球 [星地善良]：回合结束时，若当前场上己方精灵能量 = 0，
        小皮球强制换入替换该精灵。
        """
        for team in ("a", "b"):
            current = state.get_current(team)
            if current.is_fainted or current.energy > 0:
                continue
            team_list = state.get_team(team)
            cur_idx   = state.get_current_idx(team)
            for i, p in enumerate(team_list):
                if i == cur_idx or p.is_fainted:
                    continue
                if _get_ability_name(p) == "星地善良":
                    engine._log(
                        f"  [{p.name}的星地善良] {current.name} 能量归零，"
                        f"{p.name} 强制换入！"
                    )
                    engine._apply_switch(team, i)
                    break


# ============================================================
# 模块级单例（battle_engine.py 直接 import 使用）
# ============================================================

_ability_hooks = AbilityHooks()
