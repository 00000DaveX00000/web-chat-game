"""Game engine: main loop, state management, action resolution."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Callable

from game.boss import Boss
from game.character import Character, Debuff, create_character
from game.combat import CombatSystem
from game.events import (
    BOSS_CAST, COMBAT_LOG, DAMAGE, DEATH, DEFEAT, VICTORY, EventBus,
)
from game.skills import SKILLS, get_skill

logger = logging.getLogger(__name__)

TICK_INTERVAL = 0.5  # 500ms per tick


class GameEngine:
    """Core game engine driving the raid encounter."""

    def __init__(self, boss_config: dict | None = None) -> None:
        self.event_bus = EventBus()
        self.events = self.event_bus  # alias for main.py compatibility
        self.combat = CombatSystem(self.event_bus)
        self.boss = Boss(self.event_bus)

        # Create the 5 characters
        self.characters: dict[str, Character] = {}
        for role in ("tank", "healer", "mage", "rogue", "hunter"):
            char = create_character(role, role)
            self.characters[role] = char

        # Pending actions submitted by agents: list of (character_id, skill_id, target_id)
        self._pending_actions: list[tuple[str, int, str]] = []

        # God commands queue
        self._god_commands: list[str] = []
        # Latest god command text (for agent prompts)
        self.god_command_text: str = ""
        self._god_command_time: float = 0.0  # game_time when set

        # Game state
        self.running = False
        self.tick_count = 0
        self.game_time = 0.0  # seconds elapsed
        self.result: str | None = None  # "victory" | "defeat"

        # Callbacks for state broadcast
        self._on_state_change: list[Callable[[dict], None]] = []
        self._on_combat_log: list[Callable[[dict], None]] = []

        # Log index for incremental fetching
        self._last_log_index = 0

        # Agent references for AI Log
        self._agents: list[Any] = []

    @property
    def is_running(self) -> bool:
        return self.running

    # ------------------------------------------------------------------
    # Agent injection (for AI Log)
    # ------------------------------------------------------------------
    def set_agents(self, agents: list[Any]) -> None:
        """Store agent references for AI Log collection."""
        self._agents = agents

    def _get_ai_log(self) -> list[dict[str, Any]]:
        """Collect last_query/last_response from all agents."""
        logs = []
        for agent in self._agents:
            logs.append({
                "id": agent.character_id,
                "name": agent.name,
                "role": agent.role,
                "is_boss": getattr(agent, "is_boss", False),
                "last_query": getattr(agent, "last_query", ""),
                "last_response": getattr(agent, "last_response", None),
            })
        return logs

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start_game(self) -> None:
        """Initialize and start the game loop."""
        if self.running:
            return

        # If previous game ended (boss dead / all dead), do a full reset first
        if self.result or not self.boss.alive:
            self.reset_game()

        self.running = True
        self.tick_count = 0
        self.game_time = 0.0
        self.result = None
        self._pending_actions.clear()
        self._god_commands.clear()

        self.event_bus.emit(COMBAT_LOG, {
            "message": "=== 战斗开始! 熔火之王拉格纳罗斯 ===",
        })

        logger.info("Game started")
        await self.game_loop()

    def stop_game(self) -> None:
        """Stop the running game."""
        if not self.running:
            return
        self.running = False
        self.result = self.result or "stopped"
        self.event_bus.emit(COMBAT_LOG, {
            "message": "=== 战斗已停止 ===",
        })
        logger.info("Game stopped by user")

    def reset_game(self) -> None:
        """Reset all game state for a fresh start."""
        self.running = False
        self.tick_count = 0
        self.game_time = 0.0
        self.result = None
        self._pending_actions.clear()
        self._god_commands.clear()
        self.god_command_text = ""
        self._last_log_index = 0
        self.event_bus._log.clear()

        # Reset boss
        self.boss = Boss(self.event_bus)

        # Reset characters
        for role in list(self.characters.keys()):
            self.characters[role] = create_character(role, role)

        # Reset combat system
        self.combat = CombatSystem(self.event_bus)

        logger.info("Game reset")

    async def game_loop(self) -> None:
        """Main game loop running at TICK_INTERVAL."""
        while self.running:
            tick_start = time.monotonic()
            self.process_tick()

            if self.result:
                self.running = False
                break

            # Sleep for remaining time in tick
            elapsed = time.monotonic() - tick_start
            sleep_time = max(0, TICK_INTERVAL - elapsed)
            await asyncio.sleep(sleep_time)

        logger.info("Game loop ended. Result: %s", self.result)

    def process_tick(self) -> None:
        """Process one game tick."""
        dt = TICK_INTERVAL
        self.tick_count += 1
        self.game_time += dt

        # 1. Process timers (GCD, cooldowns, buff/debuff durations) - characters + boss
        self._tick_timers(dt)

        # 2. Process boss passive mechanics (fissures, traps, adds)
        self._process_boss_passive(dt)

        # 3. Process DOTs and HOTs
        self.combat.process_dots(list(self.characters.values()), self.boss, dt)

        # 4. Process casting completions (characters + boss)
        self._process_casts(dt)

        # 5. Check phase transitions
        self.boss.check_phase_transition()

        # 6. Process god commands (+ expire old commands after 15s)
        self._process_god_commands()
        if self.god_command_text and self.game_time - self._god_command_time > 15.0:
            self.god_command_text = ""

        # 7. Collect and resolve all pending actions (characters + boss unified)
        self._process_pending_actions()

        # 8. Threat table tick
        self.combat.threat.tick(dt)

        # 9. Check win/lose conditions
        self._check_end_conditions()

        # 10. Broadcast state (includes AI Log)
        self._broadcast_state()

    # ------------------------------------------------------------------
    # Agent interface
    # ------------------------------------------------------------------
    def submit_action(self, character_id: str, skill_id: int, target: str = "") -> bool:
        """Submit a player or boss action. Returns True if accepted into queue."""
        # Get entity (character or boss)
        if character_id == "boss":
            entity = self.boss
        else:
            entity = self.characters.get(character_id)

        if not entity:
            return False

        skill = get_skill(skill_id)
        if not skill:
            return False

        can_use, reason = entity.can_use_skill(skill)
        if not can_use:
            return False

        self._pending_actions.append((character_id, skill_id, target))
        return True

    def submit_god_command(self, command: str) -> None:
        """Submit a god/DM command."""
        self._god_commands.append(command)
        self.god_command_text = command
        self._god_command_time = self.game_time

    def get_character(self, character_id: str) -> Character | None:
        return self.characters.get(character_id)

    def get_game_state(self) -> dict[str, Any]:
        """Return game state snapshot with incremental combat log."""
        new_logs = self.event_bus.get_log(self._last_log_index)
        self._last_log_index = len(self.event_bus._log)

        living = [c for c in self.characters.values() if c.alive]

        return {
            "tick": self.tick_count,
            "game_time": round(self.game_time, 1),
            "running": self.running,
            "result": self.result,
            "boss": self.boss.to_dict(),
            "boss_card": self.boss.to_card_dict(),
            "characters": {cid: c.to_dict() for cid, c in self.characters.items()},
            "threat": self.combat.threat.get_threat_list(),
            "adds": [a.to_dict() for a in self.boss.adds if a.alive],
            "living_count": len(living),
            "combat_log": new_logs,
            "god_command": self.god_command_text,
            "ai_log": self._get_ai_log(),
        }

    def get_state_for_agent(self) -> dict[str, Any]:
        """Return game state snapshot for agent prompts (does NOT consume logs)."""
        living = [c for c in self.characters.values() if c.alive]

        return {
            "tick": self.tick_count,
            "game_time": round(self.game_time, 1),
            "running": self.running,
            "result": self.result,
            "boss": self.boss.to_dict(),
            "boss_card": self.boss.to_card_dict(),
            "characters": {cid: c.to_dict() for cid, c in self.characters.items()},
            "threat": self.combat.threat.get_threat_list(),
            "adds": [a.to_dict() for a in self.boss.adds if a.alive],
            "living_count": len(living),
            "god_command": self.god_command_text,
        }

    def get_full_state(self) -> dict[str, Any]:
        """Full state including all logs (for initial connection)."""
        living = [c for c in self.characters.values() if c.alive]

        return {
            "tick": self.tick_count,
            "game_time": round(self.game_time, 1),
            "running": self.running,
            "result": self.result,
            "boss": self.boss.to_dict(),
            "boss_card": self.boss.to_card_dict(),
            "characters": {cid: c.to_dict() for cid, c in self.characters.items()},
            "threat": self.combat.threat.get_threat_list(),
            "adds": [a.to_dict() for a in self.boss.adds if a.alive],
            "living_count": len(living),
            "combat_log": self.event_bus.get_log(),
            "god_command": self.god_command_text,
            "ai_log": self._get_ai_log(),
        }

    def register_state_callback(self, cb: Callable[[dict], None]) -> None:
        self._on_state_change.append(cb)

    def unregister_state_callback(self, cb: Callable[[dict], None]) -> None:
        try:
            self._on_state_change.remove(cb)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Internal processing
    # ------------------------------------------------------------------
    def _tick_timers(self, dt: float) -> None:
        """Advance character and boss timers."""
        # Character timers
        for char in self.characters.values():
            expired = char.tick_timers(dt)
            for exp in expired:
                kind, bid = exp.split(":", 1)
                self.event_bus.emit(
                    "buff_expire",
                    {"target": char.id, f"{kind}_id": bid, "reason": "expired"},
                )
        # Boss timers
        boss_expired = self.boss.tick_timers(dt)
        for exp in boss_expired:
            kind, bid = exp.split(":", 1)
            self.event_bus.emit(
                "buff_expire",
                {"target": "boss", f"{kind}_id": bid, "reason": "expired"},
            )

    def _process_boss_passive(self, dt: float) -> None:
        """Tick boss passive mechanics (fissures, traps, adds)."""
        self.boss.tick_passive(dt, list(self.characters.values()))

    def _process_casts(self, dt: float) -> None:
        """Check if any character or boss finished casting."""
        # Character casts
        for char in self.characters.values():
            if not char.casting:
                continue
            if char.casting["remaining"] <= 0:
                skill = char.casting["skill"]
                target_id = char.casting["target"]
                char.casting = None
                self._execute_skill(char, skill, target_id)

        # Boss casts
        if self.boss.casting and self.boss.casting["remaining"] <= 0:
            skill = self.boss.casting["skill"]
            target_id = self.boss.casting["target"]
            self.boss.casting = None
            self._execute_boss_skill(skill, target_id)

    def _process_pending_actions(self) -> None:
        """Resolve all queued actions (characters + boss unified)."""
        actions = list(self._pending_actions)
        self._pending_actions.clear()

        for char_id, skill_id, target_id in actions:
            # Get entity
            if char_id == "boss":
                entity = self.boss
            else:
                entity = self.characters.get(char_id)
            skill = get_skill(skill_id)
            if not entity or not skill:
                continue

            # Re-check usability (state may have changed)
            can_use, reason = entity.can_use_skill(skill)
            if not can_use:
                continue

            # Consume resources
            if skill.id == 404:
                entity._deadly_combo_energy = entity.mana

            entity.consume_mana(skill)
            entity.trigger_gcd()
            entity.set_cooldown(skill)

            # If skill has a cast time, start casting
            if skill.cast_time > 0:
                entity.start_cast(skill, target_id)
                entity_name = getattr(entity, "name", char_id)
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"[{entity_name}] 开始施放 {skill.name}...",
                })
                if char_id == "boss":
                    self.event_bus.emit(BOSS_CAST, {
                        "skill": skill.name, "cast_time": skill.cast_time,
                        "message": f"{skill.name}正在读条! {'必须打断!' if skill.id == 607 else ''}",
                    })
            else:
                if char_id == "boss":
                    self._execute_boss_skill(skill, target_id)
                else:
                    self._execute_skill(entity, skill, target_id)

    def _execute_skill(self, char: Character, skill, target_id: str) -> None:
        """Execute a resolved player skill."""
        # Determine target
        target = None
        all_allies = [c for c in self.characters.values() if c.alive]
        all_enemies: list = [self.boss] + [a for a in self.boss.adds if a.alive]

        if skill.target_type == "enemy":
            if target_id == "boss" or not target_id:
                target = self.boss
            else:
                # Could be an add
                for add in self.boss.adds:
                    if add.id == target_id and add.alive:
                        target = add
                        break
                if target is None:
                    target = self.boss
        elif skill.target_type == "self":
            target = char
        elif skill.target_type == "ally":
            target = self.characters.get(target_id, char)
        elif skill.target_type in ("ally_all", "enemy_all"):
            target = None  # handled by combat system

        result = self.combat.resolve_skill(
            caster=char,
            skill=skill,
            target=target,
            all_allies=list(self.characters.values()),
            all_enemies=all_enemies,
        )

        # Build descriptive combat log message
        target_name = getattr(target, 'name', target_id) if target else '全体'
        detail = ""
        if result:
            if "damage" in result:
                detail = f" -{result['damage']}"
            elif "total_damage" in result:
                detail = f" -{result['total_damage']}"
            elif "heal" in result:
                detail = f" +{result['heal']}"
            elif "total_heal" in result:
                detail = f" +{result['total_heal']}"
            elif "taunt_duration" in result:
                detail = f" 强制攻击{result['taunt_duration']}秒"
            elif "buff" in result:
                detail = f" [{result['buff']}]"
            elif "debuff" in result:
                detail = f" [{result['debuff']}]"

        self.event_bus.emit(COMBAT_LOG, {
            "message": f"[{char.name}] 使用 {skill.name} \u2192 {target_name}{detail}",
        })

    def _execute_boss_skill(self, skill, target_id: str) -> None:
        """Execute a boss skill."""
        living = [c for c in self.characters.values() if c.alive]
        target = self.characters.get(target_id)

        if skill.id == 601:  # 普攻
            if target and target.alive:
                damage = random.randint(self.boss.attack_min, self.boss.attack_max)
                self.combat.boss_attack(self.boss, target, damage, "普攻")

        elif skill.id == 602:  # 顺劈斩
            if target and target.alive:
                dmg = skill.effects.get("base_damage", 700)
                self.combat.boss_attack(self.boss, target, dmg, "顺劈斩")

        elif skill.id == 603:  # 岩浆喷射
            if target and target.alive:
                dmg = skill.effects.get("base_damage", 450)
                self.combat.boss_attack(self.boss, target, dmg, "岩浆喷射")
                dot = Debuff(
                    debuff_id="magma_burn",
                    name="岩浆灼烧",
                    duration=skill.effects.get("dot_duration", 5),
                    params={"damage_per_tick": skill.effects.get("dot_damage", 60), "source": "boss"},
                    source="boss",
                )
                target.add_debuff(dot)
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"岩浆喷射命中{target.name}! 灼烧DOT {skill.effects.get('dot_damage', 60)}/s",
                })

        elif skill.id == 604:  # 烈焰风暴
            aoe_dmg = skill.effects.get("base_damage", 400)
            self.combat.boss_aoe_attack(self.boss, living, aoe_dmg, "烈焰风暴")
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"烈焰风暴! 全体受到{aoe_dmg}伤害!",
            })

        elif skill.id == 605:  # 召唤元素
            self.boss.summon_adds(skill.effects.get("count", 2))
            self.event_bus.emit(COMBAT_LOG, {
                "message": "拉格纳罗斯召唤了2个熔岩元素!",
            })

        elif skill.id == 606:  # 熔岩裂隙
            if target and target.alive:
                fissure = {
                    "target_id": target.id,
                    "duration": skill.effects.get("dot_duration", 6.0),
                    "damage_per_tick": skill.effects.get("dot_damage", 150),
                    "name": "熔岩裂隙",
                }
                self.boss.fissures.append(fissure)
                self.event_bus.emit(BOSS_CAST, {"skill": "熔岩裂隙", "target": target.id})
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"熔岩裂隙出现在{target.name}脚下!",
                })

        elif skill.id == 607:  # 灭世之炎 (cast completed)
            apoc_dmg = skill.effects.get("base_damage", 8000)
            self.combat.boss_aoe_attack(self.boss, living, apoc_dmg, "灭世之炎")
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"灭世之炎释放! 全体受到{apoc_dmg}伤害!",
            })

        elif skill.id == 608:  # 熔岩陷阱
            if target and target.alive:
                trap = {
                    "target_id": target.id,
                    "countdown": skill.effects.get("countdown", 5.0),
                    "damage": skill.effects.get("damage", 1500),
                    "name": "熔岩陷阱",
                }
                self.boss.traps.append(trap)
                self.event_bus.emit(BOSS_CAST, {
                    "skill": "熔岩陷阱", "target": target.id,
                    "message": f"熔岩陷阱标记了{target.name}! 5秒后爆炸!",
                })
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"熔岩陷阱标记了{target.name}! 5秒后爆炸!",
                })

    def _process_god_commands(self) -> None:
        """Process DM/God commands."""
        commands = list(self._god_commands)
        self._god_commands.clear()

        for cmd in commands:
            self._execute_god_command(cmd)

    def _execute_god_command(self, command: str) -> None:
        """Parse and execute a god command."""
        parts = command.strip().split()
        if not parts:
            return

        cmd = parts[0].lower()

        if cmd == "damage" and len(parts) >= 3:
            target_id = parts[1]
            amount = int(parts[2])
            target = self.characters.get(target_id)
            if target:
                target.take_damage(amount)
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"[God] {target.name}受到{amount}伤害",
                })
            elif target_id == "boss":
                self.boss.take_damage(amount)
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"[God] Boss受到{amount}伤害",
                })

        elif cmd == "heal" and len(parts) >= 3:
            target_id = parts[1]
            amount = int(parts[2])
            target = self.characters.get(target_id)
            if target:
                target.receive_heal(amount)
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"[God] {target.name}恢复{amount}HP",
                })

        elif cmd == "kill" and len(parts) >= 2:
            target_id = parts[1]
            if target_id == "boss":
                self.boss.hp = 0
                self.boss.alive = False
            else:
                target = self.characters.get(target_id)
                if target:
                    target.die()

        elif cmd == "resurrect" and len(parts) >= 2:
            target_id = parts[1]
            target = self.characters.get(target_id)
            if target:
                target.resurrect(1.0)
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"[God] {target.name}被复活(满血)",
                })

        elif cmd == "phase" and len(parts) >= 2:
            phase = int(parts[1])
            if phase in (1, 2, 3):
                self.boss.phase = phase
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"[God] 强制切换到Phase {phase}",
                })

        elif cmd == "buff" and len(parts) >= 3:
            target_id = parts[1]
            buff_id = parts[2]
            duration = float(parts[3]) if len(parts) > 3 else 30
            target = self.characters.get(target_id)
            if target:
                from game.character import Buff
                target.add_buff(Buff(buff_id=buff_id, name=buff_id, duration=duration))

        elif cmd == "say":
            message = " ".join(parts[1:])
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"[DM] {message}",
            })

        elif cmd == "pause":
            self.running = False
            self.event_bus.emit(COMBAT_LOG, {"message": "[God] 游戏暂停"})

        elif cmd == "resume":
            self.event_bus.emit(COMBAT_LOG, {"message": "[God] 游戏恢复"})

        else:
            # Unrecognized commands are treated as natural language broadcast
            self.god_command_text = command
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"[上帝指令] {command}",
            })

    # ------------------------------------------------------------------
    # Win/Lose conditions
    # ------------------------------------------------------------------
    def _check_end_conditions(self) -> None:
        if not self.boss.alive:
            self.result = "victory"
            self.event_bus.emit(VICTORY, {
                "message": "胜利! 拉格纳罗斯被击败了!",
                "time": round(self.game_time, 1),
                "ticks": self.tick_count,
            })
            return

        all_dead = all(not c.alive for c in self.characters.values())
        if all_dead:
            self.result = "defeat"
            self.event_bus.emit(DEFEAT, {
                "message": "团灭! 所有玩家阵亡!",
                "boss_hp": self.boss.hp,
                "boss_hp_percent": round(self.boss.hp_percent * 100, 1),
            })

    # ------------------------------------------------------------------
    # State broadcast
    # ------------------------------------------------------------------
    def _broadcast_state(self) -> None:
        state = self.get_game_state()
        # Emit tick_complete event for server broadcast (includes combat_log)
        self.event_bus.emit("tick_complete", state)
        # Check game over
        if self.result:
            self.event_bus.emit("game_over", {
                "result": self.result,
                "message": state.get("combat_log", [{}])[-1].get("message", "") if state.get("combat_log") else "",
            })
        for cb in self._on_state_change:
            try:
                cb(state)
            except Exception:
                logger.exception("Error in state change callback")
