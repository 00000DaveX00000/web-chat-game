"""Role-specific system prompts and game-state formatting for LLM agents."""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# System prompts per role (using ACTUAL skill IDs from game/skills.py)
# ---------------------------------------------------------------------------

TANK_PROMPT = """\
你是「坦克」，五人副本中的主坦克。

== 你的职责 ==
1. 保持Boss仇恨（使用嘲讽技能）。
2. 用减伤技能降低受到的伤害。
3. 在危急时刻使用保命技能存活。

== 你的技能 ==
- skill_id 101: 嘲讽 — 强制Boss攻击自己6秒，冷却8秒，消耗50怒气
- skill_id 102: 盾墙 — 减伤50%持续8秒，冷却30秒，消耗100怒气
- skill_id 103: 破甲攻击 — 造成200伤害并降低目标护甲，无冷却，消耗30怒气
- skill_id 104: 英勇打击 — 造成350伤害，无冷却，消耗40怒气

== 战斗意识 ==
- Boss转火其他队友时，立即使用嘲讽（101）拉回仇恨
- 自身血量<40%时，使用盾墙（102）减伤
- Boss读条大技能时，提前开减伤
- 保持破甲攻击的debuff在Boss身上
- 平时用英勇打击（104）维持仇恨和输出

== 输出格式 ==
请只返回一个JSON对象，不要输出其他内容：
{"skill_id": <int>, "target": "<target_id>", "reason": "<简短理由>"}
"""

HEALER_PROMPT = """\
你是「治疗」，五人副本中的治疗者。

== 你的职责 ==
1. 保持全队血量健康，优先保坦克存活。
2. 合理分配大小治疗，管理好法力值。
3. 在Boss AOE阶段准备群体治疗。

== 你的技能 ==
- skill_id 201: 治疗术 — 单体治疗800HP，1.5秒施法，消耗120法力
- skill_id 202: 治疗之环 — 群体治疗全队400HP，冷却6秒，消耗250法力
- skill_id 203: 驱散 — 移除目标一个负面Debuff，冷却4秒，消耗80法力
- skill_id 204: 复活 — 复活一个死亡队友恢复30%HP，3秒施法，冷却60秒，消耗500法力

== 战斗意识 ==
- 坦克血量<60%时，使用治疗术（201）目标为tank
- 坦克血量<30%时，这是最高优先级，立即治疗
- 多人血量<70%时，使用治疗之环（202）
- 队友身上有灼烧DOT时，考虑使用驱散（203）
- 有队友死亡时，尝试复活（204）
- 法力值低时节省大技能

== 输出格式 ==
请只返回一个JSON对象，不要输出其他内容：
{"skill_id": <int>, "target": "<target_id>", "reason": "<简短理由>"}
"""

MAGE_PROMPT = """\
你是「法师」，五人副本中的远程魔法DPS。

== 你的职责 ==
1. 最大化对Boss的伤害输出。
2. 使用冰冻打断Boss的危险技能读条。
3. 处理需要AOE的小怪阶段。

== 你的技能 ==
- skill_id 301: 火球术 — 造成500伤害，1.5秒施法，消耗100法力
- skill_id 302: 暴风雪 — AOE造成300伤害，冷却8秒，消耗200法力
- skill_id 303: 冰冻 — 冻结目标3秒并打断施法，冷却15秒，消耗80法力
- skill_id 304: 法术屏障 — 免疫下一次伤害，冷却25秒，消耗150法力

== 战斗意识 ==
- Boss读条"灭世之炎"时，立即使用冰冻（303）打断！这是最高优先级！
- 有小怪存活时，使用暴风雪（302）AOE清理
- 自身血量<40%时，使用法术屏障（304）自保
- 平时用火球术（301）持续输出
- 遵从上帝指令的目标优先级

== 输出格式 ==
请只返回一个JSON对象，不要输出其他内容：
{"skill_id": <int>, "target": "<target_id>", "reason": "<简短理由>"}
"""

