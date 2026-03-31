"""
NRC_SIM 战斗引擎 — 回合主循环

洛克王国战斗流程：
1. 双方同时选择动作
2. 按速度（含先手修正）决定执行顺序
3. 先手执行 → 自动换人 → 检查胜负
4. 后手执行 → 自动换人
5. 回合结束效果（中毒/灼烧/冻结/天气） → 自动换人
6. 回合数 +1

天气系统（持续 8 回合）：
- 雪天：场上精灵每回合获得 2 层冻结
- 沙暴：地系技能能耗减半（向下取整）
- 雨天：水系招式威力 +50%（已在 damage_calc 中处理）
"""

import math
import random
from typing import Tuple, Optional, List

from sim.types import Type, SkillCategory, StatusType, Weather, WEATHER_DURATION, get_type_effectiveness
from sim.skill import Skill
from sim.pokemon import Pokemon, ENERGY_MAX
from sim.battle_state import BattleState
from sim.damage_calc import calculate_damage
from sim.counter_system import resolve_counter, CounterResult


# ============================================================
# 类型别名
# ============================================================
Action = Tuple[int, ...]


# ============================================================
# 战斗引擎
# ============================================================
class BattleEngine:
    """洛克王国战斗引擎"""

    GATHER_ENERGY = 5       # 汇合聚能回复量
    MAX_TURNS = 150         # 最大回合数

    def __init__(self, state: BattleState, verbose: bool = False):
        self.state = state
        self.verbose = verbose
        self.log: List[str] = []

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def get_actions(self, team: str) -> List[Action]:
        """获取指定队伍的合法动作列表"""
        team_list = self.state.get_team(team)
        idx = self.state.get_current_idx(team)
        current = team_list[idx]

        # 当前精灵已倒下 → 只能换人
        if current.is_fainted:
            actions = []
            for i, p in enumerate(team_list):
                if i != idx and not p.is_fainted:
                    actions.append((-2, i))
            return actions if actions else [(-1,)]

        # 汇合聚能始终可选
        actions: List[Action] = [(-1,)]

        # 可用技能（考虑沙暴对地系技能的能耗减半）
        for i, skill in enumerate(current.skills):
            cd = current.cooldowns.get(i, 0)
            cost = self._get_effective_energy_cost(skill)
            if current.energy >= cost and cd <= 0:
                actions.append((i,))

        # 可换人
        for i, p in enumerate(team_list):
            if i != idx and not p.is_fainted:
                actions.append((-2, i))

        return actions if actions else [(-1,)]

    def check_winner(self) -> Optional[str]:
        """
        检查胜负（roco-world 4 格生命制）：
        生命格归 0 的一方判负；若双方同时归 0 则后手方（本回合先击倒的）获胜。
        兜底：若全队精灵均倒下也判负。
        """
        if self.state.lives_a <= 0 or all(p.is_fainted for p in self.state.team_a):
            return "b"
        if self.state.lives_b <= 0 or all(p.is_fainted for p in self.state.team_b):
            return "a"
        return None

    # ------------------------------------------------------------------
    # 生命格结算
    # ------------------------------------------------------------------
    def _fainted_snapshot(self):
        """返回 (frozenset_a, frozenset_b) — 当前已倒下精灵的名字集合"""
        return (
            frozenset(p.name for p in self.state.team_a if p.is_fainted),
            frozenset(p.name for p in self.state.team_b if p.is_fainted),
        )

    def _apply_life_events(self, snap_before, snap_after) -> None:
        """
        对比两个快照，结算新增倒下事件：
        - 精灵倒下方 lives -1，对方不变
        """
        new_fainted_a = snap_after[0] - snap_before[0]
        new_fainted_b = snap_after[1] - snap_before[1]

        for name in new_fainted_a:
            self.state.lives_a = max(0, self.state.lives_a - 1)
            self._log(f"  ⚡ {name} 倒下！"
                      f"  A队生命格:{self.state.lives_a}  B队生命格:{self.state.lives_b}")

        for name in new_fainted_b:
            self.state.lives_b = max(0, self.state.lives_b - 1)
            self._log(f"  ⚡ {name} 倒下！"
                      f"  A队生命格:{self.state.lives_a}  B队生命格:{self.state.lives_b}")

    def execute_turn(self, action_a: Action, action_b: Action) -> Optional[str]:
        """
        执行一个完整回合。

        Returns
        -------
        胜者 ("a" / "b") 或 None（未分胜负）
        """
        # 1. 先手判定
        first_team, first_act, second_team, second_act = \
            self._determine_order(action_a, action_b)

        # 2. 先手行动（含生命格结算）
        snap = self._fainted_snapshot()
        self._execute_action(first_team, first_act, second_team, second_act)
        self._apply_life_events(snap, self._fainted_snapshot())
        self._auto_switch()

        winner = self.check_winner()
        if winner:
            return winner

        # 3. 后手行动（含生命格结算）
        snap = self._fainted_snapshot()
        self._execute_action(second_team, second_act, first_team, first_act)
        self._apply_life_events(snap, self._fainted_snapshot())
        self._auto_switch()

        winner = self.check_winner()
        if winner:
            return winner

        # 4. 回合结束效果（含生命格结算）
        snap = self._fainted_snapshot()
        self._turn_end_effects()
        self._apply_life_events(snap, self._fainted_snapshot())
        self._auto_switch()

        # 5. 回合数 +1
        self.state.turn += 1

        return self.check_winner()

    # ------------------------------------------------------------------
    # 天气相关
    # ------------------------------------------------------------------
    def set_weather(self, weather: Weather) -> None:
        """设置天气（持续 8 回合）"""
        self.state.weather = weather
        self.state.weather_turns = WEATHER_DURATION
        self._log(f"  天气变为: {weather.value} (持续{WEATHER_DURATION}回合)")

    def _get_effective_energy_cost(self, skill: Skill) -> int:
        """获取有效能耗（沙暴下地系技能能耗减半）"""
        cost = skill.energy_cost
        if self.state.weather == Weather.SANDSTORM and skill.skill_type == Type.GROUND:
            cost = cost // 2  # 向下取整
        return cost

    # ------------------------------------------------------------------
    # 先手判定
    # ------------------------------------------------------------------
    def _determine_order(
        self, action_a: Action, action_b: Action
    ) -> Tuple[str, Action, str, Action]:
        """返回 (先手队伍, 先手动作, 后手队伍, 后手动作)"""
        p_a = self.state.get_current("a")
        p_b = self.state.get_current("b")

        priority_a = self._get_priority("a", action_a)
        priority_b = self._get_priority("b", action_b)

        spd_a = p_a.effective_speed() * (1.0 + priority_a)
        spd_b = p_b.effective_speed() * (1.0 + priority_b)

        if spd_a >= spd_b:
            return "a", action_a, "b", action_b
        else:
            return "b", action_b, "a", action_a

    def _get_priority(self, team: str, action: Action) -> float:
        """获取先手修正值"""
        if action[0] < 0:
            return 0.0
        current = self.state.get_current(team)
        skill = current.skills[action[0]]
        return skill.priority_mod * 0.1

    # ------------------------------------------------------------------
    # 执行单个行动
    # ------------------------------------------------------------------
    def _execute_action(
        self,
        team: str,
        action: Action,
        enemy_team: str,
        enemy_action: Action,
    ) -> None:
        """执行一方的行动 + 应对解析"""
        team_list = self.state.get_team(team)
        idx = self.state.get_current_idx(team)
        current = team_list[idx]
        enemy = self.state.get_current(enemy_team)

        # ---- 换人 ----
        if action[0] == -2:
            self._apply_switch(team, action[1])
            new_p = team_list[action[1]]
            self._log(f"[{team.upper()}] {current.name} 换人 → {new_p.name} (HP:{new_p.current_hp}/{new_p.hp} 能量:{new_p.energy})")
            return

        # ---- 汇合聚能 ----
        if action[0] == -1:
            old_e = current.energy
            current.gain_energy(self.GATHER_ENERGY)
            self._log(f"[{team.upper()}] {current.name} 汇合聚能 (能量:{old_e}→{current.energy})")
            return

        skill = current.skills[action[0]]

        # ---- 能量不足 → 强制聚能 ----
        cost = self._get_effective_energy_cost(skill)
        if current.energy < cost:
            old_e = current.energy
            current.gain_energy(self.GATHER_ENERGY)
            self._log(f"[{team.upper()}] {current.name} 能量不足({current.energy}<{cost})，改为聚能 (能量:{old_e}→{current.energy})")
            return

        # 扣除能量（使用有效能耗）
        current.energy -= cost

        # ---- 脱离 ----
        if skill.force_switch:
            self._apply_escape(team, team_list, idx)
            new_idx = self.state.get_current_idx(team)
            new_p = team_list[new_idx]
            self._log(f"[{team.upper()}] {current.name} 使用 {skill.name}（脱离）→ {new_p.name} 登场")
            return

        # 获取对方技能（用于应对判定）
        enemy_skill = self._get_enemy_skill(enemy, enemy_action)

        # ---- 防御技能 ----
        if skill.is_defense:
            old_hp = current.current_hp
            self._apply_defense_skill(current, skill, enemy_skill)
            self._log(f"[{team.upper()}] {current.name} 使用 {skill.name}（防御 减伤{int(skill.damage_reduction*100)}%）")
            if current.current_hp > old_hp:
                self._log(f"  → {current.name} 回复 {current.current_hp - old_hp} HP ({old_hp}→{current.current_hp})")
            return

        # ---- 状态技能 ----
        if skill.is_status:
            old_hp_user = current.current_hp
            old_hp_enemy = enemy.current_hp
            self._apply_status_skill(current, enemy, skill)
            parts = []
            if skill.poison_stacks > 0: parts.append(f"中毒{skill.poison_stacks}层")
            if skill.burn_stacks > 0: parts.append(f"灼烧{skill.burn_stacks}层")
            if skill.freeze_stacks > 0: parts.append(f"冻结{skill.freeze_stacks}层")
            if skill.steal_energy > 0: parts.append(f"偷取{skill.steal_energy}能量")
            if skill.enemy_lose_energy > 0: parts.append(f"扣{skill.enemy_lose_energy}能量")
            buff_parts = []
            if skill.self_atk + skill.self_all_atk > 0: buff_parts.append(f"攻+{int((skill.self_atk+skill.self_all_atk)*100)}%")
            if skill.self_def + skill.self_all_def > 0: buff_parts.append(f"防+{int((skill.self_def+skill.self_all_def)*100)}%")
            if buff_parts: parts.append("自身" + "/".join(buff_parts))
            debuff_parts = []
            if skill.enemy_atk + skill.enemy_all_atk > 0: debuff_parts.append(f"攻-{int((skill.enemy_atk+skill.enemy_all_atk)*100)}%")
            if skill.enemy_def + skill.enemy_all_def > 0: debuff_parts.append(f"防-{int((skill.enemy_def+skill.enemy_all_def)*100)}%")
            if debuff_parts: parts.append("敌方" + "/".join(debuff_parts))
            effect_str = " | ".join(parts) if parts else "无额外效果"
            self._log(f"[{team.upper()}] {current.name} 使用 {skill.name}（状态）→ {effect_str}")
            if current.current_hp > old_hp_user:
                self._log(f"  → {current.name} 回复 {current.current_hp - old_hp_user} HP")
            return

        # ---- 攻击技能 ----
        self._apply_attack_skill(current, enemy, skill, enemy_skill, team)
        # 日志在 _apply_attack_skill 内部输出

    # ------------------------------------------------------------------
    # 动作执行：防御技能
    # ------------------------------------------------------------------
    def _apply_defense_skill(
        self, user: Pokemon, skill: Skill, enemy_skill: Optional[Skill]
    ) -> None:
        """防御技能：buff + 回复"""
        user.apply_self_buff(skill)

        if skill.self_heal_hp > 0:
            heal = int(user.hp * skill.self_heal_hp)
            user.heal(heal)

        if skill.self_heal_energy > 0:
            user.gain_energy(skill.self_heal_energy)

    # ------------------------------------------------------------------
    # 动作执行：状态技能
    # ------------------------------------------------------------------
    def _apply_status_skill(
        self, user: Pokemon, target: Pokemon, skill: Skill
    ) -> None:
        """状态技能：buff/debuff + 能量操作 + 异常状态附加"""
        user.apply_self_buff(skill)
        target.apply_enemy_debuff(skill)

        if skill.self_heal_hp > 0:
            heal = int(user.hp * skill.self_heal_hp)
            user.heal(heal)
        if skill.self_heal_energy > 0:
            user.gain_energy(skill.self_heal_energy)
        if skill.steal_energy > 0:
            user.gain_energy(skill.steal_energy)
            target.lose_energy(skill.steal_energy)
        if skill.enemy_lose_energy > 0:
            target.lose_energy(skill.enemy_lose_energy)

        self._apply_status_stacks(target, skill)

        if skill.force_switch:
            team = self._find_team_of(user)
            if team:
                team_list = self.state.get_team(team)
                idx = self.state.get_current_idx(team)
                self._apply_escape(team, team_list, idx)

    # ------------------------------------------------------------------
    # 动作执行：攻击技能
    # ------------------------------------------------------------------
    def _apply_attack_skill(
        self,
        attacker: Pokemon,
        defender: Pokemon,
        skill: Skill,
        enemy_skill: Optional[Skill],
        team: str = "a",
    ) -> None:
        """攻击技能：buff/debuff + 异常 + 能量 + 伤害 + 应对 + 吸血 + 回复"""

        # 1. 自身 buff
        attacker.apply_self_buff(skill)

        # 2. 敌方 debuff
        defender.apply_enemy_debuff(skill)

        # 3. 状态层数附加
        self._apply_status_stacks(defender, skill)

        # 4. 能量效果
        if skill.steal_energy > 0:
            attacker.gain_energy(skill.steal_energy)
            defender.lose_energy(skill.steal_energy)
        if skill.enemy_lose_energy > 0:
            defender.lose_energy(skill.enemy_lose_energy)

        # 5. 伤害计算
        if skill.power <= 0 or defender.is_fainted:
            self._apply_self_recovery(attacker, skill)
            self._log(f"[{team.upper()}] {attacker.name} 使用 {skill.name}（{skill.category.value}）→ 无伤害效果")
            return

        # 克制关系
        eff = get_type_effectiveness(skill.skill_type, defender.pokemon_type)
        if eff >= 2.0:
            eff_text = "克制！"
        elif eff > 1.0:
            eff_text = "效果拔群"
        elif eff == 1.0:
            eff_text = "普通"
        elif eff > 0:
            eff_text = "效果不佳"
        else:
            eff_text = "免疫！"
        stab = skill.skill_type == attacker.pokemon_type
        stab_text = " 本系加成" if stab else ""

        # 应对解析
        counter_power_mult = 1.0
        damage_reductions: List[float] = []
        counter_result = CounterResult()
        reflect_damage = 0
        counter_text = ""

        if enemy_skill and not defender.is_fainted:
            counter_result = resolve_counter(
                attacker, defender, skill, enemy_skill, 0
            )
            counter_power_mult = counter_result.power_mult

            dummy_dmg = calculate_damage(
                attacker, defender, skill,
                counter_power_mult=counter_power_mult,
                weather=self.state.weather,
            )
            counter_result = resolve_counter(
                attacker, defender, skill, enemy_skill, dummy_dmg
            )

            if enemy_skill.is_defense and enemy_skill.damage_reduction > 0:
                damage_reductions.append(enemy_skill.damage_reduction)
                counter_text = f" 被{defender.name}防御减伤{int(enemy_skill.damage_reduction*100)}%"

            if counter_power_mult > 1.0:
                counter_text += f" 应对成功威力×{counter_power_mult}"

            reflect_damage = counter_result.reflect_damage

        # 最终伤害计算
        damage = calculate_damage(
            attacker, defender, skill,
            counter_power_mult=counter_power_mult,
            damage_reductions=damage_reductions if damage_reductions else None,
            weather=self.state.weather,
        )

        # 日志：谁用了什么技能
        hit_text = f" {skill.hit_count}连击" if skill.hit_count > 1 else ""
        self._log(f"[{team.upper()}] {attacker.name} 使用 {skill.name}（{skill.category.value} {skill.skill_type.value}系 威力{skill.power}）{hit_text}")

        # 6. 扣血
        hp_before = defender.current_hp
        actual_damage = defender.take_damage(damage)
        fainted_text = " → 倒下！" if defender.is_fainted else ""
        self._log(f"  → 对 {defender.name} 造成 {actual_damage} 点伤害 [{eff_text}{stab_text}{counter_text}] (HP: {hp_before}→{defender.current_hp}/{defender.hp}){fainted_text}")

        # 7. 反弹伤害
        if reflect_damage > 0:
            ref_actual = attacker.take_damage(reflect_damage)
            self._log(f"  → {attacker.name} 受到反弹伤害 {ref_actual}")

        # 8. 吸血
        if skill.life_drain > 0:
            heal = int(actual_damage * skill.life_drain)
            healed = attacker.heal(heal)
            if healed > 0:
                self._log(f"  → {attacker.name} 吸血回复 {healed} HP ({attacker.current_hp - healed}→{attacker.current_hp})")

        # 9. 自身回复
        old_hp = attacker.current_hp
        self._apply_self_recovery(attacker, skill)
        if attacker.current_hp > old_hp:
            self._log(f"  → {attacker.name} 技能回复 {attacker.current_hp - old_hp} HP")

        # 9. 自身回复
        self._apply_self_recovery(attacker, skill)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _apply_status_stacks(self, target: Pokemon, skill: Skill) -> None:
        """附加异常状态层数"""
        if skill.poison_stacks > 0:
            target.poison_stacks += skill.poison_stacks
        if skill.burn_stacks > 0:
            target.burn_stacks += skill.burn_stacks
        if skill.freeze_stacks > 0:
            target.freeze_stacks += skill.freeze_stacks

    def _apply_self_recovery(self, user: Pokemon, skill: Skill) -> None:
        """自身回复 HP 和能量"""
        if skill.self_heal_hp > 0:
            heal = int(user.hp * skill.self_heal_hp)
            user.heal(heal)
        if skill.self_heal_energy > 0:
            user.gain_energy(skill.self_heal_energy)

    def _apply_switch(self, team: str, target_idx: int) -> None:
        """换人"""
        self.state.set_current_idx(team, target_idx)

    def _apply_escape(self, team: str, team_list: List[Pokemon], current_idx: int) -> None:
        """脱离：随机切换到一个存活队友"""
        alive = [i for i, p in enumerate(team_list) if not p.is_fainted and i != current_idx]
        if alive:
            new_idx = random.choice(alive)
            self.state.set_current_idx(team, new_idx)

    def _get_enemy_skill(self, enemy: Pokemon, enemy_action: Action) -> Optional[Skill]:
        """获取对方使用的技能（若有的话）"""
        if enemy_action[0] >= 0 and not enemy.is_fainted:
            return enemy.skills[enemy_action[0]]
        return None

    def _find_team_of(self, pokemon: Pokemon) -> Optional[str]:
        """查找精灵所属的队伍"""
        if pokemon in self.state.team_a:
            return "a"
        if pokemon in self.state.team_b:
            return "b"
        return None

    def _find_pokemon_by_name(self, name: str) -> Optional[Pokemon]:
        """在所有精灵中按名字查找（用于寄生回复）"""
        for p in self.state.team_a + self.state.team_b:
            if p.name == name:
                return p
        return None

    def _is_on_field(self, pokemon: Pokemon) -> bool:
        """判断精灵是否是当前出战精灵"""
        if pokemon in self.state.team_a:
            return self.state.team_a[self.state.current_a] is pokemon
        if pokemon in self.state.team_b:
            return self.state.team_b[self.state.current_b] is pokemon
        return False

    # ------------------------------------------------------------------
    # 回合结束效果
    # ------------------------------------------------------------------
    def _turn_end_effects(self) -> None:
        """
        回合结束效果，按顺序处理：
        1. 天气效果
        2. 烧伤：-2% × 层数 HP，然后层数减半（向下取整）
        3. 中毒：-3% × 层数 HP（不衰减）
        4. 寄生：被寄生者 -8% HP，寄生者在场则回复等量
        5. 冻结：currentHP < 冻结条(maxHP × 层数/12) 则死亡
        6. 冷却递减
        """

        # --- 1. 天气效果 ---
        if self.state.weather != Weather.NONE and self.state.weather_turns > 0:
            self._apply_weather_effects()
            self.state.weather_turns -= 1
            if self.state.weather_turns <= 0:
                self._log(f"  天气 {self.state.weather.value} 消散了")
                self.state.weather = Weather.NONE

        # --- 2-5. 异常状态处理（所有精灵，包括后备） ---
        all_pokemon = self.state.team_a + self.state.team_b
        for p in all_pokemon:
            if p.is_fainted:
                continue

            # --- 2. 烧伤 ---
            if p.burn_stacks > 0:
                dmg = int(p.hp * 0.02 * p.burn_stacks)
                if dmg > 0:
                    p.take_damage(dmg)
                    self._log(f"  {p.name} 烧伤伤害 {dmg} ({p.burn_stacks}层)")
                # 层数减半（向下取整）
                p.burn_stacks = p.burn_stacks // 2

            if p.is_fainted:
                continue

            # --- 3. 中毒 ---
            if p.poison_stacks > 0:
                dmg = int(p.hp * 0.03 * p.poison_stacks)
                if dmg > 0:
                    p.take_damage(dmg)
                    self._log(f"  {p.name} 中毒伤害 {dmg} ({p.poison_stacks}层)")

            if p.is_fainted:
                continue

            # --- 4. 寄生 ---
            if p.parasited_by is not None:
                dmg = int(p.hp * 0.08)
                if dmg > 0:
                    actual = p.take_damage(dmg)
                    self._log(f"  {p.name} 被寄生 -{actual} HP")

                    # 寄生者在场则回复
                    parasite_owner = self._find_pokemon_by_name(p.parasited_by)
                    if parasite_owner and not parasite_owner.is_fainted:
                        # 检查寄生者是否是当前出战精灵
                        is_on_field = self._is_on_field(parasite_owner)
                        if is_on_field:
                            healed = parasite_owner.heal(actual)
                            self._log(f"  {parasite_owner.name} 寄生回复 +{healed} HP")

            if p.is_fainted:
                continue

            # --- 5. 冻结判定 ---
            if p.freeze_stacks > 0:
                threshold = p.freeze_threshold
                if p.current_hp < threshold:
                    self._log(f"  {p.name} HP({p.current_hp}) < 冻结条({threshold})，冻毙！")
                    p.current_hp = 0
                    p.status = StatusType.FAINTED

        # --- 6. 冷却递减 ---
        for p in all_pokemon:
            expired = []
            for k, v in p.cooldowns.items():
                if v > 0:
                    p.cooldowns[k] = v - 1
                if p.cooldowns[k] <= 0:
                    expired.append(k)
            for k in expired:
                del p.cooldowns[k]
            for k in expired:
                del p.cooldowns[k]

    def _apply_weather_effects(self) -> None:
        """应用天气回合结束效果"""
        weather = self.state.weather

        if weather == Weather.SNOW:
            # 雪天：场上所有未倒下精灵获得 2 层冻结
            for p in self.state.team_a + self.state.team_b:
                if not p.is_fainted:
                    p.freeze_stacks += 2
                    self._log(f"  {p.name} 因雪天获得 2 层冻结 (总计:{p.freeze_stacks})")

        # 沙暴：能耗减半在 _get_effective_energy_cost 中处理
        # 雨天：威力加成在 damage_calc 中处理

    # ------------------------------------------------------------------
    # 自动换人
    # ------------------------------------------------------------------
    def _auto_switch(self) -> None:
        """当前精灵倒下时，自动切换到第一个存活精灵"""
        for team in ("a", "b"):
            team_list = self.state.get_team(team)
            idx = self.state.get_current_idx(team)
            if team_list[idx].is_fainted:
                alive = [i for i, p in enumerate(team_list) if not p.is_fainted]
                if alive:
                    self.state.set_current_idx(team, alive[0])

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        self.log.append(msg)
        if self.verbose:
            print(msg, flush=True)

    # ------------------------------------------------------------------
    # 状态序列化（给 UI 用）
    # ------------------------------------------------------------------
    def get_state_dict(self) -> dict:
        """返回可 JSON 序列化的战斗状态"""
        def pokemon_dict(p: Pokemon, idx: int, is_current: bool) -> dict:
            return {
                "idx": idx,
                "name": p.name,
                "type": p.pokemon_type.value,
                "hp": p.current_hp,
                "max_hp": p.hp,
                "hp_pct": round(p.current_hp / p.hp * 100, 1) if p.hp > 0 else 0,
                "energy": p.energy,
                "is_fainted": p.is_fainted,
                "is_current": is_current,
                "burn": p.burn_stacks,
                "poison": p.poison_stacks,
                "freeze": p.freeze_stacks,
                "freeze_threshold": p.freeze_threshold,
                "parasited_by": p.parasited_by,
                "atk_boost": round(p.atk_boost, 2),
                "def_boost": round(p.def_boost, 2),
                "spatk_boost": round(p.spatk_boost, 2),
                "spdef_boost": round(p.spdef_boost, 2),
                "speed_boost": round(p.speed_boost, 2),
                "skills": [
                    {"name": s.name, "power": s.power, "cost": s.energy_cost,
                     "type": s.skill_type.value, "category": s.category.value}
                    for s in p.skills
                ],
            }

        return {
            "turn": self.state.turn,
            "weather": self.state.weather.value,
            "weather_turns": self.state.weather_turns,
            "winner": self.check_winner(),
            "team_a": [pokemon_dict(p, i, i == self.state.current_a)
                       for i, p in enumerate(self.state.team_a)],
            "team_b": [pokemon_dict(p, i, i == self.state.current_b)
                       for i, p in enumerate(self.state.team_b)],
        }


# ============================================================
# 便捷的模块级函数（兼容旧接口）
# ============================================================
def get_actions(state: BattleState, team: str) -> List[Action]:
    """获取合法动作（无需创建 Engine 实例）"""
    engine = BattleEngine(state)
    return engine.get_actions(team)


def execute_full_turn(state: BattleState, action_a: Action, action_b: Action) -> Optional[str]:
    """执行完整回合（无需创建 Engine 实例）"""
    engine = BattleEngine(state)
    return engine.execute_turn(action_a, action_b)


def check_winner(state: BattleState) -> Optional[str]:
    """检查胜负"""
    engine = BattleEngine(state)
    return engine.check_winner()


def auto_switch(state: BattleState) -> None:
    """自动换人"""
    engine = BattleEngine(state)
    engine._auto_switch()
