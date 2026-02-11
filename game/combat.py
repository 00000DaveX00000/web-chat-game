"""Combat system: damage calculation, buff/debuff processing, threat management."""

from __future__ import annotations

import random
from typing import Any

from game.character import Buff, Character, Debuff
from game.events import (
    BUFF_APPLY, BUFF_EXPIRE, COMBAT_LOG, DAMAGE, DEATH, HEAL, EventBus,
)
from game.skills import SkillDef


class ThreatTable:
    """Tracks threat (aggro) for each character against a target."""

    def __init__(self) -> None:
        self._threat: dict[str, float] = {}
        # Taunt overrides: character_id -> remaining seconds
        self._taunt: dict[str, float] = {}

    def add_threat(self, character_id: str, amount: float) -> None:
        self._threat[character_id] = self._threat.get(character_id, 0) + amount

    def add_heal_threat(self, character_id: str, heal_amount: float) -> None:
        self.add_threat(character_id, heal_amount * 0.5)

    def apply_taunt(self, character_id: str, duration: float) -> None:
        """Force character to be top threat for duration seconds."""
        # Set threat to current max + 1 so they're highest
        max_threat = max(self._threat.values()) if self._threat else 0
        self._threat[character_id] = max_threat + 1
        self._taunt[character_id] = duration

    def get_top_threat(self, alive_ids: set[str] | None = None) -> str | None:
        """Return the character_id with the highest threat."""
        # If someone has an active taunt, they are forced first
        for cid, remaining in sorted(self._taunt.items(), key=lambda x: -x[1]):
            if remaining > 0 and (alive_ids is None or cid in alive_ids):
                return cid

        if not self._threat:
            return None

        candidates = self._threat
        if alive_ids is not None:
            candidates = {k: v for k, v in self._threat.items() if k in alive_ids}
        if not candidates:
            return None
        return max(candidates, key=candidates.get)

    def tick(self, dt: float) -> None:
        """Reduce taunt timers."""
        expired = []
        for cid in list(self._taunt):
            self._taunt[cid] -= dt
            if self._taunt[cid] <= 0:
                expired.append(cid)
        for cid in expired:
            del self._taunt[cid]

    def get_threat_list(self) -> dict[str, float]:
        return dict(self._threat)

    def remove(self, character_id: str) -> None:
        self._threat.pop(character_id, None)
        self._taunt.pop(character_id, None)


