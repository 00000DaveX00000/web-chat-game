"""LLM client wrapper supporting multiple providers."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


class LLMClient:
    """Async LLM client that returns structured JSON decisions."""

    def __init__(
        self,
        provider: str = "anthropic",
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 0.3,
        max_tokens: int = 300,
        timeout: float = 30.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        if provider == "anthropic":
            kwargs: dict[str, Any] = {}
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            self.client = anthropic.AsyncAnthropic(**kwargs)
            logger.info(
                "LLM client initialized: model=%s base_url=%s",
                model, base_url or "(default)",
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def get_decision(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any] | None:
        """Call LLM and parse the JSON decision.

        Returns parsed dict on success, None on timeout / error.
        The caller should treat None as "default to basic attack".
        """
        try:
            response = await asyncio.wait_for(
                self._call_api(system_prompt, user_prompt),
                timeout=self.timeout,
            )
            return self._parse_response(response)
        except asyncio.TimeoutError:
            logger.warning("LLM decision timed out (%.1fs)", self.timeout)
            return None
        except Exception:
            logger.exception("LLM call failed")
            return None

    # ------------------------------------------------------------------
    # Tool Use API
    # ------------------------------------------------------------------

    async def get_decision_with_tools(
        self, system_prompt: str, user_prompt: str, tools: list[dict]
    ) -> dict[str, Any] | None:
        """Use Anthropic Tool Use API to get a structured decision."""
        try:
            resp = await asyncio.wait_for(
                self._call_api_with_tools(system_prompt, user_prompt, tools),
                timeout=self.timeout,
            )
            return resp
        except asyncio.TimeoutError:
            logger.warning("LLM tool call timed out (%.1fs)", self.timeout)
            return None
        except Exception:
            logger.exception("LLM tool call failed")
            return None

    async def _call_api_with_tools(
        self, system_prompt: str, user_prompt: str, tools: list[dict]
    ) -> list[dict[str, Any]] | None:
        """Call Anthropic API with tools, return list of decisions.

        Each decision: {tool_name, tool_input, skill_id, target, reason}.
        Supports multiple tool calls per response (multi-skill).
        """
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=tools,
            tool_choice={"type": "any"},
        )
        decisions = []
        for block in resp.content:
            if block.type == "tool_use":
                decisions.append({
                    "tool_name": block.name,
                    "tool_input": block.input,
                    "skill_id": int(block.name.replace("use_", "")),
                    "target": block.input.get("target", ""),
                    "reason": block.input.get("reason", ""),
                })
        return decisions if decisions else None

    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """Invoke the underlying LLM API and return raw text."""
        if self.provider == "anthropic":
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return resp.content[0].text
        raise ValueError(f"Unsupported provider: {self.provider}")

    @staticmethod
    def _parse_response(text: str) -> dict[str, Any] | None:
        """Extract a JSON object from LLM output.

        Handles cases where the model wraps JSON in markdown fences or
        adds explanatory text around it.
        """
        # Try direct parse first
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON inside markdown code fences
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object in the text
        brace_match = re.search(r"\{[^{}]*\}", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse LLM response as JSON: %s", text[:200])
        return None
