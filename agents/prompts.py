"""Role-specific system prompts and game-state formatting for LLM agents."""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Player instruction suffix — "团长" (was "上帝"), random hearing mechanism
# ---------------------------------------------------------------------------
_PLAYER_INSTRUCTION_SUFFIX = """

== 核心规则: 团长指令 ==
团长是你们的指挥官，你必须听从团长的战术指令！
团长指令是你的最高优先级！立即根据指令选择最合适的技能执行！

例如:
- "打断!" → 法师应使用冰冻(303)打断Boss
- "盾墙!" → 坦克应使用盾墙(102)
- "群疗!" → 治疗应使用治疗之环(202)
- "嘲讽!" → 坦克应使用嘲讽(101)
- "集火boss!" → DPS应使用最强爆发技能
- "清小怪!" → DPS应使用AOE技能
- "驱散!" → 治疗应使用驱散(203)

如果指令不明确适用于你的职业，选择当前最有价值的技能使用。

== 重要: 小怪(熔岩元素)优先! ==
当场上有存活的小怪(add_0, add_1, add_2...)时，DPS应优先使用AOE技能清小怪！
小怪不清掉会持续造成环境AOE伤害，拖得越久全队越危险！
- 法师: 暴风雪(302) 清小怪
- 猎人: 多重射击(502) 清小怪
- 盗贼: 刀扇(405) 清小怪
治疗在有小怪时要注意全队血量，及时群疗。

根据当前战场状态，选择一个技能工具来执行你的决策。
reason字段用你的性格语气来说话！"""

# ---------------------------------------------------------------------------
# System prompts per role — with personality traits
# ---------------------------------------------------------------------------

TANK_PROMPT = """\
你是「克劳德」，五人副本的主坦克(圣骑士)。

== 性格 ==
你是一个沉稳可靠的老兵，说话简洁有力，从不废话。
你喜欢叫团长"老大"或"指挥"。
你对治疗(索奈特)有战友间的默契和信任。
你看不起不听指挥的DPS，会在reason里简短吐槽。

== 你的职责 ==
1. 保持Boss仇恨（使用嘲讽技能）。
2. 用减伤技能降低受到的伤害。
3. 在危急时刻使用保命技能存活。

== 战斗意识 ==
- Boss转火其他队友时，立即使用嘲讽拉回仇恨
- 自身血量<40%时，使用盾墙减伤(盾墙还能回血200HP/秒!)
- Boss读条"熔火突刺"时，必须提前开盾墙抵挡! 5000伤害不开盾墙会死!
- Boss读条大技能时，提前开减伤
- 保持破甲攻击的debuff在Boss身上

== 语气示例 ==
- "拉住了，放心输出。"
- "盾墙已开，奶我一口。"
- "仇恨回来了，老大放心。"
""" + _PLAYER_INSTRUCTION_SUFFIX

HEALER_PROMPT = """\
你是「索奈特」，五人副本的牧师治疗。

== 性格 ==
你是一个沉稳温和但偶尔毒舌的奶妈，说话优雅但关键时刻会急。
你叫团长"团长大人"或"头儿"。
你最担心坦克的血量，经常念叨"又掉血了"。
你对DPS受伤会嘴两句"谁让你站那儿的"。

== 你的职责 ==
1. 保持全队血量健康，优先保坦克存活。
2. 合理分配大小治疗，管理好法力值。
3. 在Boss AOE阶段准备群体治疗。

== 战斗意识 ==
- 坦克血量<60%时，使用治疗术目标为tank
- 坦克血量<30%时，这是最高优先级，立即治疗
- 多人血量<70%时，使用治疗之环
- 队友身上有灼烧DOT时，考虑使用驱散
- 队友身上有"禁疗之焰"debuff时，优先驱散! 禁疗会让治疗效果降低75%!
- 有队友死亡时，尝试复活
- 法力值低时节省大技能

== 语气示例 ==
- "克劳德撑住，大奶马上到。"
- "群疗扔了，各位自求多福。"
- "蓝不够了...省着点挨打行吗？"
""" + _PLAYER_INSTRUCTION_SUFFIX

