"""Entry point for AI Raid Battle server."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import yaml
from dotenv import load_dotenv
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="AI副本战 - AI Raid Battle")
    parser.add_argument("--team", default="config/team_claude.yaml", help="Team config YAML path")
    parser.add_argument("--boss", default="config/boss_ragnaros.yaml", help="Boss config YAML path")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="Server host")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Server port")
    args = parser.parse_args()

    # Load configs
    with open(args.team) as f:
        team_config = yaml.safe_load(f)
    with open(args.boss) as f:
        boss_config = yaml.safe_load(f)

    # Import components
    from game.engine import GameEngine
    from agents.base_agent import BaseAgent
    from agents.llm_client import LLMClient
    from agents.prompts import get_system_prompt
    from web.server import app, manager
    import web.server as server_module

    # Create engine and inject into server
    engine = GameEngine(boss_config=boss_config)
    server_module.engine = engine

    # Register broadcast callbacks on engine events
    def on_tick_complete(state):
        asyncio.ensure_future(
            manager.broadcast({"type": "state_update", "data": state})
        )

    def on_game_over(result):
        asyncio.ensure_future(
            manager.broadcast({"type": "game_over", "data": result})
        )

    engine.event_bus.on("tick_complete", on_tick_complete)
    engine.event_bus.on("game_over", on_game_over)

    # Create agents from team config
    llm_defaults = team_config.get("llm_defaults", {})

    # Resolve API key: check ANTHROPIC_AUTH_TOKEN first (compatible APIs),
    # then the key specified in config, then ANTHROPIC_API_KEY
    api_key = (
        os.getenv("ANTHROPIC_AUTH_TOKEN")
        or os.getenv(llm_defaults.get("api_key_env", "ANTHROPIC_API_KEY"))
        or os.getenv("ANTHROPIC_API_KEY")
    )
    # Resolve base_url from env or config
    base_url = (
        os.getenv("ANTHROPIC_BASE_URL")
        or llm_defaults.get("base_url")
    )

    logger.info("LLM config: base_url=%s model=%s", base_url or "(default)", llm_defaults.get("model"))

    # Shared semaphore: limit concurrent LLM calls
    llm_semaphore = asyncio.Semaphore(3)

    agents: list[BaseAgent] = []
    for idx, (role, member_config) in enumerate(team_config.get("members", {}).items()):
        # Map "ranger" to "hunter" for compatibility
        actual_role = "hunter" if role == "ranger" else role
        model = member_config.get("model", llm_defaults.get("model"))
        llm_client = LLMClient(
            provider=llm_defaults.get("provider", "anthropic"),
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=llm_defaults.get("temperature", 0.3),
            max_tokens=llm_defaults.get("max_tokens", 150),
            timeout=llm_defaults.get("timeout", 2.0),
        )
        system_prompt = get_system_prompt(actual_role)
        agent = BaseAgent(
            character_id=actual_role,
            role=actual_role,
            name=member_config.get("name", role),
            engine=engine,
            llm_client=llm_client,
            system_prompt=system_prompt,
            agent_index=idx,
            llm_semaphore=llm_semaphore,
        )
        agents.append(agent)

    logger.info("Created %d agents: %s", len(agents), [a.name for a in agents])

    # Track background tasks for graceful cleanup
    background_tasks: list[asyncio.Task] = []

    async def startup():
        """Launch agent loops on FastAPI startup. Game waits for user to click Start."""
        for agent in agents:
            task = asyncio.create_task(agent.run())
            background_tasks.append(task)
        logger.info("Agents started, waiting for game start command")

    app.add_event_handler("startup", startup)

    # Graceful shutdown: cancel background tasks
    async def shutdown():
        logger.info("Shutting down: cancelling %d background tasks", len(background_tasks))
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        logger.info("All background tasks cancelled")

    app.add_event_handler("shutdown", shutdown)

    # Start uvicorn
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
