"""Game engine: main loop, state management, action resolution."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from game.boss import Boss
from game.character import Character, Debuff, create_character
from game.combat import CombatSystem
from game.events import (
    COMBAT_LOG, DAMAGE, DEATH, DEFEAT, VICTORY, EventBus,
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

    @property
    def is_running(self) -> bool:
        return self.running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start_game(self) -> None:
        """Initialize and start the game loop."""
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

        # 1. Process timers (GCD, cooldowns, buff/debuff durations)
        self._tick_timers(dt)

        # 2. Process DOTs and HOTs
        self.combat.process_dots(list(self.characters.values()), self.boss, dt)

        # 3. Process casting completions
        self._process_casts(dt)

        # 4. Boss AI
        self._process_boss_ai(dt)

        # 5. Check phase transitions
        self.boss.check_phase_transition()

        # 6. Process god commands
        self._process_god_commands()

        # 7. Collect and resolve player actions
        self._process_pending_actions()

        # 8. Threat table tick
        self.combat.threat.tick(dt)

        # 9. Check win/lose conditions
        self._check_end_conditions()

        # 10. Broadcast state
        self._broadcast_state()

    # ------------------------------------------------------------------
    # Agent interface
    # ------------------------------------------------------------------
    def submit_action(self, character_id: str, skill_id: int, target: str = "") -> bool:
        """Submit a player action. Returns True if accepted into queue."""
        char = self.characters.get(character_id)
        if not char:
            return False

        skill = get_skill(skill_id)
        if not skill:
            return False

        can_use, reason = char.can_use_skill(skill)
        if not can_use:
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"[{char.name}] 无法使用{skill.name}: {reason}",
            })
            return False

        self._pending_actions.append((character_id, skill_id, target))
        return True

    def submit_god_command(self, command: str) -> None:
        """Submit a god/DM command."""
        self._god_commands.append(command)
        self.god_command_text = command

    def get_character(self, character_id: str) -> Character | None:
        return self.characters.get(character_id)

    def get_game_state(self) -> dict[str, Any]:
        """Return complete game state snapshot for agents and websockets."""
        new_logs = self.event_bus.get_log(self._last_log_index)
        self._last_log_index = len(self.event_bus._log)

        living = [c for c in self.characters.values() if c.alive]

        return {
            "tick": self.tick_count,
            "game_time": round(self.game_time, 1),
            "running": self.running,
            "result": self.result,
            "boss": self.boss.to_dict(),
            "characters": {cid: c.to_dict() for cid, c in self.characters.items()},
            "threat": self.combat.threat.get_threat_list(),
            "adds": [a.to_dict() for a in self.boss.adds if a.alive],
            "living_count": len(living),
            "combat_log": new_logs,
            "god_command": self.god_command_text,
        }

    def get_full_state(self) -> dict[str, Any]:
        """Full state including all logs (for initial connection)."""
        state = self.get_game_state()
        state["combat_log"] = self.event_bus.get_log()
        return state

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
        """Advance character timers."""
        for char in self.characters.values():
            expired = char.tick_timers(dt)
            for exp in expired:
                kind, bid = exp.split(":", 1)
                self.event_bus.emit(
                    "buff_expire",
                    {"target": char.id, f"{kind}_id": bid, "reason": "expired"},
                )

    def _process_casts(self, dt: float) -> None:
        """Check if any character finished casting."""
        for char in self.characters.values():
            if not char.casting:
                continue
            if char.casting["remaining"] <= 0:
                skill = char.casting["skill"]
                target_id = char.casting["target"]
                char.casting = None
                self._execute_skill(char, skill, target_id)

    def _process_boss_ai(self, dt: float) -> None:
        """Run boss AI and resolve its actions."""
        alive_ids = {c.id for c in self.characters.values() if c.alive}
        threat_top = self.combat.threat.get_top_threat(alive_ids)
        actions = self.boss.tick_ai(dt, list(self.characters.values()), threat_top)

        for action in actions:
            self._resolve_boss_action(action)

    def _resolve_boss_action(self, action: dict) -> None:
        atype = action.get("type", "")
        target_id = action.get("target", "")
        target = self.characters.get(target_id)
        living = [c for c in self.characters.values() if c.alive]

        if atype == "auto_attack":
            if target and target.alive:
                self.combat.boss_attack(self.boss, target, action["damage"], action.get("name", "普攻"))

        elif atype == "cleave":
            if target and target.alive:
                self.combat.boss_attack(self.boss, target, action["damage"], action["name"])

        elif atype == "magma_blast":
            if target and target.alive:
                self.combat.boss_attack(self.boss, target, action["damage"], action["name"])
                # Apply burn DOT
                dot = Debuff(
                    debuff_id="magma_burn",
                    name="岩浆灼烧",
                    duration=action["dot_duration"],
                    params={"damage_per_tick": action["dot_damage"], "source": "boss"},
                    source="boss",
                )
                target.add_debuff(dot)
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"岩浆喷射命中{target.name}! 灼烧DOT {action['dot_damage']}/s 持续{action['dot_duration']}秒",
                })

        elif atype == "firestorm":
            self.combat.boss_aoe_attack(self.boss, living, action["damage"], action["name"])
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"烈焰风暴! 全体受到{action['damage']}伤害!",
            })

        elif atype == "summon":
            self.event_bus.emit(COMBAT_LOG, {
                "message": "拉格纳罗斯召唤了2个熔岩元素!",
            })

        elif atype == "apocalypse_start":
            self.event_bus.emit(COMBAT_LOG, {
                "message": "!! 灭世之炎读条开始(3秒)! 必须打断 !!",
            })

        elif atype == "cast_complete":
            if action.get("name") == "灭世之炎":
                # Wipe if not interrupted
                self.combat.boss_aoe_attack(self.boss, living, 8000, "灭世之炎")
                self.event_bus.emit(COMBAT_LOG, {
                    "message": "灭世之炎释放! 全体受到8000伤害!",
                })

        elif atype == "enrage":
            pass  # Already handled in boss.tick_ai

    def _process_pending_actions(self) -> None:
        """Resolve all queued player actions."""
        actions = list(self._pending_actions)
        self._pending_actions.clear()

        for char_id, skill_id, target_id in actions:
            char = self.characters.get(char_id)
            skill = get_skill(skill_id)
            if not char or not skill:
                continue

            # Re-check usability (state may have changed)
            can_use, reason = char.can_use_skill(skill)
            if not can_use:
                continue

            # Consume resources
            # For deadly combo, save energy before consuming
            if skill.id == 404:
                char._deadly_combo_energy = char.mana

            char.consume_mana(skill)
            char.trigger_gcd()
            char.set_cooldown(skill)

            # If skill has a cast time, start casting
            if skill.cast_time > 0:
                char.start_cast(skill, target_id)
                self.event_bus.emit(COMBAT_LOG, {
                    "message": f"[{char.name}] 开始施放 {skill.name}...",
                })
            else:
                self._execute_skill(char, skill, target_id)

    def _execute_skill(self, char: Character, skill, target_id: str) -> None:
        """Execute a resolved skill."""
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

        self.event_bus.emit(COMBAT_LOG, {
            "message": f"[{char.name}] 使用 {skill.name}" +
                      (f" -> {result.get('damage', result.get('heal', result.get('buff', '')))}") if result else "",
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
            # damage <target> <amount>
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
            # Will be called to restart the loop externally
            self.event_bus.emit(COMBAT_LOG, {"message": "[God] 游戏恢复"})

        else:
            self.event_bus.emit(COMBAT_LOG, {
                "message": f"[God] 未知命令: {command}",
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
        # Emit tick_complete event for server broadcast
        self.event_bus.emit("tick_complete", state)
        # Emit combat_log events for new logs
        for log_entry in state.get("combat_log", []):
            self.event_bus.emit("combat_log_broadcast", log_entry)
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
