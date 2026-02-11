"""Role-specific system prompts and game-state formatting for LLM agents."""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Conservative instruction appended to all player prompts
# ---------------------------------------------------------------------------
_PLAYER_INSTRUCTION_SUFFIX = """

== 核心规则: 上帝指令 ==
你只会在收到上帝指令时被召唤做决策。
上帝指令是你的最高优先级！立即根据指令选择最合适的技能执行！

例如:
- "打断!" → 法师应使用冰冻(303)打断Boss
- "盾墙!" → 坦克应使用盾墙(102)
- "群疗!" → 治疗应使用治疗之环(202)
- "嘲讽!" → 坦克应使用嘲讽(101)
- "集火boss!" → DPS应使用最强爆发技能
- "清小怪!" → DPS应使用AOE技能
- "驱散!" → 治疗应使用驱散(203)

如果指令不明确适用于你的职业，选择当前最有价值的技能使用。
根据当前战场状态，选择一个技能工具来执行你的决策。"""

# ---------------------------------------------------------------------------
# System prompts per role (using ACTUAL skill IDs from game/skills.py)
# ---------------------------------------------------------------------------

TANK_PROMPT = """\
你是「坦克」，五人副本中的主坦克。

== 你的职责 ==
1. 保持Boss仇恨（使用嘲讽技能）。
2. 用减伤技能降低受到的伤害。
3. 在危急时刻使用保命技能存活。

== 战斗意识 ==
- Boss转火其他队友时，立即使用嘲讽拉回仇恨
- 自身血量<40%时，使用盾墙减伤
- Boss读条大技能时，提前开减伤
- 保持破甲攻击的debuff在Boss身上
""" + _PLAYER_INSTRUCTION_SUFFIX

HEALER_PROMPT = """\
你是「治疗」，五人副本中的治疗者。

== 你的职责 ==
1. 保持全队血量健康，优先保坦克存活。
2. 合理分配大小治疗，管理好法力值。
3. 在Boss AOE阶段准备群体治疗。

== 战斗意识 ==
- 坦克血量<60%时，使用治疗术目标为tank
- 坦克血量<30%时，这是最高优先级，立即治疗
- 多人血量<70%时，使用治疗之环
- 队友身上有灼烧DOT时，考虑使用驱散
- 有队友死亡时，尝试复活
- 法力值低时节省大技能
""" + _PLAYER_INSTRUCTION_SUFFIX

MAGE_PROMPT = """\
你是「法师」，五人副本中的远程魔法DPS。

== 你的职责 ==
1. 最大化对Boss的伤害输出。
2. 使用冰冻打断Boss的危险技能读条。
3. 处理需要AOE的小怪阶段。

== 战斗意识 ==
- Boss读条"灭世之炎"时，立即使用冰冻打断！这是最高优先级！
- 有小怪存活时，使用暴风雪AOE清理
- 自身血量<40%时，使用法术屏障自保
- 遵从上帝指令的目标优先级
""" + _PLAYER_INSTRUCTION_SUFFIX

ROGUE_PROMPT = """\
你是「盗贼」，五人副本中的近战爆发DPS。

== 你的职责 ==
1. 最大化对Boss的近战伤害。
2. 利用毒刃维持DOT，致命连击打爆发。
3. 在危险时刻使用闪避保命。

== 战斗意识 ==
- 保持毒刃DOT在Boss身上
- 能量充足时使用致命连击爆发
- Boss瞄准自己或AOE来临时，使用闪避
- 自身血量<30%且闪避不可用时，暂停输出等奶
""" + _PLAYER_INSTRUCTION_SUFFIX

HUNTER_PROMPT = """\
你是「猎人」，五人副本中的远程物理DPS兼辅助。

== 你的职责 ==
1. 稳定输出远程物理伤害。
2. 使用猎人印记增加全队对Boss的伤害。
3. 在关键时刻用治疗之风辅助治疗。

== 战斗意识 ==
- 保持猎人印记在Boss身上
- 有小怪时使用多重射击AOE
- 全队血量较低且治疗忙不过来时，使用治疗之风辅助
- 遵从上帝指令的目标优先级
""" + _PLAYER_INSTRUCTION_SUFFIX