class CombatSystem:
    """Resolves skills, manages buffs/debuffs, and processes DOTs/HOTs."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.threat = ThreatTable()

    # ------------------------------------------------------------------
    # Skill resolution
    # ------------------------------------------------------------------
    def resolve_skill(
        self,
        caster: Character,
        skill: SkillDef,
        target: Any,  # Character, Boss, or list
        all_allies: list[Character] | None = None,
        all_enemies: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a skill's effects. Returns a result summary."""
        result: dict[str, Any] = {"skill": skill.name, "caster": caster.id}
        eff = skill.effects

        etype = eff.get("type", "")

        if etype == "damage":
            result.update(self._resolve_damage(caster, skill, target, eff))
        elif etype == "damage_aoe":
            result.update(self._resolve_damage_aoe(caster, skill, all_enemies or [], eff))
        elif etype == "heal":
            result.update(self._resolve_heal(caster, skill, target, eff))
        elif etype == "heal_aoe":
            result.update(self._resolve_heal_aoe(caster, skill, all_allies or [], eff))
        elif etype == "taunt":
            result.update(self._resolve_taunt(caster, skill, eff))
        elif etype == "buff":
            result.update(self._resolve_buff(caster, skill, target, eff))
        elif etype == "debuff":
            result.update(self._resolve_debuff(caster, skill, target, eff))
        elif etype == "control":
            result.update(self._resolve_control(caster, skill, target, eff))
        elif etype == "dispel":
            result.update(self._resolve_dispel(caster, skill, target))
        elif etype == "resurrect":
            result.update(self._resolve_resurrect(caster, skill, target, eff))
        elif etype == "special":
            result.update(self._resolve_special(caster, skill, target, eff))

        return result

    # ------------------------------------------------------------------
    # Damage
    # ------------------------------------------------------------------
    def _resolve_damage(self, caster: Character, skill: SkillDef, target: Any, eff: dict) -> dict:
        base = eff.get("base_damage", 0)
        damage = self._calc_damage(base, caster, target)
        actual = target.take_damage(damage)
        self.threat.add_threat(caster.id, actual)

        self.event_bus.emit(DAMAGE, {
            "source": caster.id, "target": getattr(target, "id", "boss"),
            "skill": skill.name, "amount": actual,
        })

        # Apply DOT if present
        if eff.get("dot"):
            dot_debuff = Debuff(
                debuff_id=eff["dot_id"],
                name=f"{skill.name}(DOT)",
                duration=eff["dot_duration"],
                params={"damage_per_tick": eff["dot_damage"], "source": caster.id},
                source=caster.id,
            )
            target.add_debuff(dot_debuff)
            self.event_bus.emit(BUFF_APPLY, {
                "target": getattr(target, "id", "boss"),
                "debuff_id": eff["dot_id"], "name": dot_debuff.name,
                "duration": eff["dot_duration"],
            })

        # Apply armor debuff if present
        if eff.get("debuff_id") and not eff.get("dot"):
            debuff = Debuff(
                debuff_id=eff["debuff_id"],
                name=f"{skill.name}效果",
                duration=eff.get("duration", 10),
                params={k: v for k, v in eff.items() if k not in ("type", "base_damage", "debuff_id", "duration")},
                source=caster.id,
            )
            target.add_debuff(debuff)

        return {"damage": actual, "target": getattr(target, "id", "boss")}

    def _resolve_damage_aoe(self, caster: Character, skill: SkillDef, targets: list, eff: dict) -> dict:
        base = eff.get("base_damage", 0)
        total = 0
        hit_list = []
        for t in targets:
            if not getattr(t, "alive", True):
                continue
            damage = self._calc_damage(base, caster, t)
            actual = t.take_damage(damage)
            total += actual
            hit_list.append({"target": getattr(t, "id", "?"), "amount": actual})
            self.event_bus.emit(DAMAGE, {
                "source": caster.id, "target": getattr(t, "id", "?"),
                "skill": skill.name, "amount": actual,
            })
        self.threat.add_threat(caster.id, total)
        return {"total_damage": total, "hits": hit_list}

    def _calc_damage(self, base: int, caster: Character, target: Any) -> int:
        """Calculate final damage considering buffs/debuffs."""
        damage = base
        # Random variance +/- 10%
        damage = int(damage * random.uniform(0.9, 1.1))

        # Hunter's mark on target
        if hasattr(target, "has_debuff") and target.has_debuff("hunters_mark"):
            mark = target.get_debuff("hunters_mark")
            if mark:
                amp = mark.params.get("damage_amp", 0)
                damage = int(damage * (1 + amp))

        # Sunder armor on target
        if hasattr(target, "has_debuff") and target.has_debuff("sunder_armor"):
            sa = target.get_debuff("sunder_armor")
            if sa:
                reduction = sa.params.get("armor_reduction", 0)
                damage = int(damage * (1 + reduction))

        return max(1, damage)

    # ------------------------------------------------------------------
    # Healing
    # ------------------------------------------------------------------
    def _resolve_heal(self, caster: Character, skill: SkillDef, target: Character, eff: dict) -> dict:
        base = eff.get("base_heal", 0)
        heal = int(base * random.uniform(0.95, 1.05))
        actual = target.receive_heal(heal)
        self.threat.add_heal_threat(caster.id, actual)
        self.event_bus.emit(HEAL, {
            "source": caster.id, "target": target.id,
            "skill": skill.name, "amount": actual,
        })
        return {"heal": actual, "target": target.id}

    def _resolve_heal_aoe(self, caster: Character, skill: SkillDef, targets: list[Character], eff: dict) -> dict:
        base = eff.get("base_heal", 0)
        total = 0
        for t in targets:
            if not t.alive:
                continue
            heal = int(base * random.uniform(0.95, 1.05))
            actual = t.receive_heal(heal)
            total += actual
            self.event_bus.emit(HEAL, {
                "source": caster.id, "target": t.id,
                "skill": skill.name, "amount": actual,
            })
        self.threat.add_heal_threat(caster.id, total)
        return {"total_heal": total}

    # ------------------------------------------------------------------
    # Buffs / Debuffs / Control
    # ------------------------------------------------------------------
    def _resolve_taunt(self, caster: Character, skill: SkillDef, eff: dict) -> dict:
        duration = eff.get("duration", 6)
        self.threat.apply_taunt(caster.id, duration)
        self.event_bus.emit(COMBAT_LOG, {
            "message": f"{caster.name}对Boss使用了嘲讽,强制仇恨{duration}秒",
        })
        return {"taunt_duration": duration}

    def _resolve_buff(self, caster: Character, skill: SkillDef, target: Any, eff: dict) -> dict:
        buff_target = caster if skill.target_type == "self" else target
        buff = Buff(
            buff_id=eff["buff_id"],
            name=skill.name,
            duration=eff.get("duration", 9999),
            params={k: v for k, v in eff.items() if k not in ("type", "buff_id", "duration")},
            source=caster.id,
        )
        buff_target.add_buff(buff)
        self.event_bus.emit(BUFF_APPLY, {
            "target": getattr(buff_target, "id", "?"),
            "buff_id": eff["buff_id"], "name": skill.name,
            "duration": eff.get("duration", 0),
        })
        return {"buff": eff["buff_id"], "target": getattr(buff_target, "id", "?")}

    def _resolve_debuff(self, caster: Character, skill: SkillDef, target: Any, eff: dict) -> dict:
        debuff = Debuff(
            debuff_id=eff["debuff_id"],
            name=skill.name,
            duration=eff.get("duration", 10),
            params={k: v for k, v in eff.items() if k not in ("type", "debuff_id", "duration")},
            source=caster.id,
        )
        target.add_debuff(debuff)
        self.threat.add_threat(caster.id, 50)  # debuff generates some threat
        self.event_bus.emit(BUFF_APPLY, {
            "target": getattr(target, "id", "boss"),
            "debuff_id": eff["debuff_id"], "name": skill.name,
            "duration": eff.get("duration", 10),
        })
        return {"debuff": eff["debuff_id"], "target": getattr(target, "id", "boss")}

    def _resolve_control(self, caster: Character, skill: SkillDef, target: Any, eff: dict) -> dict:
        duration = eff.get("duration", 3)
        debuff = Debuff(
            debuff_id=eff.get("control_type", "stun"),
            name=skill.name,
            duration=duration,
            params={"control_type": eff.get("control_type", "stun")},
            source=caster.id,
        )
        target.add_debuff(debuff)

        # Interrupt casting
        if hasattr(target, "casting") and target.casting is not None:
            cast_skill = target.casting.get("skill")
            interrupted_skill = getattr(cast_skill, "name", "") if cast_skill else target.casting.get("skill_name", "")
            target.casting = None
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"{caster.name}打断了{getattr(target, 'name', 'Boss')}的{interrupted_skill}",
            })

        self.threat.add_threat(caster.id, 100)
        return {"control": eff.get("control_type"), "duration": duration}

    def _resolve_dispel(self, caster: Character, skill: SkillDef, target: Character) -> dict:
        removed = target.remove_one_debuff()
        if removed:
            self.event_bus.emit(BUFF_EXPIRE, {
                "target": target.id, "debuff_id": removed.debuff_id,
                "name": removed.name, "reason": "dispel",
            })
            return {"dispelled": removed.debuff_id, "target": target.id}
        return {"dispelled": None, "target": target.id}

    def _resolve_resurrect(self, caster: Character, skill: SkillDef, target: Character, eff: dict) -> dict:
        if target.alive:
            return {"resurrect": False, "reason": "target_alive"}
        hp_pct = eff.get("hp_percent", 0.3)
        target.resurrect(hp_pct)
        self.event_bus.emit(COMBAT_LOG, {
            "message": f"{caster.name}复活了{target.name}",
        })
        return {"resurrect": True, "target": target.id}

    def _resolve_special(self, caster: Character, skill: SkillDef, target: Any, eff: dict) -> dict:
        sid = eff.get("special_id")
        if sid == "deadly_combo":
            # 3 hits, total damage = energy * damage_per_energy
            energy_before = caster.mana  # mana already consumed, use snapshot from engine
            dpe = eff.get("damage_per_energy", 1.5)
            # The mana was already consumed, so we check the stored value
            energy = getattr(caster, "_deadly_combo_energy", caster.max_mana)
            total_damage = int(energy * dpe)
            per_hit = total_damage // 3
            total_actual = 0
            for i in range(3):
                dmg = self._calc_damage(per_hit, caster, target)
                actual = target.take_damage(dmg)
                total_actual += actual
                self.event_bus.emit(DAMAGE, {
                    "source": caster.id, "target": getattr(target, "id", "boss"),
                    "skill": f"致命连击#{i+1}", "amount": actual,
                })
            self.threat.add_threat(caster.id, total_actual)
            return {"damage": total_actual, "hits": 3}
        return {}

    # ------------------------------------------------------------------
    # DOT / HOT processing (called each tick)
    # ------------------------------------------------------------------
    def process_dots(self, characters: list[Character], boss: Any, dt: float) -> None:
        """Process DOT damage on all entities each tick."""
        # DOTs on characters (from boss abilities)
        for char in characters:
            if not char.alive:
                continue
            for debuff in list(char.debuffs):
                dpt = debuff.params.get("damage_per_tick", 0)
                if dpt > 0:
                    actual = char.take_damage(int(dpt * dt))
                    if actual > 0:
                        self.event_bus.emit(DAMAGE, {
                            "source": debuff.source or "boss",
                            "target": char.id,
                            "skill": debuff.name,
                            "amount": actual,
                            "is_dot": True,
                        })
                    if not char.alive:
                        self.event_bus.emit(DEATH, {"target": char.id, "source": debuff.name})

        # DOTs on boss (from player abilities like poison)
        if hasattr(boss, "debuffs"):
            for debuff in list(boss.debuffs):
                dpt = debuff.params.get("damage_per_tick", 0)
                if dpt > 0:
                    actual = boss.take_damage(int(dpt * dt))
                    if actual > 0:
                        source_id = debuff.source or "unknown"
                        self.threat.add_threat(source_id, actual)
                        self.event_bus.emit(DAMAGE, {
                            "source": source_id,
                            "target": "boss",
                            "skill": debuff.name,
                            "amount": actual,
                            "is_dot": True,
                        })

    # ------------------------------------------------------------------
    # Boss attack helpers
    # ------------------------------------------------------------------
    def boss_attack(self, boss: Any, target: Character, damage: int, skill_name: str = "普攻") -> int:
        """Boss attacks a character. Returns actual damage dealt."""
        actual = target.take_damage(damage)
        self.event_bus.emit(DAMAGE, {
            "source": "boss", "target": target.id,
            "skill": skill_name, "amount": actual,
        })
        self.event_bus.emit(COMBAT_LOG, {
            "message": f"[Boss] {skill_name} \u2192 {target.name}  -{actual} (HP:{target.hp}/{target.max_hp})",
            "type": "damage",
        })
        if not target.alive:
            self.event_bus.emit(DEATH, {"target": target.id, "source": skill_name})
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"\u2620 {target.name} \u88AB {skill_name} \u51FB\u6740!",
                "type": "damage",
            })
        return actual

    def boss_aoe_attack(self, boss: Any, targets: list[Character], damage: int, skill_name: str) -> int:
        """Boss AOE attack on all living characters."""
        total = 0
        for t in targets:
            if not t.alive:
                continue
            actual = t.take_damage(damage)
            total += actual
            self.event_bus.emit(DAMAGE, {
                "source": "boss", "target": t.id,
                "skill": skill_name, "amount": actual,
            })
            if not t.alive:
                self.event_bus.emit(DEATH, {"target": t.id, "source": skill_name})
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"\u2620 {t.name} \u88AB {skill_name} \u51FB\u6740!",
                    "type": "damage",
                })
        if total > 0:
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"[Boss] {skill_name} AOE \u2192 \u5168\u4F53 -{damage} (\u603B{total})",
                "type": "damage",
            })
        return total
