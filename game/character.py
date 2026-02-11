"""Character classes for the five roles."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from game.skills import ROLE_SKILLS, SkillDef


@dataclass
class Buff:
    buff_id: str
    name: str
    duration: float  # remaining seconds
    params: dict[str, Any] = field(default_factory=dict)
    source: str = ""  # character_id that applied it


@dataclass
class Debuff:
    debuff_id: str
    name: str
    duration: float
    params: dict[str, Any] = field(default_factory=dict)
    source: str = ""


# ---------------------------------------------------------------------------
# Role config
# ---------------------------------------------------------------------------
ROLE_CONFIG: dict[str, dict[str, Any]] = {
    "tank": {"max_hp": 8000, "max_mana": 1500, "resource_name": "怒气"},
    "healer": {"max_hp": 4000, "max_mana": 4000, "resource_name": "法力"},
    "mage": {"max_hp": 3500, "max_mana": 4000, "resource_name": "法力"},
    "rogue": {"max_hp": 4500, "max_mana": 2000, "resource_name": "能量"},
    "hunter": {"max_hp": 4200, "max_mana": 3000, "resource_name": "法力"},
}

ROLE_NAMES: dict[str, str] = {
    "tank": "坦克",
    "healer": "治疗",
    "mage": "法师",
    "rogue": "盗贼",
    "hunter": "猎人",
}

GCD_DURATION = 1.5  # seconds


class Character:
    """Base character used by all roles."""

    def __init__(self, character_id: str, role: str) -> None:
        cfg = ROLE_CONFIG[role]
        self.id: str = character_id
        self.role: str = role
        self.name: str = ROLE_NAMES[role]
        self.resource_name: str = cfg["resource_name"]

        self.max_hp: int = cfg["max_hp"]
        self.hp: int = self.max_hp
        self.max_mana: int = cfg["max_mana"]
        self.mana: int = self.max_mana

        self.alive: bool = True
        self.skills: list[SkillDef] = list(ROLE_SKILLS.get(role, []))

        # Cooldown tracking: skill_id -> remaining seconds
        self.cooldowns: dict[int, float] = {}
        # GCD remaining seconds
        self.gcd: float = 0.0
        # Casting state
        self.casting: dict[str, Any] | None = None  # {"skill": SkillDef, "target": str, "remaining": float}

        self.buffs: list[Buff] = []
        self.debuffs: list[Debuff] = []

        # Mana regen per tick (passive)
        self._mana_regen_per_tick = 20 if role != "rogue" else 30  # rogues regen energy faster

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @property
    def is_alive(self) -> bool:
        return self.alive

    def gcd_ready(self) -> bool:
        return self.gcd <= 0 and not self.is_casting()

    def is_on_gcd(self) -> bool:
        return self.gcd > 0

    def is_casting(self) -> bool:
        return self.casting is not None

    def can_use_skill(self, skill: SkillDef) -> tuple[bool, str]:
        if not self.alive:
            return False, "角色已死亡"
        if self.is_casting():
            return False, "正在施法中"
        if self.is_on_gcd():
            return False, "全局冷却中"
        cd = self.cooldowns.get(skill.id, 0)
        if cd > 0:
            return False, f"技能冷却中({cd:.1f}s)"
        # Deadly combo costs all energy, just needs > 0
        if skill.id == 404:
            if self.mana <= 0:
                return False, "能量不足"
        else:
            if self.mana < skill.mana_cost:
                return False, f"{self.resource_name}不足"
        return True, ""

    def has_buff(self, buff_id: str) -> bool:
        return any(b.buff_id == buff_id for b in self.buffs)

    def has_debuff(self, debuff_id: str) -> bool:
        return any(d.debuff_id == debuff_id for d in self.debuffs)

    def get_buff(self, buff_id: str) -> Buff | None:
        for b in self.buffs:
            if b.buff_id == buff_id:
                return b
        return None

    def get_debuff(self, debuff_id: str) -> Debuff | None:
        for d in self.debuffs:
            if d.debuff_id == debuff_id:
                return d
        return None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def start_cast(self, skill: SkillDef, target: str) -> None:
        """Begin casting a skill with a cast time."""
        self.casting = {"skill": skill, "target": target, "remaining": skill.cast_time}

    def consume_mana(self, skill: SkillDef) -> None:
        if skill.id == 404:
            self.mana = 0
        else:
            self.mana = max(0, self.mana - skill.mana_cost)

    def trigger_gcd(self) -> None:
        self.gcd = GCD_DURATION

    def set_cooldown(self, skill: SkillDef) -> None:
        if skill.cooldown > 0:
            self.cooldowns[skill.id] = skill.cooldown

    def add_buff(self, buff: Buff) -> None:
        # Refresh if same buff_id exists
        self.buffs = [b for b in self.buffs if b.buff_id != buff.buff_id]
        self.buffs.append(buff)

    def remove_buff(self, buff_id: str) -> Buff | None:
        for i, b in enumerate(self.buffs):
            if b.buff_id == buff_id:
                return self.buffs.pop(i)
        return None

    def add_debuff(self, debuff: Debuff) -> None:
        self.debuffs = [d for d in self.debuffs if d.debuff_id != debuff.debuff_id]
        self.debuffs.append(debuff)

    def remove_debuff(self, debuff_id: str) -> Debuff | None:
        for i, d in enumerate(self.debuffs):
            if d.debuff_id == debuff_id:
                return self.debuffs.pop(i)
        return None

    def remove_one_debuff(self) -> Debuff | None:
        """Remove the first harmful debuff (for dispel)."""
        if self.debuffs:
            return self.debuffs.pop(0)
        return None

    def take_damage(self, amount: int) -> int:
        """Apply damage after reduction. Returns actual damage taken."""
        if not self.alive:
            return 0

        # Spell barrier absorbs one hit entirely
        barrier = self.get_buff("spell_barrier")
        if barrier:
            charges = barrier.params.get("charges", 0)
            if charges > 0:
                barrier.params["charges"] = charges - 1
                if barrier.params["charges"] <= 0:
                    self.remove_buff("spell_barrier")
                return 0

        # Evasion avoids all attacks
        if self.has_buff("evasion"):
            return 0

        # Shield wall reduces damage
        sw = self.get_buff("shield_wall")
        if sw:
            reduction = sw.params.get("damage_reduction", 0)
            amount = int(amount * (1 - reduction))

        actual = min(self.hp, max(0, amount))
        self.hp -= actual
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return actual

    def receive_heal(self, amount: int) -> int:
        """Heal the character. Returns actual healing done."""
        if not self.alive:
            return 0
        actual = min(self.max_hp - self.hp, max(0, amount))
        self.hp += actual
        return actual

    def die(self) -> None:
        self.hp = 0
        self.alive = False
        self.casting = None
        self.buffs.clear()
        self.debuffs.clear()

    def resurrect(self, hp_percent: float = 0.3) -> None:
        self.alive = True
        self.hp = int(self.max_hp * hp_percent)
        self.mana = int(self.max_mana * 0.2)

    def tick_timers(self, dt: float) -> list[str]:
        """Advance all timers by dt seconds. Return list of expired buff/debuff ids."""
        expired: list[str] = []

        # GCD
        if self.gcd > 0:
            self.gcd = max(0, self.gcd - dt)

        # Cooldowns
        for sid in list(self.cooldowns):
            self.cooldowns[sid] -= dt
            if self.cooldowns[sid] <= 0:
                del self.cooldowns[sid]

        # Casting
        if self.casting:
            self.casting["remaining"] -= dt
            # Casting is resolved in combat system when remaining <= 0

        # Buffs
        remaining_buffs: list[Buff] = []
        for b in self.buffs:
            if b.duration is not None and b.duration > 0:
                b.duration -= dt
                if b.duration <= 0:
                    expired.append(f"buff:{b.buff_id}")
                    continue
            remaining_buffs.append(b)
        self.buffs = remaining_buffs

        # Debuffs (DOTs handled separately in combat)
        remaining_debuffs: list[Debuff] = []
        for d in self.debuffs:
            if d.duration is not None and d.duration > 0:
                d.duration -= dt
                if d.duration <= 0:
                    expired.append(f"debuff:{d.debuff_id}")
                    continue
            remaining_debuffs.append(d)
        self.debuffs = remaining_debuffs

        # Passive mana regen
        if self.alive:
            self.mana = min(self.max_mana, self.mana + self._mana_regen_per_tick)

        return expired

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mana": self.mana,
            "max_mana": self.max_mana,
            "resource_name": self.resource_name,
            "alive": self.alive,
            "gcd": round(self.gcd, 2),
            "casting": {
                "skill_name": self.casting["skill"].name,
                "remaining": round(self.casting["remaining"], 2),
                "target": self.casting["target"],
            } if self.casting else None,
            "cooldowns": {str(k): round(v, 2) for k, v in self.cooldowns.items()},
            "buffs": [{"id": b.buff_id, "name": b.name, "duration": round(b.duration, 2), "params": b.params} for b in self.buffs],
            "debuffs": [{"id": d.debuff_id, "name": d.name, "duration": round(d.duration, 2), "params": d.params} for d in self.debuffs],
            "skills": [{"id": s.id, "name": s.name, "cooldown": s.cooldown, "mana_cost": s.mana_cost, "cast_time": s.cast_time, "description": s.description} for s in self.skills],
        }


def create_character(character_id: str, role: str) -> Character:
    """Factory function to create a character for the given role."""
    if role not in ROLE_CONFIG:
        raise ValueError(f"Unknown role: {role}")
    return Character(character_id, role)
