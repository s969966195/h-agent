"""
h_agent/personality - Agent Personality System

Supports SOUL.md format personality definitions for agents.
Each adapter can have its own SOUL.md that gets injected into system prompts.
"""

from h_agent.personality.base import Personality, get_personality
from h_agent.personality.loader import (
    load_personality,
    load_adapter_personality,
    list_available_personalities,
    inject_personality_into_system,
)

__all__ = [
    "Personality",
    "get_personality",
    "load_personality",
    "load_adapter_personality",
    "list_available_personalities",
    "inject_personality_into_system",
]
