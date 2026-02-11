"""Boss: Ragnaros the Firelord - 3 phase encounter."""

from __future__ import annotations

import random
from typing import Any

from game.character import Character, Debuff
from game.events import (
    BOSS_CAST, COMBAT_LOG, DAMAGE, DEATH, PHASE_CHANGE, SUMMON, EventBus,
)


class MoltenElemental:
    """Summoned add in Phase 2."""

    def __init__(self, add_id: str) -> None:
        self.id = add_id
        self.name = "熔岩元素"
        self.max_hp = 3000
        self.hp = 3000
        self.alive = True
        self.attack_damage = 150
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
    """Ragnaros the Firelord."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.id = "boss"
        self.name = "熔火之王拉格纳罗斯"
        self.max_hp = 40000
        self.hp = 40000
        self.alive = True
        self.phase = 1

        # Base stats (tuned for slow LLM response ~3-5s per agent)
        self.base_attack_min = 150
        self.base_attack_max = 280
        self.attack_speed = 3.5  # seconds between auto attacks

        # Timers (longer intervals = more time for agents to respond)
        self.auto_attack_timer = 0.0
        self.cleave_timer = 8.0
        self.magma_timer = 12.0
        self.firestorm_timer = 25.0
        self.summon_timer = 35.0
        self.fissure_timer = 20.0
        self.apocalypse_timer = 20.0
        self.trap_timer = 15.0
        self.enrage_timer = 180.0  # P3 enrage

        # Casting state
        self.casting: dict[str, Any] | None = None  # {"name": str, "remaining": float, "effect": callable}

        # Phase 2 adds
        self.adds: list[MoltenElemental] = []

        # Phase 2/3 fissures: list of {"target_id": str, "duration": float, "damage_per_tick": int}
        self.fissures: list[dict[str, Any]] = []

        # Phase 3 traps: list of {"target_id": str, "countdown": float, "damage": int}
        self.traps: list[dict[str, Any]] = []

        # Debuffs on boss (from players)
        self.debuffs: list[Debuff] = []

        # P3 enrage flag
        self.enraged = False

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
    # Take damage
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
        """Check and apply phase transitions. Returns True if phase changed."""
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
        self.firestorm_timer = 8.0
        self.summon_timer = 5.0

    def _enter_phase3(self) -> None:
        self.event_bus.emit(COMBAT_LOG, {
            "message": f"[Phase 3] {self.name}进入灭世阶段! 攻击力+50%, 攻速+30%! 狂暴倒计时120秒!",
        })
        self.apocalypse_timer = 10.0
        self.trap_timer = 6.0
        self.enrage_timer = 120.0

    # ------------------------------------------------------------------
    # AI tick - returns list of actions to execute
    # ------------------------------------------------------------------
    def tick_ai(
        self, dt: float, characters: list[Character], threat_top: str | None
    ) -> list[dict[str, Any]]:
        """Run boss AI for one tick. Returns list of actions taken."""
        if not self.alive:
            return []

        actions: list[dict[str, Any]] = []

        # If currently casting, advance cast
        if self.casting:
            self.casting["remaining"] -= dt
            if self.casting["remaining"] <= 0:
                actions.append({"type": "cast_complete", "name": self.casting["name"]})
                self.casting = None
            else:
                # While casting, skip other actions
                return actions

        # Check if frozen/stunned
        if self.has_debuff("freeze"):
            self._tick_debuff_timers(dt)
            return actions

        self._tick_debuff_timers(dt)
        self._tick_fissures(dt, characters, actions)
        self._tick_traps(dt, characters, actions)
        self._tick_adds(dt, characters, actions)

        # Decrease all timers
        self.auto_attack_timer = max(0, self.auto_attack_timer - dt)
        self.cleave_timer = max(0, self.cleave_timer - dt)
        self.magma_timer = max(0, self.magma_timer - dt)

        if self.phase >= 2:
            self.firestorm_timer = max(0, self.firestorm_timer - dt)
            self.summon_timer = max(0, self.summon_timer - dt)
            self.fissure_timer = max(0, self.fissure_timer - dt)

        if self.phase >= 3:
            self.apocalypse_timer = max(0, self.apocalypse_timer - dt)
            self.trap_timer = max(0, self.trap_timer - dt)
            self.enrage_timer = max(0, self.enrage_timer - dt)
            if self.enrage_timer <= 0 and not self.enraged:
                self.enraged = True
                actions.append({"type": "enrage"})
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"[狂暴] {self.name}进入狂暴状态! 攻击力翻倍!",
                })

        living = [c for c in characters if c.alive]
        if not living:
            return actions

        # Priority: special abilities > cleave > auto attack
        # Phase 3 abilities
        if self.phase >= 3:
            if self.apocalypse_timer <= 0:
                actions.append(self._cast_apocalypse())
                self.apocalypse_timer = 25.0
                return actions

            if self.trap_timer <= 0 and living:
                target = random.choice(living)
                actions.append(self._place_trap(target))
                self.trap_timer = 12.0

        # Phase 2 abilities
        if self.phase >= 2:
            if self.firestorm_timer <= 0:
                actions.append(self._cast_firestorm(living))
                self.firestorm_timer = 15.0

            if self.summon_timer <= 0:
                actions.append(self._summon_adds())
                self.summon_timer = 25.0

            if self.fissure_timer <= 0 and living:
                target = random.choice(living)
                actions.append(self._place_fissure(target))
                self.fissure_timer = 12.0

        # Phase 1+ abilities
        if self.magma_timer <= 0 and living:
            target = random.choice(living)
            actions.append(self._cast_magma_blast(target))
            self.magma_timer = 12.0

        if self.cleave_timer <= 0 and threat_top:
            actions.append(self._cast_cleave(threat_top))
            self.cleave_timer = 8.0

        if self.auto_attack_timer <= 0 and threat_top:
            actions.append(self._auto_attack(threat_top))
            self.auto_attack_timer = self.current_attack_speed

        return actions

    # ------------------------------------------------------------------
    # Boss abilities
    # ------------------------------------------------------------------
    def _auto_attack(self, target_id: str) -> dict:
        damage = random.randint(self.attack_min, self.attack_max)
        return {"type": "auto_attack", "target": target_id, "damage": damage, "name": "普攻"}

    def _cast_cleave(self, target_id: str) -> dict:
        self.event_bus.emit(BOSS_CAST, {"skill": "顺劈斩", "target": target_id})
        return {"type": "cleave", "target": target_id, "damage": 450, "name": "顺劈斩"}

    def _cast_magma_blast(self, target: Character) -> dict:
        self.event_bus.emit(BOSS_CAST, {"skill": "岩浆喷射", "target": target.id})
        return {
            "type": "magma_blast",
            "target": target.id,
            "damage": 350,
            "dot_damage": 60,
            "dot_duration": 5,
            "name": "岩浆喷射",
        }

    def _cast_firestorm(self, targets: list[Character]) -> dict:
        self.event_bus.emit(BOSS_CAST, {"skill": "烈焰风暴"})
        return {"type": "firestorm", "damage": 220, "name": "烈焰风暴"}

    def _summon_adds(self) -> dict:
        add_count = len(self.adds)
        new_adds = []
        for i in range(2):
            add = MoltenElemental(f"add_{add_count + i}")
            self.adds.append(add)
            new_adds.append(add)
        self.event_bus.emit(SUMMON, {
            "boss": self.name, "summon": "熔岩元素", "count": 2,
        })
        return {"type": "summon", "adds": new_adds, "name": "召唤熔岩元素"}

    def _place_fissure(self, target: Character) -> dict:
        fissure = {
            "target_id": target.id,
            "duration": 6.0,
            "damage_per_tick": 150,
            "name": "熔岩裂隙",
        }
        self.fissures.append(fissure)
        self.event_bus.emit(BOSS_CAST, {"skill": "熔岩裂隙", "target": target.id})
        return {"type": "fissure", "target": target.id, "name": "熔岩裂隙"}

    def _cast_apocalypse(self) -> dict:
        """灭世之炎: 3s cast, 8000 damage to all. Must be interrupted."""
        self.casting = {
            "name": "灭世之炎",
            "remaining": 3.0,
        }
        self.event_bus.emit(BOSS_CAST, {
            "skill": "灭世之炎", "cast_time": 3.0,
            "message": "灭世之炎正在读条! 必须打断!",
        })
        return {"type": "apocalypse_start", "cast_time": 3.0, "name": "灭世之炎"}

    def _place_trap(self, target: Character) -> dict:
        trap = {
            "target_id": target.id,
            "countdown": 5.0,
            "damage": 1500,
            "name": "熔岩陷阱",
        }
        self.traps.append(trap)
        self.event_bus.emit(BOSS_CAST, {
            "skill": "熔岩陷阱", "target": target.id,
            "message": f"熔岩陷阱标记了{target.name}! 5秒后爆炸!",
        })
        return {"type": "trap", "target": target.id, "countdown": 5.0, "name": "熔岩陷阱"}

    # ------------------------------------------------------------------
    # Tick helpers
    # ------------------------------------------------------------------
    def _tick_debuff_timers(self, dt: float) -> None:
        remaining = []
        for d in self.debuffs:
            d.duration -= dt
            if d.duration > 0:
                remaining.append(d)
        self.debuffs = remaining

    def _tick_fissures(self, dt: float, characters: list[Character], actions: list) -> None:
        remaining = []
        for f in self.fissures:
            f["duration"] -= dt
            if f["duration"] > 0:
                remaining.append(f)
                # Damage the targeted character each tick
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

    def _tick_traps(self, dt: float, characters: list[Character], actions: list) -> None:
        remaining = []
        for trap in self.traps:
            trap["countdown"] -= dt
            if trap["countdown"] <= 0:
                # Explode - damage the target and nearby allies
                for c in characters:
                    if c.alive:
                        actual = c.take_damage(trap["damage"])
                        if actual > 0:
                            self.event_bus.emit(DAMAGE, {
                                "source": "boss", "target": c.id,
                                "skill": trap["name"], "amount": actual,
                            })
                        if not c.alive:
                            self.event_bus.emit(DEATH, {"target": c.id, "source": trap["name"]})
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"熔岩陷阱爆炸! 对全体造成{trap['damage']}伤害!",
                })
            else:
                remaining.append(trap)
        self.traps = remaining

    def _tick_adds(self, dt: float, characters: list[Character], actions: list) -> None:
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
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "hp_percent": round(self.hp_percent * 100, 1),
            "phase": self.phase,
            "alive": self.alive,
            "casting": {
                "name": self.casting["name"],
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
