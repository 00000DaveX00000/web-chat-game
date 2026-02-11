"""Base agent class — observe / decide / act loop powered by an LLM."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from agents.llm_client import LLMClient
from agents.prompts import format_game_state

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default skills per role (first skill = basic attack)
_DEFAULT_SKILLS: dict[str, int] = {
    "tank": 104,     # 英勇打击
    "healer": 201,   # 治疗术 -> target tank
    "mage": 301,     # 火球术
    "rogue": 401,    # 背刺
    "hunter": 501,   # 精准射击
}


class BaseAgent:
    """One agent controls one character via LLM decisions.

    Parameters
    ----------
    character_id : str
        Unique id for the character in the game engine.
    role : str
        Role key (tank / healer / mage / rogue / hunter).
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
    ) -> None:
        self.character_id = character_id
        self.role = role
        self.engine = engine
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.name = name or character_id
        self.agent_index = agent_index
        self._llm_semaphore = llm_semaphore
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> asyncio.Task:
        """Spawn the agent loop as an asyncio task."""
        self._task = asyncio.create_task(self.run(), name=f"agent-{self.name}")
        return self._task

    def stop(self) -> None:
        """Cancel the agent loop."""
        if self._task and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Agent main loop: observe -> decide -> act.

        Outer loop survives game restarts — waits for engine.is_running,
        runs the inner tick loop, then goes back to waiting.
        """
        logger.info("[%s] Agent started (role=%s)", self.name, self.role)
        try:
            while True:
                # Wait for engine to start running
                while not self.engine.is_running:
                    await asyncio.sleep(0.2)

                # Stagger startup: each agent waits agent_index * 0.5s
                stagger = self.agent_index * 0.5
                if stagger > 0:
                    logger.info("[%s] Staggering start by %.1fs", self.name, stagger)
                    await asyncio.sleep(stagger)

                logger.info("[%s] Engine is running, entering loop", self.name)
                while self.engine.is_running:
                    await self._tick()
                    # Brief pause between decisions
                    await asyncio.sleep(0.5)

                logger.info("[%s] Game ended, waiting for next start", self.name)
        except asyncio.CancelledError:
            logger.info("[%s] Agent cancelled", self.name)
        except Exception:
            logger.exception("[%s] Agent crashed", self.name)
        finally:
            logger.info("[%s] Agent stopped", self.name)

    async def _tick(self) -> None:
        """Single iteration of the agent loop."""
        character = self.engine.get_character(self.character_id)
        if character is None:
            await asyncio.sleep(0.5)
            return

        # Dead characters just wait
        if not character.is_alive:
            await asyncio.sleep(0.5)
            return

        # Not ready to act yet (GCD not finished or casting)
        if not character.gcd_ready():
            return

        # Build state prompt (use agent-specific method that won't consume logs)
        state = self.engine.get_state_for_agent()
        user_prompt = format_game_state(state, self.character_id)

        # Build tools for this role
        from agents.tools import build_tools_for_role
        tools = build_tools_for_role(self.role)

        # Ask LLM for a decision via Tool Use (rate-limited via semaphore)
        from game.events import COMBAT_LOG
        if self._llm_semaphore:
            async with self._llm_semaphore:
                decision = await self.llm_client.get_decision_with_tools(
                    self.system_prompt, user_prompt, tools
                )
                await asyncio.sleep(0.3)
        else:
            decision = await self.llm_client.get_decision_with_tools(
                self.system_prompt, user_prompt, tools
            )

        # Track decision source
        decision_source = "ai"

        if decision is None:
            default_skill = _DEFAULT_SKILLS.get(self.role, 104)
            default_target = "tank" if self.role == "healer" else "boss"
            decision = {
                "skill_id": default_skill,
                "target": default_target,
                "reason": "超时,使用默认技能",
                "tool_name": None,
            }
            decision_source = "timeout"
            logger.info("[%s] LLM returned None, using default action", self.name)

        # Submit to game engine
        skill_id = decision.get("skill_id", 0)
        target = decision.get("target", "boss")
        reason = decision.get("reason", "")
        tool_name = decision.get("tool_name")

        # Resolve skill name for display
        from game.skills import get_skill as _get_skill
        _skill_def = _get_skill(skill_id)
        skill_name = _skill_def.name if _skill_def else f"skill_{skill_id}"

        # Capture instruction context the agent is acting upon
        god_cmd = state.get("god_command", "")

        ok = self.engine.submit_action(self.character_id, skill_id, target)
        if ok:
            character.last_action = {
                "skill_name": skill_name,
                "target": target,
                "reason": reason,
                "source": decision_source,
                "tool_name": tool_name,
                "time": time.time(),
                "instruction": god_cmd,  # what instruction was active
            }
            # Emit AI decision / timeout to combat log
            char_name = character.name
            if decision_source == "ai":
                self.engine.event_bus.emit(COMBAT_LOG, {
                    "message": f"\U0001f916 [{char_name}] 调用 {skill_name}(target={target}) \"{reason}\"",
                    "type": "ai_decision",
                })
            elif decision_source == "timeout":
                self.engine.event_bus.emit(COMBAT_LOG, {
                    "message": f"\u23f1 [{char_name}] 超时 \u2192 默认 {skill_name}",
                    "type": "ai_timeout",
                })
            logger.debug(
                "[%s] Action submitted: skill=%d target=%s reason=%s source=%s",
                self.name, skill_id, target, reason, decision_source,
            )
        else:
            # If the chosen skill failed, try the default basic attack
            default_skill = _DEFAULT_SKILLS.get(self.role, 104)
            if skill_id != default_skill:
                default_target = "tank" if self.role == "healer" else "boss"
                fallback_ok = self.engine.submit_action(self.character_id, default_skill, default_target)
                if fallback_ok:
                    _fb_skill = _get_skill(default_skill)
                    character.last_action = {
                        "skill_name": _fb_skill.name if _fb_skill else "普攻",
                        "target": default_target,
                        "reason": "技能失败，使用默认攻击",
                        "source": "auto",
                        "tool_name": None,
                        "time": time.time(),
                        "instruction": god_cmd,
                    }
            logger.debug(
                "[%s] Action rejected: skill=%d target=%s, fell back to default",
                self.name, skill_id, target
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sanitize(self, decision: dict[str, Any]) -> dict[str, Any]:
        """Ensure the decision dict has required keys with valid types."""
        try:
            decision["skill_id"] = int(decision.get("skill_id", 0))
        except (TypeError, ValueError):
            decision["skill_id"] = _DEFAULT_SKILLS.get(self.role, 104)

        if "target" not in decision or not isinstance(decision["target"], str):
            decision["target"] = "boss"

        return decision
