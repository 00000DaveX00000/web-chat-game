"""Skill data definitions for all character classes and Boss."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillDef:
    id: int
    name: str
    role: str  # tank / healer / mage / rogue / hunter / boss
    cooldown: float  # seconds
    mana_cost: int
    cast_time: float  # 0 = instant
    target_type: str  # "enemy" | "self" | "ally" | "ally_all" | "enemy_all"
    description: str = ""
    # effect parameters stored as a flat dict
    effects: dict[str, Any] = field(default_factory=dict)
    # auto skills are cast by the auto loop, not LLM
    auto: bool = False


# ---------------------------------------------------------------------------
# Tank skills
# ---------------------------------------------------------------------------
TAUNT = SkillDef(
    id=101,
    name="嘲讽",
    role="tank",
    cooldown=8,
    mana_cost=50,
    cast_time=0,
    target_type="enemy",
    description="强制Boss攻击自己6秒",
    effects={"type": "taunt", "duration": 6},
)

SHIELD_WALL = SkillDef(
    id=102,
    name="盾墙",
    role="tank",
    cooldown=30,
    mana_cost=100,
    cast_time=0,
    target_type="self",
    description="减伤50%持续8秒,并回复200HP/秒",
    effects={"type": "buff", "buff_id": "shield_wall", "duration": 8, "damage_reduction": 0.5, "hot_per_second": 200},
)

SUNDER_ARMOR = SkillDef(
    id=103,
    name="破甲攻击",
    role="tank",
    cooldown=0,
    mana_cost=30,
    cast_time=0,
    target_type="enemy",
    description="造成200伤害并降低目标护甲",
    effects={"type": "damage", "base_damage": 200, "debuff_id": "sunder_armor", "duration": 10, "armor_reduction": 0.1},
)

HEROIC_STRIKE = SkillDef(
    id=104,
    name="英勇打击",
    role="tank",
    cooldown=0,
    mana_cost=40,
    cast_time=0,
    target_type="enemy",
    description="造成350伤害",
    effects={"type": "damage", "base_damage": 350},
    auto=True,
)

# ---------------------------------------------------------------------------
# Healer skills
# ---------------------------------------------------------------------------
HEAL = SkillDef(
    id=201,
    name="治疗术",
    role="healer",
    cooldown=0,
    mana_cost=120,
    cast_time=1.5,
    target_type="ally",
    description="单体治疗800HP",
    effects={"type": "heal", "base_heal": 800},
    auto=True,
)

CIRCLE_OF_HEAL = SkillDef(
    id=202,
    name="治疗之环",
    role="healer",
    cooldown=4,
    mana_cost=250,
    cast_time=0,
    target_type="ally_all",
    description="群体治疗全队400HP",
    effects={"type": "heal_aoe", "base_heal": 400},
)

DISPEL = SkillDef(
    id=203,
    name="驱散",
    role="healer",
    cooldown=2,
    mana_cost=80,
    cast_time=0,
    target_type="ally",
    description="移除目标一个负面Debuff",
    effects={"type": "dispel"},
)

RESURRECT = SkillDef(
    id=204,
    name="复活",
    role="healer",
    cooldown=60,
    mana_cost=500,
    cast_time=4.0,
    target_type="ally",
    description="复活一个死亡队友,恢复30%HP",
    effects={"type": "resurrect", "hp_percent": 0.3},
)

# ---------------------------------------------------------------------------
# Mage skills
# ---------------------------------------------------------------------------
FIREBALL = SkillDef(
    id=301,
    name="火球术",
    role="mage",
    cooldown=0,
    mana_cost=100,
    cast_time=2.0,
    target_type="enemy",
    description="造成500伤害",
    effects={"type": "damage", "base_damage": 500},
    auto=True,
)

BLIZZARD = SkillDef(
    id=302,
    name="暴风雪",
    role="mage",
    cooldown=5,
    mana_cost=200,
    cast_time=0,
    target_type="enemy_all",
    description="AOE造成300伤害",
    effects={"type": "damage_aoe", "base_damage": 300},
)

FROST_NOVA = SkillDef(
    id=303,
    name="冰冻",
    role="mage",
    cooldown=15,
    mana_cost=80,
    cast_time=0,
    target_type="enemy",
    description="冻结目标3秒(打断施法)",
    effects={"type": "control", "control_type": "freeze", "duration": 3},
)

SPELL_BARRIER = SkillDef(
    id=304,
    name="法术屏障",
    role="mage",
    cooldown=25,
    mana_cost=150,
    cast_time=0,
    target_type="self",
    description="免疫下一次伤害",
    effects={"type": "buff", "buff_id": "spell_barrier", "charges": 1},
)

# ---------------------------------------------------------------------------
# Rogue skills
# ---------------------------------------------------------------------------
BACKSTAB = SkillDef(
    id=401,
    name="背刺",
    role="rogue",
    cooldown=0,
    mana_cost=40,
    cast_time=0,
    target_type="enemy",
    description="造成450伤害",
    effects={"type": "damage", "base_damage": 450},
    auto=True,
)

POISON_BLADE = SkillDef(
    id=402,
    name="毒刃",
    role="rogue",
    cooldown=6,
    mana_cost=35,
    cast_time=0,
    target_type="enemy",
    description="造成150伤害并附加DOT(80/s持续5s)",
    effects={"type": "damage", "base_damage": 150, "dot": True, "dot_id": "poison", "dot_damage": 80, "dot_duration": 5},
)

EVASION = SkillDef(
    id=403,
    name="闪避",
    role="rogue",
    cooldown=20,
    mana_cost=0,
    cast_time=0,
    target_type="self",
    description="闪避所有攻击持续5秒",
    effects={"type": "buff", "buff_id": "evasion", "duration": 5},
)

DEADLY_COMBO = SkillDef(
    id=404,
    name="致命连击",
    role="rogue",
    cooldown=10,
    mana_cost=0,  # costs all energy, handled in combat
    cast_time=0,
    target_type="enemy",
    description="三连击,消耗全部能量,每点能量造成1.5伤害",
    effects={"type": "special", "special_id": "deadly_combo", "damage_per_energy": 1.5},
)

FAN_OF_KNIVES = SkillDef(
    id=405,
    name="刀扇",
    role="rogue",
    cooldown=4,
    mana_cost=60,
    cast_time=0,
    target_type="enemy_all",
    description="AOE造成250伤害",
    effects={"type": "damage_aoe", "base_damage": 250},
)

# ---------------------------------------------------------------------------
# Hunter skills
# ---------------------------------------------------------------------------
AIMED_SHOT = SkillDef(
    id=501,
    name="精准射击",
    role="hunter",
    cooldown=0,
    mana_cost=60,
    cast_time=1.5,
    target_type="enemy",
    description="造成420伤害",
    effects={"type": "damage", "base_damage": 420},
    auto=True,
)

MULTI_SHOT = SkillDef(
    id=502,
    name="多重射击",
    role="hunter",
    cooldown=4,
    mana_cost=100,
    cast_time=0,
    target_type="enemy_all",
    description="AOE造成250伤害",
    effects={"type": "damage_aoe", "base_damage": 250},
)

HUNTERS_MARK = SkillDef(
    id=503,
    name="猎人印记",
    role="hunter",
    cooldown=0,
    mana_cost=40,
    cast_time=0,
    target_type="enemy",
    description="标记目标,全队对其伤害+15%持续12秒",
    effects={"type": "debuff", "debuff_id": "hunters_mark", "duration": 12, "damage_amp": 0.15},
)

HEALING_WIND = SkillDef(
    id=504,
    name="治疗之风",
    role="hunter",
    cooldown=15,
    mana_cost=120,
    cast_time=0,
    target_type="ally_all",
    description="群体治疗全队250HP",
    effects={"type": "heal_aoe", "base_heal": 250},
)

# ---------------------------------------------------------------------------
# Boss skills
# ---------------------------------------------------------------------------
BOSS_AUTO_ATTACK = SkillDef(
    id=601,
    name="普攻",
    role="boss",
    cooldown=2.5,
    mana_cost=0,
    cast_time=0,
    target_type="enemy",
    description="造成350-600伤害",
    effects={"type": "boss_attack"},
    auto=True,
)

BOSS_CLEAVE = SkillDef(
    id=602,
    name="顺劈斩",
    role="boss",
    cooldown=3.0,
    mana_cost=0,
    cast_time=0,
    target_type="enemy",
    description="造成900伤害",
    effects={"type": "boss_attack", "base_damage": 900},
    auto=True,
)

BOSS_MAGMA_BLAST = SkillDef(
    id=603,
    name="岩浆喷射",
    role="boss",
    cooldown=6.0,
    mana_cost=0,
    cast_time=0,
    target_type="enemy",
    description="造成600伤害并附加150/s灼烧DOT持续5秒",
    effects={"type": "boss_magma", "base_damage": 600, "dot_damage": 150, "dot_duration": 5},
)

BOSS_FIRESTORM = SkillDef(
    id=604,
    name="烈焰风暴",
    role="boss",
    cooldown=6.0,
    mana_cost=0,
    cast_time=0,
    target_type="enemy_all",
    description="对全体造成600伤害",
    effects={"type": "boss_aoe", "base_damage": 600},
)

BOSS_SUMMON = SkillDef(
    id=605,
    name="召唤元素",
    role="boss",
    cooldown=10.0,
    mana_cost=0,
    cast_time=0,
    target_type="self",
    description="召唤3个熔岩元素小怪",
    effects={"type": "boss_summon", "count": 3},
)

BOSS_FISSURE = SkillDef(
    id=606,
    name="熔岩裂隙",
    role="boss",
    cooldown=5.0,
    mana_cost=0,
    cast_time=0,
    target_type="enemy",
    description="在目标脚下制造裂隙,300/s DOT持续5秒",
    effects={"type": "boss_fissure", "dot_damage": 300, "dot_duration": 5},
)

BOSS_APOCALYPSE = SkillDef(
    id=607,
    name="灭世之炎",
    role="boss",
    cooldown=20.0,
    mana_cost=0,
    cast_time=10.0,
    target_type="enemy_all",
    description="10秒读条,对全体造成8000伤害(可打断)",
    effects={"type": "boss_apocalypse", "base_damage": 8000},
)

BOSS_TRAP = SkillDef(
    id=608,
    name="熔岩陷阱",
    role="boss",
    cooldown=6.0,
    mana_cost=0,
    cast_time=0,
    target_type="enemy",
    description="标记目标,5秒后爆炸造成2500伤害",
    effects={"type": "boss_trap", "damage": 2500, "countdown": 5.0},
)

BOSS_HEAL_REDUCTION = SkillDef(
    id=609,
    name="禁疗之焰",
    role="boss",
    cooldown=25.0,
    mana_cost=0,
    cast_time=0,
    target_type="enemy_all",
    description="全体玩家治疗效果降低75%,持续6秒(需逐个驱散)",
    effects={"type": "boss_heal_reduction", "heal_reduction": 0.75, "duration": 6},
)

BOSS_FIRE_SHIELD = SkillDef(
    id=610,
    name="火焰盾",
    role="boss",
    cooldown=18.0,
    mana_cost=0,
    cast_time=0,
    target_type="self",
    description="获得火焰盾,反弹30%受到的伤害,持续10秒",
    effects={"type": "boss_fire_shield", "damage_reflect": 0.3, "duration": 10},
)

BOSS_THRUST = SkillDef(
    id=611,
    name="熔火突刺",
    role="boss",
    cooldown=12.0,
    mana_cost=0,
    cast_time=2.0,
    target_type="enemy",
    description="2秒读条,对当前目标造成5000伤害(需开盾墙抵挡)",
    effects={"type": "boss_thrust", "base_damage": 5000},
)

# ---------------------------------------------------------------------------
# Skill registry
# ---------------------------------------------------------------------------
ALL_SKILLS: list[SkillDef] = [
    TAUNT, SHIELD_WALL, SUNDER_ARMOR, HEROIC_STRIKE,
    HEAL, CIRCLE_OF_HEAL, DISPEL, RESURRECT,
    FIREBALL, BLIZZARD, FROST_NOVA, SPELL_BARRIER,
    BACKSTAB, POISON_BLADE, EVASION, DEADLY_COMBO, FAN_OF_KNIVES,
    AIMED_SHOT, MULTI_SHOT, HUNTERS_MARK, HEALING_WIND,
    BOSS_AUTO_ATTACK, BOSS_CLEAVE, BOSS_MAGMA_BLAST, BOSS_FIRESTORM,
    BOSS_SUMMON, BOSS_FISSURE, BOSS_APOCALYPSE, BOSS_TRAP,
    BOSS_HEAL_REDUCTION, BOSS_FIRE_SHIELD, BOSS_THRUST,
]

SKILLS: dict[int, SkillDef] = {s.id: s for s in ALL_SKILLS}

ROLE_SKILLS: dict[str, list[SkillDef]] = {}
for _s in ALL_SKILLS:
    ROLE_SKILLS.setdefault(_s.role, []).append(_s)


def get_skill(skill_id: int) -> SkillDef | None:
    return SKILLS.get(skill_id)


def get_auto_skills(role: str) -> list[SkillDef]:
    """Return auto skills for a role."""
    return [s for s in ROLE_SKILLS.get(role, []) if s.auto]


def get_llm_skills(role: str) -> list[SkillDef]:
    """Return LLM-controlled skills for a role (non-auto)."""
    return [s for s in ROLE_SKILLS.get(role, []) if not s.auto]
