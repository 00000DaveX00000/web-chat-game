"""SkillDef -> Anthropic tool definition generator for Tool Use API."""

from __future__ import annotations

from game.skills import ROLE_SKILLS, SkillDef


def skill_to_tool(skill: SkillDef) -> dict:
    """Convert a SkillDef into an Anthropic tool definition."""
    properties: dict = {
        "reason": {
            "type": "string",
            "description": "为什么现在使用这个技能(简短说明)",
        }
    }
    required = ["reason"]

    if skill.target_type in ("enemy", "ally"):
        properties["target"] = {
            "type": "string",
            "description": "目标ID. 可选: boss, tank, healer, mage, rogue, hunter, add_0, add_1...",
            "enum": [
                "boss", "tank", "healer", "mage", "rogue", "hunter",
                "add_0", "add_1", "add_2", "add_3",
            ],
        }
        required.insert(0, "target")

    # Build description including cooldown/cost/cast info
    desc_parts = [skill.description]
    if skill.cooldown > 0:
        desc_parts.append(f"冷却{skill.cooldown}秒")
    if skill.mana_cost > 0:
        desc_parts.append(f"消耗{skill.mana_cost}")
    if skill.cast_time > 0:
        desc_parts.append(f"施法{skill.cast_time}秒")

    return {
        "name": f"use_{skill.id}",
        "description": " | ".join(desc_parts),
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def build_tools_for_role(role: str) -> list[dict]:
    """Build all 4 skill tool definitions for a given role."""
    skills = ROLE_SKILLS.get(role, [])
    return [skill_to_tool(s) for s in skills]


def tool_name_to_skill_id(tool_name: str) -> int:
    """Extract skill_id from tool name (e.g. 'use_101' -> 101)."""
    return int(tool_name.replace("use_", ""))
