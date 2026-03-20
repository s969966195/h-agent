"""
h_agent/skills - Skill System for h-agent

Skills are optional plugins that provide specialized capabilities like
Office automation (Word, Excel, PowerPoint) and Outlook integration.

Unlike core plugins, skills can be:
- Installed via pip (h_agent_skills_<name>)
- Placed in local skills directory
- Auto-discovered and loaded on demand
"""

import os
import sys
import json
import importlib
import importlib.util
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

# Skill directories
SKILLS_DIR = Path(__file__).parent
PROJECT_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"
SKILLS_CONFIG_FILE = Path.home() / ".h-agent" / "skills.json"
SKILL_INDEX_URL = "https://raw.githubusercontent.com/ekko-ai/h-agent-skills/main/index.json"


@dataclass
class Skill:
    """Represents a loaded skill."""
    name: str
    version: str
    description: str
    author: str
    category: str = "general"  # office, outlook, development, etc.
    dependencies: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=lambda: ["windows"])  # windows, macos, linux
    tools: List[Dict] = field(default_factory=list)
    functions: Dict[str, Callable] = field(default_factory=dict)
    enabled: bool = True
    installed: bool = False
    path: Optional[Path] = None
    pip_package: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "category": self.category,
            "dependencies": self.dependencies,
            "platforms": self.platforms,
            "enabled": self.enabled,
            "installed": self.installed,
            "path": str(self.path) if self.path else None,
            "pip_package": self.pip_package,
            "tool_count": len(self.tools),
        }

    def is_available(self) -> bool:
        """Check if skill can run on current platform."""
        import platform
        current_platform = platform.system().lower()
        return current_platform in self.platforms

    def check_dependencies(self) -> Dict[str, bool]:
        """Check if all dependencies are installed."""
        results = {}
        for dep in self.dependencies:
            try:
                importlib.import_module(dep)
                results[dep] = True
            except ImportError:
                results[dep] = False
        return results


_loaded_skills: Dict[str, Skill] = {}
_skill_state: Dict[str, bool] = {}


def _get_skill_state() -> Dict[str, bool]:
    """Load skill enabled/disabled state from config."""
    if SKILLS_CONFIG_FILE.exists():
        try:
            with open(SKILLS_CONFIG_FILE) as f:
                data = json.load(f)
            return data.get("skills", {})
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_skill_state(state: Dict[str, bool]) -> None:
    """Save skill state to config."""
    SKILLS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SKILLS_CONFIG_FILE, "w") as f:
        json.dump({"skills": state}, f, indent=2)


def _discover_local_skills() -> List[Path]:
    """Discover skill modules in local skills directory."""
    skills = []
    for skills_dir in [SKILLS_DIR, PROJECT_SKILLS_DIR]:
        if not skills_dir.exists():
            continue
        for item in skills_dir.iterdir():
            if item.is_file() and item.suffix == ".py" and item.stem not in ("__init__", "__base__"):
                skills.append(item)
            elif item.is_dir() and (item / "__init__.py").exists():
                skills.append(item)
    return skills