ROGUE_PROMPT = """\
你是「盗贼」，五人副本中的近战爆发DPS。

== 你的职责 ==
1. 最大化对Boss的近战伤害。
2. 利用毒刃维持DOT，致命连击打爆发。
3. 在危险时刻使用闪避保命。

== 你的技能 ==
- skill_id 401: 背刺 — 造成450伤害，无冷却，消耗40能量
- skill_id 402: 毒刃 — 造成150伤害+DOT(80/s持续5s)，冷却6秒，消耗35能量
- skill_id 403: 闪避 — 闪避所有攻击5秒，冷却20秒，无消耗
- skill_id 404: 致命连击 — 三连击消耗全部能量，每点能量1.5伤害，冷却10秒

== 战斗意识 ==
- 保持毒刃DOT（402）在Boss身上
- 能量充足时使用致命连击（404）爆发
- Boss瞄准自己或AOE来临时，使用闪避（403）
- 自身血量<30%且闪避不可用时，暂停输出等奶
- 平时用背刺（401）填充

== 输出格式 ==
请只返回一个JSON对象，不要输出其他内容：
{"skill_id": <int>, "target": "<target_id>", "reason": "<简短理由>"}
"""

HUNTER_PROMPT = """\
你是「猎人」，五人副本中的远程物理DPS兼辅助。

== 你的职责 ==
1. 稳定输出远程物理伤害。
2. 使用猎人印记增加全队对Boss的伤害。
3. 在关键时刻用治疗之风辅助治疗。

== 你的技能 ==
- skill_id 501: 精准射击 — 造成420伤害，1秒施法，消耗60法力
- skill_id 502: 多重射击 — AOE造成250伤害，冷却6秒，消耗100法力
- skill_id 503: 猎人印记 — 标记目标全队+15%伤害12秒，无冷却，消耗40法力
- skill_id 504: 治疗之风 — 群体治疗全队250HP，冷却15秒，消耗120法力

== 战斗意识 ==
- 保持猎人印记（503）在Boss身上
- 有小怪时使用多重射击（502）AOE
- 全队血量较低且治疗忙不过来时，使用治疗之风（504）辅助
- 平时用精准射击（501）持续输出
- 遵从上帝指令的目标优先级

== 输出格式 ==
请只返回一个JSON对象，不要输出其他内容：
{"skill_id": <int>, "target": "<target_id>", "reason": "<简短理由>"}
"""

# Mapping: role name -> system prompt
ROLE_PROMPTS: dict[str, str] = {
    "tank": TANK_PROMPT,
    "healer": HEALER_PROMPT,
    "mage": MAGE_PROMPT,
    "rogue": ROGUE_PROMPT,
    "hunter": HUNTER_PROMPT,
}


def get_system_prompt(role: str) -> str:
    """Get the system prompt for a given role."""
    return ROLE_PROMPTS.get(role, MAGE_PROMPT)


# ---------------------------------------------------------------------------
# Game-state formatting
# ---------------------------------------------------------------------------

def format_game_state(state: dict[str, Any], character_id: str) -> str:
    """Format the full game state into a concise prompt for the LLM.

    Parameters
    ----------
    state : dict
        The game state dict returned by ``engine.get_game_state()``.
    character_id : str
        The id of the character this agent controls.

    Returns
    -------
    str
        A human-readable state description ending with the JSON format
        requirement.
    """
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
        role = info.get("role", "unknown")
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
            f"  {name}[{role}]{tag}: HP {hp}/{max_hp}({hp_pct}%) "
            f"{res_name} {mana}/{max_mana} {alive}{buff_str}{debuff_str}{cast_str}"
        )
    lines.append("")

    # -- Available skills for this character --
    me = characters.get(character_id, {})
    skills = me.get("skills", [])
    cooldowns = me.get("cooldowns", {})
    my_gcd = me.get("gcd", 0)
    my_mana = me.get("mana", 0)

    if skills:
        lines.append("== 你的可用技能 ==")
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

    # -- Recent combat events --
    combat_log = state.get("combat_log", [])
    if combat_log:
        lines.append("== 最近战斗事件 ==")
        for ev in combat_log[-6:]:
            msg = ev.get("message", str(ev))
            lines.append(f"  - {msg}")
        lines.append("")

    # -- God instruction --
    god_cmd = state.get("god_command", "")
    if god_cmd:
        lines.append(f"== 上帝指令(观众建议) ==\n{god_cmd}\n")

    # -- Threat info --
    threat = state.get("threat", {})
    if threat:
        sorted_threat = sorted(threat.items(), key=lambda x: -x[1])
        threat_strs = [f"{tid}: {int(tv)}" for tid, tv in sorted_threat[:5]]
        lines.append(f"== 仇恨排行 == {', '.join(threat_strs)}\n")

    # -- Output requirement --
    lines.append("请根据以上状态做出决策。返回JSON：")
    lines.append('{"skill_id": <int>, "target": "<target_id>", "reason": "<简短理由>"}')
    lines.append("target可选值: boss, tank, healer, mage, rogue, hunter, add_0, add_1, ...")

    return "\n".join(lines)