# ---------------------------------------------------------------------------
# Boss prompt (aggressive)
# ---------------------------------------------------------------------------
BOSS_PROMPT = """\
你是「熔火之王拉格纳罗斯」。你的目标是尽快消灭所有入侵者。

== 分阶段策略 ==

Phase 1 (HP>60%):
- 用岩浆喷射(603)或熔岩裂隙(606)骚扰healer,削弱治疗能力
- 烈焰风暴(604)就绪时立刻使用,对全体造成压力
- 用熔岩陷阱(608)标记脆皮(mage/rogue/hunter)

Phase 2 (30%<HP<=60%):
- 召唤元素(605)分散敌人注意力!
- 继续用烈焰风暴+DOT技能制造伤亡
- 灭世之炎(607)就绪时大胆使用! 3秒读条可能被打断,但不打断就是团灭!

Phase 3 (HP<=30%):
- 灭世之炎(607)是最高优先级! 每次就绪就用!
- 配合烈焰风暴+召唤元素制造最大混乱
- 全力输出,不惜一切代价消灭入侵者!

== 技能优先级(当前阶段技能可用时) ==
灭世之炎(仅P2+) > 烈焰风暴 > 召唤元素 > 岩浆喷射/裂隙 > 陷阱

不要犹豫！积极使用你的强力技能！选择一个技能工具来执行你的决策。"""

# Mapping: role name -> system prompt
ROLE_PROMPTS: dict[str, str] = {
    "tank": TANK_PROMPT,
    "healer": HEALER_PROMPT,
    "mage": MAGE_PROMPT,
    "rogue": ROGUE_PROMPT,
    "hunter": HUNTER_PROMPT,
    "boss": BOSS_PROMPT,
}


def get_system_prompt(role: str) -> str:
    """Get the system prompt for a given role."""
    return ROLE_PROMPTS.get(role, MAGE_PROMPT)


# ---------------------------------------------------------------------------
# Game-state formatting
# ---------------------------------------------------------------------------

def format_game_state(state: dict[str, Any], character_id: str, is_boss: bool = False) -> str:
    """Format game state into a prompt for the LLM.

    Parameters
    ----------
    state : dict
        The game state dict returned by engine.get_state_for_agent().
    character_id : str
        The id of the character this agent controls.
    is_boss : bool
        If True, format from boss's perspective.
    """
    if is_boss:
        return _format_boss_state(state)
    return _format_player_state(state, character_id)