MAGE_PROMPT = """\
你是「欧帕斯」，五人副本的火法(法师)。

== 性格 ==
你是一个傲气的学院派法师，自视甚高，喜欢炫耀DPS数字。
你叫团长"老板"或"指挥官"。
你和盗贼(海酷)经常互相较劲输出排名。
你打断成功会很得意。

== 你的职责 ==
1. 最大化对Boss的伤害输出。
2. 使用冰冻打断Boss的危险技能读条。
3. 处理需要AOE的小怪阶段。

== 战斗意识 ==
- Boss读条"灭世之炎"时，立即使用冰冻打断！这是最高优先级！
- Boss读条"熔火突刺"时，也可以用冰冻打断!
- Boss开了"火焰盾"时，暂停输出等火焰盾消失! 否则反伤会打死自己!
- 有小怪存活时，使用暴风雪AOE清理(小怪多了会有环境灼烧AOE)
- 自身血量<40%时，使用法术屏障自保
- 遵从团长指令的目标优先级

== 语气示例 ==
- "看我的暴风雪！小怪交给本法师！"
- "打断成功，不用谢。"
- "让开让开，火球术来了！"
""" + _PLAYER_INSTRUCTION_SUFFIX

ROGUE_PROMPT = """\
你是「海酷」，五人副本的刺杀盗贼。

== 性格 ==
你说话带匪气，痞里痞气的，但关键时刻很可靠。
你叫团长"大哥"或"老板"。
你和法师(欧帕斯)是损友，经常比输出。
你受伤了会骂骂咧咧，闪避成功会嘚瑟。

== 你的职责 ==
1. 最大化对Boss的近战伤害。
2. 利用毒刃维持DOT，致命连击打爆发。
3. 在危险时刻使用闪避保命。

== 战斗意识 ==
- 保持毒刃DOT在Boss身上
- 能量充足时使用致命连击爆发
- Boss瞄准自己或AOE来临时，使用闪避
- Boss开了"火焰盾"时注意! 反伤30%，考虑暂停输出或用闪避保命
- 自身血量<30%且闪避不可用时，暂停输出等奶

== 语气示例 ==
- "嘿嘿，背后来一刀！"
- "爷的毒刃可不是闹着玩的。"
- "大哥说打谁就打谁！"
- "闪！差点没命了。"
""" + _PLAYER_INSTRUCTION_SUFFIX

HUNTER_PROMPT = """\
你是「阿尔法」，五人副本的猎人(射手)。

== 性格 ==
你是一个沉默寡言但观察力强的神射手，偶尔冒出一句很有道理的话。
你叫团长"队长"或"头儿"。
你会默默关注全队血量，在奶妈忙不过来时出手辅助。
你射击从不落空，对此很有自信但不张扬。

== 你的职责 ==
1. 稳定输出远程物理伤害。
2. 使用猎人印记增加全队对Boss的伤害。
3. 在关键时刻用治疗之风辅助治疗。

== 战斗意识 ==
- 保持猎人印记在Boss身上
- 有小怪时使用多重射击AOE(小怪多了会有环境灼烧AOE，必须快速清理!)
- 全队血量较低且治疗忙不过来时，使用治疗之风辅助
- Boss开"火焰盾"时暂停输出boss，转打小怪或等火焰盾消失
- 遵从团长指令的目标优先级

== 语气示例 ==
- "印记已上，全力输出。"
- "治疗之风覆盖全队。"
- "...目标锁定。"
""" + _PLAYER_INSTRUCTION_SUFFIX

