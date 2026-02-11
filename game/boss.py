"""Boss: Ragnaros the Firelord - Agent-driven encounter."""

from __future__ import annotations

import random
from typing import Any

from game.character import Character, Debuff
from game.events import (
    COMBAT_LOG, DAMAGE, DEATH, PHASE_CHANGE, SUMMON, EventBus,
)
from game.skills import ROLE_SKILLS, SkillDef

GCD_DURATION = 1.5


class MoltenElemental:
    """Summoned add in Phase 2."""

    def __init__(self, add_id: str) -> None:
        self.id = add_id
        self.name = "熔岩元素"
        self.max_hp = 4000
        self.hp = 4000
        self.alive = True
        self.attack_damage = 200
        self.attack_cooldown = 2.0
        self.attack_timer = 0.0
        self.debuffs: list[Debuff] = []

    def take_damage(self, amount: int) -> int:
        if not self.alive:
            return 0
        actual = min(self.hp, max(0, amount))
        self.hp -= actual
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return actual

    def has_debuff(self, debuff_id: str) -> bool:
        return any(d.debuff_id == debuff_id for d in self.debuffs)

    def get_debuff(self, debuff_id: str) -> Debuff | None:
        for d in self.debuffs:
            if d.debuff_id == debuff_id:
                return d
        return None

    def add_debuff(self, debuff: Debuff) -> None:
        self.debuffs = [d for d in self.debuffs if d.debuff_id != debuff.debuff_id]
        self.debuffs.append(debuff)

    def tick_timers(self, dt: float) -> None:
        self.attack_timer = max(0, self.attack_timer - dt)
        remaining = []
        for d in self.debuffs:
            d.duration -= dt
            if d.duration > 0:
                remaining.append(d)
        self.debuffs = remaining

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "alive": self.alive,
        }