def _discover_pip_skills() -> List[str]:
    """Discover installed skill packages via pip."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            packages = json.loads(result.stdout)
            return [p["name"] for p in packages if p["name"].startswith("h_agent_skill_")]
    except Exception:
        pass
    return []


def load_skill_from_path(path: Path) -> Optional[Skill]:
    """Load a skill from a path (file or directory)."""
    try:
        if path.is_file():
            name = path.stem
            spec = importlib.util.spec_from_file_location(name, path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
        elif path.is_dir():
            name = path.name
            spec = importlib.util.spec_from_file_location(name, path / "__init__.py")
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
        else:
            return None

        module = sys.modules.get(name)
        if not module:
            return None

        # Check for required skill attributes
        skill_name = getattr(module, "SKILL_NAME", name)
        skill_version = getattr(module, "SKILL_VERSION", "0.0.0")
        skill_desc = getattr(module, "SKILL_DESCRIPTION", "")
        skill_author = getattr(module, "SKILL_AUTHOR", "unknown")
        skill_category = getattr(module, "SKILL_CATEGORY", "general")
        skill_deps = getattr(module, "SKILL_DEPENDENCIES", [])
        skill_platforms = getattr(module, "SKILL_PLATFORMS", ["windows"])
        skill_tools = getattr(module, "SKILL_TOOLS", [])
        skill_functions = getattr(module, "SKILL_FUNCTIONS", {})

        skill = Skill(
            name=skill_name,
            version=skill_version,
            description=skill_desc,
            author=skill_author,
            category=skill_category,
            dependencies=skill_deps,
            platforms=skill_platforms,
            tools=skill_tools,
            functions=skill_functions,
            path=path,
            installed=True,
        )

        # Restore enabled state
        state = _get_skill_state()
        skill.enabled = state.get(skill.name, True)

        _loaded_skills[skill.name] = skill
        return skill

    except Exception as e:
        print(f"[skill] Failed to load {path}: {e}", file=sys.stderr)
        return None


def load_skill_from_package(package_name: str) -> Optional[Skill]:
    """Load a skill from an installed pip package."""
    try:
        module = importlib.import_module(package_name)
        
        skill_name = getattr(module, "SKILL_NAME", package_name.replace("h_agent_skill_", ""))
        skill_version = getattr(module, "SKILL_VERSION", "0.0.0")
        skill_desc = getattr(module, "SKILL_DESCRIPTION", "")
        skill_author = getattr(module, "SKILL_AUTHOR", "unknown")
        skill_category = getattr(module, "SKILL_CATEGORY", "general")
        skill_deps = getattr(module, "SKILL_DEPENDENCIES", [])
        skill_platforms = getattr(module, "SKILL_PLATFORMS", ["windows"])
        skill_tools = getattr(module, "SKILL_TOOLS", [])
        skill_functions = getattr(module, "SKILL_FUNCTIONS", {})

        skill = Skill(
            name=skill_name,
            version=skill_version,
            description=skill_desc,
            author=skill_author,
            category=skill_category,
            dependencies=skill_deps,
            platforms=skill_platforms,
            tools=skill_tools,
            functions=skill_functions,
            pip_package=package_name,
            installed=True,
        )

        state = _get_skill_state()
        skill.enabled = state.get(skill.name, True)

        _loaded_skills[skill.name] = skill
        return skill

    except Exception as e:
        print(f"[skill] Failed to load {package_name}: {e}", file=sys.stderr)
        return None


def load_all_skills() -> Dict[str, Skill]:
    """Discover and load all available skills."""
    # Load local skills
    for path in _discover_local_skills():
        name = path.stem if path.is_file() else path.name
        if name == "__init__":
            continue
        if name not in _loaded_skills:
            load_skill_from_path(path)

    # Load pip-installed skills
    for package_name in _discover_pip_skills():
        skill_name = package_name.replace("h_agent_skill_", "")
        if skill_name not in _loaded_skills:
            load_skill_from_package(package_name)

    return _loaded_skills


def get_skill(name: str) -> Optional[Skill]:
    """Get a loaded skill by name."""
    return _loaded_skills.get(name)


def list_skills(include_all: bool = False) -> List[Skill]:
    """List all loaded skills, optionally including unavailable ones."""
    skills = []
    for skill in _loaded_skills.values():
        if include_all or skill.enabled:
            skills.append(skill)
    return skills


def enable_skill(name: str) -> bool:
    """Enable a skill."""
    if name in _loaded_skills:
        _loaded_skills[name].enabled = True
        state = _get_skill_state()
        state[name] = True
        _save_skill_state(state)
        return True
    return False


def disable_skill(name: str) -> bool:
    """Disable a skill."""
    if name in _loaded_skills:
        _loaded_skills[name].enabled = False
        state = _get_skill_state()
        state[name] = False
        _save_skill_state(state)
        return True
    return False


def install_skill(name: str, package_name: Optional[str] = None) -> bool:
    """Install a skill via pip."""
    pip_package = package_name or f"h_agent_skill_{name}"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pip_package],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return load_skill_from_package(f"h_agent_skill_{name}") is not None
        else:
            print(f"[skill] Install failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"[skill] Install error: {e}")
        return False


def uninstall_skill(name: str) -> bool:
    """Uninstall a skill via pip."""
    skill = get_skill(name)
    if not skill:
        return False
    
    pip_package = skill.pip_package or f"h_agent_skill_{name}"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", pip_package],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            if name in _loaded_skills:
                del _loaded_skills[name]
            return True
        return False
    except Exception as e:
        print(f"[skill] Uninstall error: {e}")
        return False


def get_enabled_tools() -> List[Dict]:
    """Get all tools from enabled skills."""
    tools = []
    for skill in _loaded_skills.values():
        if skill.enabled and skill.is_available():
            # Check dependencies
            deps_ok = all(skill.check_dependencies().values())
            if deps_ok:
                tools.extend(skill.tools)
    return tools


def get_enabled_functions() -> Dict[str, Callable]:
    """Get all functions from enabled skills."""
    functions = {}
    for skill in _loaded_skills.values():
        if skill.enabled and skill.is_available():
            deps_ok = all(skill.check_dependencies().values())
            if deps_ok:
                functions.update(skill.functions)
    return functions


def call_skill_function(name: str, func_name: str, *args, **kwargs) -> Any:
    """Call a function from a skill."""
    skill = get_skill(name)
    if not skill:
        raise ValueError(f"Skill not found: {name}")
    if func_name not in skill.functions:
        raise ValueError(f"Function {func_name} not found in skill {name}")
    return skill.functions[func_name](*args, **kwargs)