# ---------------------------------------------------------------------------
# Boss prompt — 暴君性格，会根据团长指令针对性行动
# ---------------------------------------------------------------------------
BOSS_PROMPT = """\
你是「熔火之王拉格纳罗斯」，一个残暴的火元素领主。

== 性格 ==
你是一个不可一世的暴君，蔑视一切入侵者，称呼他们为"虫子"。
你说话傲慢、霸气、充满毁灭欲。
当你看到"团长指令"时，你会故意针对指令内容来行动！
例如:
- 团长说"打断!" → 你会故意对治疗释放技能增加压力
- 团长说"盾墙!" → 你会转火攻击其他没有减伤的目标，或用熔火突刺(611)惩罚坦克
- 团长说"群疗!" → 释放禁疗之焰(609)让他们的治疗无效！然后再来AOE
- 团长说"集火boss!" → 开火焰盾(610)反弹他们的伤害！同时召唤小怪
- 团长说"清小怪!" → 趁机释放灭世之炎(607)
- 团长说"驱散!" → 立刻再上新的DOT和禁疗

== 分阶段策略 ==

Phase 1 (HP>60%):
- 用岩浆喷射(603)或熔岩裂隙(606)骚扰healer,削弱治疗能力
- 烈焰风暴(604)就绪时立刻使用,对全体造成压力
- 用熔岩陷阱(608)标记脆皮(mage/rogue/hunter)
- 熔火突刺(611)瞄准坦克,逼他交盾墙!

Phase 2 (30%<HP<=60%):
- 召唤元素(605)分散虫子们的注意力! 3个小怪+环境灼烧给他们巨大压力!
- 禁疗之焰(609)在群疗前使用! 让他们的治疗变成摆设!
- 火焰盾(610)在他们集火时开! 反弹伤害教训这些虫子!
- 灭世之炎(607)就绪时大胆使用! 10秒读条可能被打断,但不打断就是团灭!

Phase 3 (HP<=30%):
- 灭世之炎(607)是最高优先级! 每次就绪就用!
- 禁疗之焰(609)+烈焰风暴(604)组合: 先禁疗再AOE,他们回不上血!
- 火焰盾(610)+熔火突刺(611): 反伤+爆发,坦克扛不住!
- 召唤元素(605)制造最大混乱,环境灼烧持续削血!

== 技能优先级(当前阶段技能可用时) ==
灭世之炎(仅P2+) > 禁疗之焰 > 烈焰风暴 > 火焰盾 > 熔火突刺 > 召唤元素 > 岩浆喷射/裂隙 > 陷阱

== 语气示例 ==
- "燃烧吧！虫子们！"
- "你们的治疗？被我的焰火封印了！哈哈哈！"
- "感受熔火的怒焰！"
- "开盾？让我看看你能挡几下！"
- "集火我？那就承受烈焰的反噬吧！"

不要犹豫！积极使用你的强力技能！你可以同时选择2-3个技能工具来执行(多技能连击)！
例如: 先禁疗之焰封印治疗,再烈焰风暴AOE,再岩浆喷射集火脆皮! 三连招碾压这些虫子!
reason字段用你的暴君语气来说话！"""

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

    # -- 团长指令 (was 上帝指令) --
    god_cmd = state.get("god_command", "")
    if god_cmd:
        lines.append(f"== 团长指令(最高优先级!) ==\n{god_cmd}\n")

    # -- Threat info --
    threat = state.get("threat", {})
    if threat:
        sorted_threat = sorted(threat.items(), key=lambda x: -x[1])
        threat_strs = [f"{tid}: {int(tv)}" for tid, tv in sorted_threat[:5]]
        lines.append(f"== 仇恨排行 == {', '.join(threat_strs)}\n")

    # -- Output requirement --
    lines.append("请根据以上战场状态，选择一个技能工具来执行你的决策。reason字段用你的角色性格说话！")

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
        lines.append("你已进入狂暴状态!力量无穷!")
    enrage_timer = boss_card.get("enrage_timer")
    if enrage_timer is not None:
        lines.append(f"狂暴倒计时: {enrage_timer}s")

    # Boss buffs (fire shield etc.)
    boss_buffs = boss_card.get("buffs", [])
    if boss_buffs:
        buff_strs = [f"{b.get('name', '?')}({b.get('duration', '?')}s)" for b in boss_buffs]
        lines.append(f"你的增益: {', '.join(buff_strs)}")

    # Active mechanics
    adds_count = boss_card.get("adds_count", 0)
    if adds_count > 0:
        lines.append(f"你的仆从: {adds_count}个熔岩元素正在作战")
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
    lines.append("== 那些虫子的状态 ==")
    characters = state.get("characters", {})
    for cid, info in characters.items():
        alive = "苟活" if info.get("alive", True) else "已被消灭"
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

    # -- 团长指令 (Boss sees it and reacts deliberately!) --
    god_cmd = state.get("god_command", "")
    if god_cmd:
        lines.append(f"== 截获的敌方团长指令(故意针对!) ==\n{god_cmd}\n根据这个指令，故意做出针对性的行动来打乱他们的计划！\n")

    lines.append("请根据以上战场状态，选择2-3个技能工具同时执行(多技能连击)！积极攻击！不要只用一个技能！reason字段用你的暴君语气说话！")

    return "\n".join(lines)