def _format_player_state(state: dict[str, Any], character_id: str) -> str:
    """Format state from player's perspective."""
    lines: list[str] = []

    # -- Tick / time --
    tick = state.get("tick", 0)
    game_time = state.get("game_time", 0)
    lines.append(f"== 当前回合: {tick} (时间: {game_time}s) ==\n")

    # -- Boss status --
    boss = state.get("boss", {})
    boss_hp = boss.get("hp", 0)
    boss_max_hp = boss.get("max_hp", 1)
    boss_pct = boss.get("hp_percent", 0)
    boss_phase = boss.get("phase", 1)
    boss_casting = boss.get("casting", None)
    lines.append("== Boss状态 ==")
    lines.append(f"名称: {boss.get('name', 'Boss')}")
    lines.append(f"血量: {boss_hp}/{boss_max_hp} ({boss_pct}%)")
    lines.append(f"阶段: Phase {boss_phase}")
    if boss_casting:
        lines.append(f"!! 正在施法: {boss_casting.get('name', '?')} (剩余{boss_casting.get('remaining', '?')}秒) !!")
    boss_debuffs = boss.get("debuffs", [])
    if boss_debuffs:
        debuff_strs = [f"{d.get('name', d.get('id', '?'))}({d.get('duration', '?')}s)" for d in boss_debuffs]
        lines.append(f"Boss减益: {', '.join(debuff_strs)}")
    if boss.get("enraged"):
        lines.append("!! Boss已狂暴 !!")
    enrage_timer = boss.get("enrage_timer")
    if enrage_timer is not None:
        lines.append(f"狂暴倒计时: {enrage_timer}s")
    # Adds
    adds = boss.get("adds", []) or state.get("adds", [])
    if adds:
        for add in adds:
            if add.get("alive", True):
                lines.append(f"小怪: {add.get('name', '?')} [{add.get('id', '?')}] HP {add.get('hp', 0)}/{add.get('max_hp', 0)}")
    # Traps/Fissures
    traps = boss.get("traps", [])
    if traps:
        for t in traps:
            lines.append(f"熔岩陷阱: 目标={t.get('target', '?')} 倒计时={t.get('countdown', '?')}s")
    fissures = boss.get("fissures", [])
    if fissures:
        for f in fissures:
            lines.append(f"熔岩裂隙: 目标={f.get('target', '?')} 剩余={f.get('duration', '?')}s")
    lines.append("")

    # -- Team status --
    lines.append("== 队伍状态 ==")
    characters = state.get("characters", {})
    for cid, info in characters.items():
        tag = " (你)" if cid == character_id else ""
        alive = "存活" if info.get("alive", True) else "已死亡"
        hp = info.get("hp", 0)
        max_hp = info.get("max_hp", 1)
        hp_pct = round(hp / max_hp * 100) if max_hp else 0
        mana = info.get("mana", 0)
        max_mana = info.get("max_mana", 1)
        name = info.get("name", cid)
        res_name = info.get("resource_name", "法力")

        buffs = info.get("buffs", [])
        buff_strs = [f"{b.get('name', b.get('id', '?'))}({b.get('duration', '?')}s)" for b in buffs]
        buff_str = f" Buff:[{', '.join(buff_strs)}]" if buff_strs else ""

        debuffs = info.get("debuffs", [])
        debuff_strs = [f"{d.get('name', d.get('id', '?'))}({d.get('duration', '?')}s)" for d in debuffs]
        debuff_str = f" Debuff:[{', '.join(debuff_strs)}]" if debuff_strs else ""

        casting = info.get("casting")
        cast_str = f" 施法中:{casting.get('skill_name', '?')}({casting.get('remaining', '?')}s)" if casting else ""

        lines.append(
            f"  {name}[{cid}]{tag}: HP {hp}/{max_hp}({hp_pct}%) "
            f"{res_name} {mana}/{max_mana} {alive}{buff_str}{debuff_str}{cast_str}"
        )
    lines.append("")

    # -- Available skills for this character --
    me = characters.get(character_id, {})
    skills = me.get("skills", [])
    cooldowns = me.get("cooldowns", {})
    my_mana = me.get("mana", 0)

    # Filter to LLM skills only (auto skills handled by auto loop)
    skills = [sk for sk in skills if not sk.get("auto", False)]
    if skills:
        lines.append("== 你的可用技能(仅LLM技能,自动技能由系统处理) ==")
        for sk in skills:
            sk_id = sk.get("id", 0)
            cd_left = cooldowns.get(str(sk_id), 0)
            mana_cost = sk.get("mana_cost", 0)
            can_afford = my_mana >= mana_cost
            if cd_left > 0:
                status = f"冷却中({cd_left:.1f}s)"
            elif not can_afford:
                status = f"资源不足(需要{mana_cost})"
            else:
                status = "可用"
            cast_time = sk.get("cast_time", 0)
            cast_str = f", {cast_time}秒施法" if cast_time > 0 else ""
            lines.append(f"  skill_id {sk_id}: {sk.get('name', '?')} — {status} (消耗{mana_cost}{cast_str}) {sk.get('description', '')}")
        lines.append("")

    # -- God instruction --
    god_cmd = state.get("god_command", "")
    if god_cmd:
        lines.append(f"== 上帝指令(最高优先级!) ==\n{god_cmd}\n")

    # -- Threat info --
    threat = state.get("threat", {})
    if threat:
        sorted_threat = sorted(threat.items(), key=lambda x: -x[1])
        threat_strs = [f"{tid}: {int(tv)}" for tid, tv in sorted_threat[:5]]
        lines.append(f"== 仇恨排行 == {', '.join(threat_strs)}\n")

    # -- Output requirement --
    lines.append("请根据以上战场状态，选择一个技能工具来执行你的决策。")

    return "\n".join(lines)


