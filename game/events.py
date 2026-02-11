"""Event bus for game-wide communication."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable

# Event type constants
DAMAGE = "damage"
HEAL = "heal"
BUFF_APPLY = "buff_apply"
BUFF_EXPIRE = "buff_expire"
PHASE_CHANGE = "phase_change"
DEATH = "death"
VICTORY = "victory"
DEFEAT = "defeat"
COMBAT_LOG = "combat_log"
BOSS_CAST = "boss_cast"
SUMMON = "summon"


class EventBus:
    """Simple synchronous event bus with optional async listener support."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = defaultdict(list)
        self._log: list[dict[str, Any]] = []

    def on(self, event_type: str, callback: Callable) -> None:
        self._listeners[event_type].append(callback)

    def off(self, event_type: str, callback: Callable) -> None:
        try:
            self._listeners[event_type].remove(callback)
        except ValueError:
            pass

    # Event types that should NOT be stored in the combat log
    _NO_LOG_EVENTS = {"tick_complete", "combat_log_broadcast", "game_over"}

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        entry = {"type": event_type, **(data or {})}
        if event_type not in self._NO_LOG_EVENTS:
            self._log.append(entry)
        for cb in list(self._listeners.get(event_type, [])):
            cb(entry)

    def get_log(self, since: int = 0) -> list[dict[str, Any]]:
        return self._log[since:]

    def clear_log(self) -> None:
        self._log.clear()