class Boss:
    """Ragnaros the Firelord - Character-compatible interface for Agent system."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.id = "boss"
        self.name = "熔火之王拉格纳罗斯"
        self.max_hp = 80000
        self.hp = 80000
        self.alive = True
        self.phase = 1

        # Base stats (tuned for slow LLM response ~3-5s per agent)
        self.base_attack_min = 350
        self.base_attack_max = 550
        self.attack_speed = 2.5  # seconds between auto attacks

        # --- Character-compatible interface ---
        self.gcd: float = 0.0
        self.cooldowns: dict[int, float] = {}
        self.skills: list[SkillDef] = list(ROLE_SKILLS.get("boss", []))
        self.last_action: dict | None = None

        # Casting state (same format as Character)
        self.casting: dict[str, Any] | None = None

        # Initial cooldowns — ramp up boss aggression gradually
        self.cooldowns[607] = 30.0  # 灭世之炎: first available ~30s (around P2)
        self.cooldowns[605] = 15.0  # 召唤元素: first available ~15s
        self.cooldowns[604] = 8.0   # 烈焰风暴: first available ~8s

        # Phase 2 adds
        self.adds: list[MoltenElemental] = []

        # Phase 2/3 fissures
        self.fissures: list[dict[str, Any]] = []

        # Phase 3 traps
        self.traps: list[dict[str, Any]] = []

        # Debuffs on boss (from players)
        self.debuffs: list[Debuff] = []

        # P3 enrage
        self.enraged = False
        self.enrage_timer = 180.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def hp_percent(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0

    @property
    def attack_min(self) -> int:
        mult = 1.0
        if self.phase >= 2:
            mult += 0.15
        if self.phase >= 3:
            mult += 0.25
        if self.enraged:
            mult += 0.5
        return int(self.base_attack_min * mult)

    @property
    def attack_max(self) -> int:
        mult = 1.0
        if self.phase >= 2:
            mult += 0.15
        if self.phase >= 3:
            mult += 0.25
        if self.enraged:
            mult += 0.5
        return int(self.base_attack_max * mult)

    @property
    def current_attack_speed(self) -> float:
        speed = self.attack_speed
        if self.phase >= 3:
            speed *= 0.7  # 30% faster
        return speed

    # ------------------------------------------------------------------
    # Character-compatible interface
    # ------------------------------------------------------------------
    def gcd_ready(self) -> bool:
        return self.gcd <= 0 and not self.is_casting()

    def is_on_gcd(self) -> bool:
        return self.gcd > 0

    def is_casting(self) -> bool:
        return self.casting is not None

    def can_use_skill(self, skill: SkillDef) -> tuple[bool, str]:
        if not self.alive:
            return False, "Boss已死亡"
        if self.is_casting():
            return False, "正在施法中"
        if self.is_on_gcd():
            return False, "全局冷却中"
        if self.has_debuff("freeze"):
            return False, "被冻结"
        cd = self.cooldowns.get(skill.id, 0)
        if cd > 0:
            return False, f"技能冷却中({cd:.1f}s)"
        return True, ""

    def trigger_gcd(self) -> None:
        self.gcd = GCD_DURATION

    def set_cooldown(self, skill: SkillDef) -> None:
        if skill.cooldown > 0:
            self.cooldowns[skill.id] = skill.cooldown

    def consume_mana(self, skill: SkillDef) -> None:
        pass  # Boss has no resource

    def start_cast(self, skill: SkillDef, target: str) -> None:
        self.casting = {"skill": skill, "target": target, "remaining": skill.cast_time}

    # ------------------------------------------------------------------
    # Take damage / debuffs
    # ------------------------------------------------------------------
    def take_damage(self, amount: int) -> int:
        if not self.alive:
            return 0
        actual = min(self.hp, max(0, amount))
        self.hp -= actual
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return actual

    def has_debuff(self, debuff_id: str) -> bool:
        return any(d.debuff_id == debuff_id for d in self.debuffs)

    def get_debuff(self, debuff_id: str) -> Debuff | None:
        for d in self.debuffs:
            if d.debuff_id == debuff_id:
                return d
        return None

    def add_debuff(self, debuff: Debuff) -> None:
        self.debuffs = [d for d in self.debuffs if d.debuff_id != debuff.debuff_id]
        self.debuffs.append(debuff)

    # ------------------------------------------------------------------
    # Phase management
    # ------------------------------------------------------------------
    def check_phase_transition(self) -> bool:
        old_phase = self.phase
        pct = self.hp_percent
        if pct <= 0.3 and self.phase < 3:
            self.phase = 3
            self._enter_phase3()
        elif pct <= 0.6 and self.phase < 2:
            self.phase = 2
            self._enter_phase2()

        if self.phase != old_phase:
            self.event_bus.emit(PHASE_CHANGE, {
                "boss": self.name, "phase": self.phase, "hp_percent": round(pct * 100, 1),
            })
            return True
        return False

    def _enter_phase2(self) -> None:
        self.event_bus.emit(COMBAT_LOG, {
            "message": f"[Phase 2] {self.name}进入狂怒阶段! 攻击力提升30%!",
        })

    def _enter_phase3(self) -> None:
        self.event_bus.emit(COMBAT_LOG, {
            "message": f"[Phase 3] {self.name}进入灭世阶段! 攻击力+50%, 攻速+30%! 狂暴倒计时90秒!",
        })
        self.enrage_timer = 90.0

    # ------------------------------------------------------------------
    # Timer ticking (called by engine each tick)
    # ------------------------------------------------------------------
    def tick_timers(self, dt: float) -> list[str]:
        """Advance GCD, cooldowns, debuffs. Returns expired debuff ids."""
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

        # Debuffs
        remaining_debuffs: list[Debuff] = []
        for d in self.debuffs:
            if d.duration is not None and d.duration > 0:
                d.duration -= dt
                if d.duration <= 0:
                    expired.append(f"debuff:{d.debuff_id}")
                    continue
            remaining_debuffs.append(d)
        self.debuffs = remaining_debuffs

        # Enrage timer (P3)
        if self.phase >= 3 and not self.enraged:
            self.enrage_timer = max(0, self.enrage_timer - dt)
            if self.enrage_timer <= 0:
                self.enraged = True
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"[狂暴] {self.name}进入狂暴状态! 攻击力翻倍!",
                })

        return expired

    # ------------------------------------------------------------------
    # Passive mechanics (called by engine each tick)
    # ------------------------------------------------------------------
    def tick_passive(self, dt: float, characters: list[Character]) -> None:
        """Tick fissures, traps, adds - passive mechanics independent of Agent."""
        if not self.alive:
            return
        self._tick_fissures(dt, characters)
        self._tick_traps(dt, characters)
        self._tick_adds(dt, characters)

    def _tick_fissures(self, dt: float, characters: list[Character]) -> None:
        remaining = []
        for f in self.fissures:
            f["duration"] -= dt
            if f["duration"] > 0:
                remaining.append(f)
                for c in characters:
                    if c.id == f["target_id"] and c.alive:
                        dmg = int(f["damage_per_tick"] * dt)
                        actual = c.take_damage(dmg)
                        if actual > 0:
                            self.event_bus.emit(DAMAGE, {
                                "source": "boss", "target": c.id,
                                "skill": f["name"], "amount": actual, "is_dot": True,
                            })
                        if not c.alive:
                            self.event_bus.emit(DEATH, {"target": c.id, "source": f["name"]})
        self.fissures = remaining

    def _tick_traps(self, dt: float, characters: list[Character]) -> None:
        remaining = []
        for trap in self.traps:
            trap["countdown"] -= dt
            if trap["countdown"] <= 0:
                # Single-target: only damage the marked target
                target_id = trap.get("target_id", "")
                for c in characters:
                    if c.id == target_id and c.alive:
                        actual = c.take_damage(trap["damage"])
                        if actual > 0:
                            self.event_bus.emit(DAMAGE, {
                                "source": "boss", "target": c.id,
                                "skill": trap["name"], "amount": actual,
                            })
                        if not c.alive:
                            self.event_bus.emit(DEATH, {"target": c.id, "source": trap["name"]})
                        self.event_bus.emit(COMBAT_LOG, {
                            "message": f"熔岩陷阱在{c.name}脚下爆炸! 造成{trap['damage']}伤害!",
                        })
                        break
            else:
                remaining.append(trap)
        self.traps = remaining

    def _tick_adds(self, dt: float, characters: list[Character]) -> None:
        for add in self.adds:
            if not add.alive:
                continue
            add.tick_timers(dt)
            if add.attack_timer <= 0:
                living = [c for c in characters if c.alive]
                if living:
                    target = random.choice(living)
                    actual = target.take_damage(add.attack_damage)
                    add.attack_timer = add.attack_cooldown
                    if actual > 0:
                        self.event_bus.emit(DAMAGE, {
                            "source": add.id, "target": target.id,
                            "skill": "熔岩元素攻击", "amount": actual,
                        })
                    if not target.alive:
                        self.event_bus.emit(DEATH, {"target": target.id, "source": add.name})

    # ------------------------------------------------------------------
    # Summon adds (called by engine when skill 605 executes)
    # ------------------------------------------------------------------
    def summon_adds(self, count: int = 2) -> list[MoltenElemental]:
        add_offset = len(self.adds)
        new_adds = []
        for i in range(count):
            add = MoltenElemental(f"add_{add_offset + i}")
            self.adds.append(add)
            new_adds.append(add)
        self.event_bus.emit(SUMMON, {
            "boss": self.name, "summon": "熔岩元素", "count": count,
        })
        return new_adds

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Legacy format for backward compatibility."""
        return {
            "id": self.id,
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "hp_percent": round(self.hp_percent * 100, 1),
            "phase": self.phase,
            "alive": self.alive,
            "casting": {
                "name": self.casting["skill"].name,
                "remaining": round(self.casting["remaining"], 2),
            } if self.casting else None,
            "debuffs": [
                {"id": d.debuff_id, "name": d.name, "duration": round(d.duration, 2)}
                for d in self.debuffs
            ],
            "adds": [a.to_dict() for a in self.adds if a.alive],
            "fissures": [
                {"target": f["target_id"], "duration": round(f["duration"], 2)}
                for f in self.fissures
            ],
            "traps": [
                {"target": t["target_id"], "countdown": round(t["countdown"], 2)}
                for t in self.traps
            ],
            "enraged": self.enraged,
            "enrage_timer": round(self.enrage_timer, 1) if self.phase >= 3 else None,
        }

    def to_card_dict(self) -> dict[str, Any]:
        """Return Character.to_dict()-compatible format for the 6-card UI."""
        return {
            "id": self.id,
            "role": "boss",
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mana": 0,
            "max_mana": 0,
            "resource_name": "",
            "alive": self.alive,
            "gcd": round(self.gcd, 2),
            "casting": {
                "skill_name": self.casting["skill"].name,
                "remaining": round(self.casting["remaining"], 2),
                "target": self.casting["target"],
            } if self.casting else None,
            "cooldowns": {str(k): round(v, 2) for k, v in self.cooldowns.items()},
            "buffs": [],
            "debuffs": [
                {"id": d.debuff_id, "name": d.name, "duration": round(d.duration, 2), "params": d.params}
                for d in self.debuffs
            ],
            "skills": [
                {"id": s.id, "name": s.name, "cooldown": s.cooldown, "mana_cost": s.mana_cost,
                 "cast_time": s.cast_time, "description": s.description, "auto": s.auto}
                for s in self.skills
            ],
            "last_action": self.last_action,
            # Boss-specific badges
            "phase": self.phase,
            "adds_count": len([a for a in self.adds if a.alive]),
            "enraged": self.enraged,
            "enrage_timer": round(self.enrage_timer, 1) if self.phase >= 3 else None,
            "fissures": [
                {"target": f["target_id"], "duration": round(f["duration"], 2)}
                for f in self.fissures
            ],
            "traps": [
                {"target": t["target_id"], "countdown": round(t["countdown"], 2)}
                for t in self.traps
            ],
        }
