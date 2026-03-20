"""
h_agent/personality/loader.py - Personality File Loader

Loads SOUL.md format personality files and converts them to Personality objects.
Supports:
- Built-in templates (default, coder, researcher, etc.)
- Per-adapter SOUL.md files
- Project-level personality definitions
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

from h_agent.personality.base import Personality, cache_personality, get_personality

# Personality templates directory
PERSONALITY_DIR = Path(__file__).parent
TEMPLATES_DIR = PERSONALITY_DIR / "templates"

# Project-level personality dir
PROJECT_PERSONALITY_DIR = Path.home() / ".h-agent" / "personalities"


def _parse_soul_markdown(content: str, source_name: str = "unknown") -> Personality:
    """
    Parse a SOUL.md format file into a Personality object.
    
    SOUL.md format:
    - # Name - Role (header)
    - ## description  (optional, follows header)
    - ## traits       (bullet list)
    - ## beliefs      (bullet list or blockquotes)
    - ## quotes       (blockquotes)
    - ## communication_style  (key-value pairs)
    - ## tech_philosophy  (bullet list)
    - ## flaws       (bullet list)
    """
    lines = content.strip().split("\n")
    
    name = source_name
    role = ""
    description = ""
    section = None
    section_content: List[str] = []
    traits: List[str] = []
    beliefs: List[str] = []
    quotes: List[str] = []
    communication_style: Dict[str, Any] = {}
    tech_philosophy: List[str] = []
    flaws: List[str] = []

    def _flush_section():
        nonlocal section, section_content
        if section is None:
            return
        text = "\n".join(section_content).strip()
        if section == "description":
            description = text
        elif section == "traits":
            for line in section_content:
                line = line.strip().lstrip("-*").strip()
                if line:
                    traits.append(line)
        elif section == "beliefs":
            for line in section_content:
                line = line.strip().lstrip("-*").strip()
                if line:
                    beliefs.append(line)
        elif section == "quotes":
            for line in section_content:
                line = line.strip().lstrip("-*").strip().strip('"').strip()
                if line:
                    quotes.append(line)
        elif section == "communication_style":
            for line in section_content:
                line = line.strip()
                if ":" in line:
                    key, val = line.split(":", 1)
                    communication_style[key.strip()] = val.strip()
        elif section == "tech_philosophy":
            for line in section_content:
                line = line.strip().lstrip("-*").strip()
                if line:
                    tech_philosophy.append(line)
        elif section == "flaws":
            for line in section_content:
                line = line.strip().lstrip("-*").strip()
                if line:
                    flaws.append(line)
        section_content = []

    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Parse header: # Name - Role
        if line.startswith("# ") and role == "":
            header = line[2:].strip()
            if " - " in header:
                parts = header.split(" - ", 1)
                name = parts[0].strip()
                role = parts[1].strip()
            else:
                name = header
            i += 1
            continue

        # Parse section headers
        if line.startswith("## "):
            _flush_section()
            section_title = line[3:].strip().lower()
            if section_title == "description":
                section = "description"
            elif section_title in ("traits", "核心特质"):
                section = "traits"
            elif section_title in ("beliefs", "信念"):
                section = "beliefs"
            elif section_title in ("quotes", "经典台词"):
                section = "quotes"
            elif section_title in ("communication_style", "沟通风格", "风格"):
                section = "communication_style"
            elif section_title in ("tech_philosophy", "技术理念", "技术哲学"):
                section = "tech_philosophy"
            elif section_title in ("flaws", "缺点"):
                section = "flaws"
            else:
                section = None
            i += 1
            continue

        # Collect content
        if section is not None:
            section_content.append(line)
        i += 1

    _flush_section()

    # Fallback description
    if not description:
        description = f"{name} - {role}" if role else name

    return Personality(
        name=name,
        role=role,
        description=description,
        traits=traits,
        beliefs=beliefs,
        quotes=quotes,
        communication_style=communication_style,
        tech_philosophy=tech_philosophy,
        flaws=flaws,
        raw_content=content,
    )


def load_personality(name: str) -> Optional[Personality]:
    """
    Load a personality by name.
    
    Search order:
    1. Cache (return cached if available)
    2. Built-in templates (templates/ directory)
    3. ~/.h-agent/personalities/<name>.md
    4. Per-adapter SOUL.md files
    
    Returns None if not found.
    """
    # Check cache first
    cached = get_personality(name)
    if cached:
        return cached

    # Search in templates dir
    template_path = TEMPLATES_DIR / f"{name}.md"
    if template_path.exists():
        try:
            content = template_path.read_text(encoding="utf-8")
            personality = _parse_soul_markdown(content, source_name=name)
            cache_personality(name, personality)
            return personality
        except Exception as e:
            print(f"[personality] Failed to load template {name}: {e}")

    # Search in project personalities dir
    PROJECT_PERSONALITY_DIR.mkdir(parents=True, exist_ok=True)
    project_path = PROJECT_PERSONALITY_DIR / f"{name}.md"
    if project_path.exists():
        try:
            content = project_path.read_text(encoding="utf-8")
            personality = _parse_soul_markdown(content, source_name=name)
            cache_personality(name, personality)
            return personality
        except Exception as e:
            print(f"[personality] Failed to load project personality {name}: {e}")

    return None


def load_adapter_personality(adapter_name: str, adapter_dir: Optional[Path] = None) -> Optional[Personality]:
    """
    Load personality specific to an adapter.
    
    Looks for SOUL.md in:
    1. Adapter's own directory (adapter_dir / "SOUL.md")
    2. Project personalities dir (~/.h-agent/personalities/adapters/<adapter_name>/SOUL.md)
    """
    # Check adapter dir first
    if adapter_dir:
        soul_path = adapter_dir / "SOUL.md"
        if soul_path.exists():
            try:
                content = soul_path.read_text(encoding="utf-8")
                personality = _parse_soul_markdown(content, source_name=adapter_name)
                cache_personality(f"adapter:{adapter_name}", personality)
                return personality
            except Exception as e:
                print(f"[personality] Failed to load adapter SOUL.md for {adapter_name}: {e}")

    # Check project adapters dir
    PROJECT_PERSONALITY_DIR.mkdir(parents=True, exist_ok=True)
    adapter_soul = PROJECT_PERSONALITY_DIR / "adapters" / adapter_name / "SOUL.md"
    if adapter_soul.exists():
        try:
            content = adapter_soul.read_text(encoding="utf-8")
            personality = _parse_soul_markdown(content, source_name=adapter_name)
            cache_personality(f"adapter:{adapter_name}", personality)
            return personality
        except Exception as e:
            print(f"[personality] Failed to load adapter personality for {adapter_name}: {e}")

    return None


def list_available_personalities() -> List[str]:
    """List all available personality templates."""
    personalities = []
    
    # Built-in templates
    if TEMPLATES_DIR.exists():
        for p in TEMPLATES_DIR.glob("*.md"):
            personalities.append(f"template:{p.stem}")
    
    # Project personalities
    PROJECT_PERSONALITY_DIR.mkdir(parents=True, exist_ok=True)
    for p in PROJECT_PERSONALITY_DIR.glob("*.md"):
        personalities.append(f"project:{p.stem}")
    
    return personalities


def inject_personality_into_system(system_prompt: str, personality: Personality) -> str:
    """
    Inject personality definition into a system prompt.
    
    Appends the personality section at the end of the system prompt.
    """
    personality_section = "\n\n" + personality.to_system_prompt()
    
    # Check if the system prompt already ends with a personality section
    if "## 核心特质" in system_prompt or "## Core Traits" in system_prompt:
        # Already has personality, skip injection
        return system_prompt
    
    return system_prompt.rstrip() + personality_section
