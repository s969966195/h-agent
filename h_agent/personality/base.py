"""
h_agent/personality/base.py - Personality Data Model
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class Personality:
    """
    Represents an agent's personality/character definition.
    
    Loaded from SOUL.md format files.
    """
    name: str
    role: str
    description: str = ""
    # Core traits that define how the agent behaves
    traits: List[str] = field(default_factory=list)
    # Agent's core beliefs and values
    beliefs: List[str] = field(default_factory=list)
    # Famous quotes or sayings of this personality
    quotes: List[str] = field(default_factory=list)
    # Communication style hints
    communication_style: Dict[str, Any] = field(default_factory=dict)
    # Technical philosophy / approach
    tech_philosophy: List[str] = field(default_factory=list)
    # Flaws / weaknesses
    flaws: List[str] = field(default_factory=list)
    # Custom system prompt fragments
    custom_prompts: Dict[str, str] = field(default_factory=dict)
    # Raw loaded content (preserves original formatting)
    raw_content: str = ""

    def to_system_prompt(self) -> str:
        """
        Convert personality definition into a system prompt fragment.
        Injects personality into the agent's instructions.
        """
        lines = [
            f"# {self.name} - {self.role}",
            "",
            self.description,
            "",
        ]

        if self.traits:
            lines.append("## 核心特质")
            for trait in self.traits:
                lines.append(f"- {trait}")
            lines.append("")

        if self.beliefs:
            lines.append("## 信念")
            for belief in self.beliefs:
                lines.append(f"- {belief}")
            lines.append("")

        if self.quotes:
            lines.append("## 经典台词")
            for quote in self.quotes:
                lines.append(f'> "{quote}"')
            lines.append("")

        if self.tech_philosophy:
            lines.append("## 技术理念")
            for philosophy in self.tech_philosophy:
                lines.append(f"- {philosophy}")
            lines.append("")

        if self.flaws:
            lines.append("## 缺点（不掩饰）")
            for flaw in self.flaws:
                lines.append(f"- {flaw}")
            lines.append("")

        if self.communication_style:
            lines.append("## 沟通风格")
            for key, val in self.communication_style.items():
                lines.append(f"- {key}: {val}")
            lines.append("")

        return "\n".join(lines)

    def merge_with(self, other: "Personality") -> "Personality":
        """Merge another personality into this one (for layering)."""
        return Personality(
            name=self.name,
            role=self.role,
            description=self.description or other.description,
            traits=self.traits + [t for t in other.traits if t not in self.traits],
            beliefs=self.beliefs + [b for b in other.beliefs if b not in self.beliefs],
            quotes=self.quotes + [q for q in other.quotes if q not in self.quotes],
            communication_style={**other.communication_style, **self.communication_style},
            tech_philosophy=self.tech_philosophy + [p for p in other.tech_philosophy if p not in self.tech_philosophy],
            flaws=self.flaws + [f for f in other.flaws if f not in self.flaws],
            custom_prompts={**other.custom_prompts, **self.custom_prompts},
            raw_content=self.raw_content + "\n\n" + other.raw_content,
        )


# Global personality cache
_personality_cache: Dict[str, Personality] = {}


def get_personality(name: str) -> Optional[Personality]:
    """Get a cached personality by name."""
    return _personality_cache.get(name)


def cache_personality(name: str, personality: Personality) -> None:
    """Cache a personality for reuse."""
    _personality_cache[name] = personality