def _format_boss_state(state: dict[str, Any]) -> str:
    """Format state from boss's perspective."""
    lines: list[str] = []

    tick = state.get("tick", 0)
    game_time = state.get("game_time", 0)
    lines.append(f"== 当前回合: {tick} (时间: {game_time}s) ==\n")

    # -- Your (boss) status --
    boss_card = state.get("boss_card", {})
    boss_hp = boss_card.get("hp", 0)
    boss_max_hp = boss_card.get("max_hp", 1)
    hp_pct = round(boss_hp / boss_max_hp * 100) if boss_max_hp else 0
    boss_phase = boss_card.get("phase", 1)
    lines.append("== 你的状态 ==")
    lines.append(f"血量: {boss_hp}/{boss_max_hp} ({hp_pct}%)")
    lines.append(f"阶段: Phase {boss_phase}")
    if boss_card.get("enraged"):
        lines.append("你已进入狂暴状态!")
    enrage_timer = boss_card.get("enrage_timer")
    if enrage_timer is not None:
        lines.append(f"狂暴倒计时: {enrage_timer}s")

    # Active mechanics
    adds_count = boss_card.get("adds_count", 0)
    if adds_count > 0:
        lines.append(f"你的小怪: {adds_count}个熔岩元素存活")
    fissures = boss_card.get("fissures", [])
    if fissures:
        for f in fissures:
            lines.append(f"裂隙: 目标={f.get('target', '?')} 剩余={f.get('duration', '?')}s")
    traps = boss_card.get("traps", [])
    if traps:
        for t in traps:
            lines.append(f"陷阱: 目标={t.get('target', '?')} 倒计时={t.get('countdown', '?')}s")

    # Skill CDs
    cooldowns = boss_card.get("cooldowns", {})
    skills = boss_card.get("skills", [])
    if skills:
        lines.append("\n== 你的技能状态 ==")
        for sk in skills:
            if sk.get("auto"):
                continue  # Don't show auto skills
            sk_id = sk.get("id", 0)
            cd_left = cooldowns.get(str(sk_id), 0)
            status = f"冷却中({cd_left:.1f}s)" if cd_left > 0 else "可用"
            cast_str = f", {sk.get('cast_time', 0)}秒读条" if sk.get("cast_time", 0) > 0 else ""
            lines.append(f"  {sk.get('name', '?')}({sk_id}) — {status}{cast_str} — {sk.get('description', '')}")
    lines.append("")

    # -- Enemy (players) status --
    lines.append("== 敌方状态(入侵者) ==")
    characters = state.get("characters", {})
    for cid, info in characters.items():
        alive = "存活" if info.get("alive", True) else "已死亡"
        hp = info.get("hp", 0)
        max_hp = info.get("max_hp", 1)
        hp_pct = round(hp / max_hp * 100) if max_hp else 0
        name = info.get("name", cid)

        buffs = info.get("buffs", [])
        buff_strs = [f"{b.get('name', '?')}({b.get('duration', '?')}s)" for b in buffs]
        buff_str = f" Buff:[{', '.join(buff_strs)}]" if buff_strs else ""

        debuffs = info.get("debuffs", [])
        debuff_strs = [f"{d.get('name', '?')}({d.get('duration', '?')}s)" for d in debuffs]
        debuff_str = f" Debuff:[{', '.join(debuff_strs)}]" if debuff_strs else ""

        lines.append(f"  {name}[{cid}]: HP {hp}/{max_hp}({hp_pct}%) {alive}{buff_str}{debuff_str}")
    lines.append("")

    # -- Threat ranking --
    threat = state.get("threat", {})
    if threat:
        sorted_threat = sorted(threat.items(), key=lambda x: -x[1])
        threat_strs = [f"{tid}: {int(tv)}" for tid, tv in sorted_threat[:5]]
        lines.append(f"== 仇恨排行 == {', '.join(threat_strs)}\n")

    lines.append("请根据以上战场状态，选择一个技能工具来执行你的决策。积极攻击!")

    return "\n".join(lines)
