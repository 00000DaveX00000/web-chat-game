"""Base agent class — dual-loop architecture: fast auto + slow LLM."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any

from agents.llm_client import LLMClient
from agents.prompts import format_game_state
from agents.tools import build_tools_for_role, tool_name_to_skill_id
from game.skills import get_auto_skills, get_skill

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

AUTO_LOOP_INTERVAL = 0.5   # seconds between auto-skill checks
DEFAULT_LLM_INTERVAL = 5.0 # seconds between LLM queries


class BaseAgent:
    """One agent controls one character (or boss) via dual-loop architecture.

    Two concurrent loops:
      - _auto_loop (fast, 0.5s): executes auto skills + pending LLM decisions
      - _llm_loop (slow, 4-6s): queries LLM for strategic skill decisions

    Parameters
    ----------
    character_id : str
        Unique id ("tank", "healer", ... or "boss").
    role : str
        Role key (tank / healer / mage / rogue / hunter / boss).
    engine : GameEngine
        Reference to the running game engine.
    llm_client : LLMClient
        The LLM client to use for decision making.
    system_prompt : str
        The role-specific system prompt.
    name : str | None
        Display name for logging.
    agent_index : int
        Index for staggering startup delay.
    llm_semaphore : asyncio.Semaphore | None
        Shared semaphore to limit concurrent LLM calls.
    is_boss : bool
        True if this agent controls the Boss entity.
    llm_interval : float
        Seconds between LLM queries.
    """

    def __init__(
        self,
        character_id: str,
        role: str,
        engine: Any,
        llm_client: LLMClient,
        system_prompt: str,
        name: str | None = None,
        agent_index: int = 0,
        llm_semaphore: asyncio.Semaphore | None = None,
        is_boss: bool = False,
        llm_interval: float = DEFAULT_LLM_INTERVAL,
    ) -> None:
        self.character_id = character_id
        self.role = role
        self.engine = engine
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.name = name or character_id
        self.agent_index = agent_index
        self._llm_semaphore = llm_semaphore
        self.is_boss = is_boss
        self.llm_interval = llm_interval
        self._task: asyncio.Task | None = None

        # Auto skills for this role
        self._auto_skills = get_auto_skills(role)

        # LLM tools (exclude auto skills)
        self._tools = build_tools_for_role(role, exclude_auto=True)

        # Pending LLM decisions queue (set by _llm_loop, consumed by _auto_loop)
        # Supports multiple skills per LLM call
        self._pending_decisions: list[dict] = []

        # AI Log: last query and response (read by engine._get_ai_log())
        self.last_query: str = ""
        self.last_response: dict | None = None

        # Track last seen god command
        self._last_seen_command: str = ""

        # Guard: prevent queuing LLM calls when already querying
        self._querying: bool = False

    # ------------------------------------------------------------------
    # Entity accessor
    # ------------------------------------------------------------------
    def _get_entity(self) -> Any:
        """Get the entity (Character or Boss) this agent controls."""
        if self.is_boss:
            return self.engine.boss
        return self.engine.get_character(self.character_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self.run(), name=f"agent-{self.name}")
        return self._task

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    async def run(self) -> None:
        logger.info("[%s] Agent started (role=%s, is_boss=%s)", self.name, self.role, self.is_boss)
        try:
            while True:
                # Wait for engine to start
                while not self.engine.is_running:
                    await asyncio.sleep(0.2)

                # Stagger startup
                stagger = self.agent_index * 0.5
                if stagger > 0:
                    await asyncio.sleep(stagger)

                logger.info("[%s] Engine running, entering dual loop", self.name)

                # Reset state for new game
                self._pending_decisions = []
                self.last_query = ""
                self.last_response = None
                self._last_seen_command = ""
                self._querying = False

                # Run both loops concurrently until game ends
                auto_task = asyncio.create_task(self._auto_loop(), name=f"auto-{self.name}")
                llm_task = asyncio.create_task(self._llm_loop(), name=f"llm-{self.name}")
                try:
                    await asyncio.gather(auto_task, llm_task)
                except asyncio.CancelledError:
                    auto_task.cancel()
                    llm_task.cancel()
                    raise

                logger.info("[%s] Game ended, waiting for next start", self.name)

        except asyncio.CancelledError:
            logger.info("[%s] Agent cancelled", self.name)
        except Exception:
            logger.exception("[%s] Agent crashed", self.name)
        finally:
            logger.info("[%s] Agent stopped", self.name)

    # ------------------------------------------------------------------
    # Auto loop (fast, 0.5s)
    # ------------------------------------------------------------------
    async def _auto_loop(self) -> None:
        """Fast loop: execute pending LLM decisions or auto skills."""
        while self.engine.is_running:
            try:
                entity = self._get_entity()
                if entity and getattr(entity, "alive", True) and entity.gcd_ready():
                    # Priority 1: Execute pending LLM decisions (multi-skill queue)
                    if self._pending_decisions:
                        decision = self._pending_decisions[0]
                        consumed = self._try_execute_decision(entity, decision, source="ai")
                        if consumed:
                            self._pending_decisions.pop(0)
                        else:
                            # Decision failed (skill on CD etc), discard and try auto
                            self._pending_decisions.pop(0)
                            self._try_auto_skill(entity)
                    else:
                        # Priority 2: Execute auto skill
                        self._try_auto_skill(entity)
            except Exception:
                logger.exception("[%s] Error in auto loop", self.name)

            await asyncio.sleep(AUTO_LOOP_INTERVAL)

    # ------------------------------------------------------------------
    # LLM loop (slow, 4-6s)
    # ------------------------------------------------------------------
    async def _llm_loop(self) -> None:
        """Slow loop: query LLM for strategic decisions.

        All agents autonomously query LLM every random 3-8 seconds.
        God commands trigger immediate extra query for players who "hear" it
        (random chance — some agents may miss the command).
        Boss always hears commands and uses them to counter-attack.
        If agent is already querying, new requests are ignored (no queue).
        """
        # Initial delay to let auto loop start
        await asyncio.sleep(1.0)

        while self.engine.is_running:
            try:
                entity = self._get_entity()
                if entity and getattr(entity, "alive", True):
                    # Check for new god command (only if not already querying)
                    current_cmd = self.engine.god_command_text
                    if current_cmd and current_cmd != self._last_seen_command:
                        self._last_seen_command = current_cmd
                        if not self._querying:
                            if self.is_boss:
                                # Boss ALWAYS hears and reacts to counter
                                await self._query_llm()
                            elif random.random() < 0.7:
                                # Players have 70% chance to "hear" the command
                                logger.info("[%s] Heard team leader command: %s", self.name, current_cmd[:30])
                                await self._query_llm()
                            else:
                                logger.info("[%s] Missed team leader command", self.name)

                    # All agents autonomously query LLM (skip if already querying)
                    if not self._querying:
                        await self._query_llm()
            except Exception:
                logger.exception("[%s] Error in LLM loop", self.name)

            # Boss: 2-4s (aggressive), Players: 3-8s
            if self.is_boss:
                await asyncio.sleep(random.uniform(2.0, 4.0))
            else:
                await asyncio.sleep(random.uniform(3.0, 8.0))

    async def _query_llm(self) -> None:
        """Query LLM and store decision as pending.

        Uses _querying guard: if already querying, silently returns.
        This prevents command queue buildup.
        """
        if self._querying:
            return
        self._querying = True
        try:
            state = self.engine.get_state_for_agent()
            user_prompt = format_game_state(state, self.character_id, is_boss=self.is_boss)

            # Store query for AI Log
            self.last_query = user_prompt

            # Call LLM with semaphore
            decision = None
            if self._llm_semaphore:
                async with self._llm_semaphore:
                    decision = await self.llm_client.get_decision_with_tools(
                        self.system_prompt, user_prompt, self._tools
                    )
                    await asyncio.sleep(0.2)
            else:
                decision = await self.llm_client.get_decision_with_tools(
                    self.system_prompt, user_prompt, self._tools
                )

            if decision and isinstance(decision, list) and len(decision) > 0:
                # Cap at 3 skills max per LLM call
                self._pending_decisions = list(decision[:3])
                # Store first decision for AI Log display
                first = decision[0]
                skill_id = first.get("skill_id", 0)
                skill_def = get_skill(skill_id)
                # Build summary of all decisions for reason display
                all_skills = []
                for d in decision:
                    sid = d.get("skill_id", 0)
                    sdef = get_skill(sid)
                    sname = sdef.name if sdef else f"skill_{sid}"
                    all_skills.append(sname)
                reason_parts = first.get("reason", "")
                if len(decision) > 1:
                    reason_parts = f"[{len(decision)}技能] {reason_parts}"
                self.last_response = {
                    "tool_name": first.get("tool_name", ""),
                    "skill_name": skill_def.name if skill_def else first.get("tool_name", ""),
                    "skill_id": skill_id,
                    "target": first.get("target", ""),
                    "reason": reason_parts,
                    "all_skills": all_skills,
                    "time": time.time(),
                }
                logger.debug(
                    "[%s] LLM decisions: %s",
                    self.name,
                    ", ".join(f"skill={d.get('skill_id', 0)} target={d.get('target', '')}" for d in decision),
                )
            elif decision and isinstance(decision, dict):
                # Legacy: single decision dict
                self._pending_decisions = [decision]
                skill_id = decision.get("skill_id", 0)
                skill_def = get_skill(skill_id)
                self.last_response = {
                    "tool_name": decision.get("tool_name", ""),
                    "skill_name": skill_def.name if skill_def else decision.get("tool_name", ""),
                    "skill_id": skill_id,
                    "target": decision.get("target", ""),
                    "reason": decision.get("reason", ""),
                    "time": time.time(),
                }
            else:
                self.last_response = {"tool_name": "", "reason": "LLM returned None", "time": time.time()}
        finally:
            self._querying = False

    # ------------------------------------------------------------------
    # Execute a decision (LLM or auto)
    # ------------------------------------------------------------------
    def _try_execute_decision(self, entity: Any, decision: dict, source: str = "ai") -> bool:
        """Try to execute a skill decision. Returns True if submitted."""
        skill_id = decision.get("skill_id", 0)
        target = decision.get("target", "")
        reason = decision.get("reason", "")
        tool_name = decision.get("tool_name", "")

        if not target:
            target = self._default_target(entity)

        ok = self.engine.submit_action(self.character_id, skill_id, target)
        if ok:
            skill_def = get_skill(skill_id)
            skill_name = skill_def.name if skill_def else f"skill_{skill_id}"
            god_cmd = self.engine.god_command_text

            entity.last_action = {
                "skill_name": skill_name,
                "target": target,
                "reason": reason,
                "source": source,
                "tool_name": tool_name,
                "time": time.time(),
                "instruction": god_cmd,
            }

            # Emit combat log
            from game.events import COMBAT_LOG
            entity_name = getattr(entity, "name", self.character_id)
            if source == "ai":
                self.engine.event_bus.emit(COMBAT_LOG, {
                    "message": f"\U0001f916 [{entity_name}] 调用 {skill_name}(target={target}) \"{reason}\"",
                    "type": "ai_decision",
                })
            return True
        return False

    # ------------------------------------------------------------------
    # Auto skill execution
    # ------------------------------------------------------------------
    def _try_auto_skill(self, entity: Any) -> None:
        """Execute the first available auto skill."""
        for skill_def in self._auto_skills:
            can_use, _ = entity.can_use_skill(skill_def)
            if not can_use:
                continue

            # Check mana (for non-boss)
            if not self.is_boss and hasattr(entity, "mana"):
                if entity.mana < skill_def.mana_cost:
                    continue

            target = self._auto_target(entity, skill_def)
            ok = self.engine.submit_action(self.character_id, skill_def.id, target)
            if ok:
                entity.last_action = {
                    "skill_name": skill_def.name,
                    "target": target,
                    "reason": "",
                    "source": "auto",
                    "tool_name": None,
                    "time": time.time(),
                    "instruction": "",
                }
                return

    # ------------------------------------------------------------------
    # Target selection
    # ------------------------------------------------------------------
    def _auto_target(self, entity: Any, skill_def: Any) -> str:
        """Select target for auto skill."""
        if self.is_boss:
            return self._boss_auto_target()

        if self.role == "healer":
            return self._healer_auto_target()

        # Other player roles: target boss
        return "boss"

    def _boss_auto_target(self) -> str:
        """Boss auto targets highest-threat player, with 30% chance to pick random."""
        living = [cid for cid, c in self.engine.characters.items() if c.alive]
        if not living:
            return "tank"

        # 30% chance: random target (makes boss unpredictable)
        if random.random() < 0.3:
            return random.choice(living)

        # 70%: highest threat
        threat = self.engine.combat.threat.get_threat_list()
        if threat:
            sorted_threat = sorted(threat.items(), key=lambda x: -x[1])
            for tid, _ in sorted_threat:
                char = self.engine.get_character(tid)
                if char and char.alive:
                    return tid

        return random.choice(living)

    def _healer_auto_target(self) -> str:
        """Healer auto targets lowest-HP living ally."""
        lowest_id = "tank"
        lowest_pct = 999.0
        for cid, char in self.engine.characters.items():
            if char.alive and char.max_hp > 0:
                pct = char.hp / char.max_hp
                if pct < lowest_pct:
                    lowest_pct = pct
                    lowest_id = cid
        return lowest_id

    def _default_target(self, entity: Any) -> str:
        """Default target when LLM doesn't specify one."""
        if self.is_boss:
            return self._boss_auto_target()
        if self.role == "healer":
            return self._healer_auto_target()
        return "boss"
