"""
h_agent/core/config.py - Configuration module

Central configuration for the h_agent system.
Loads from multiple sources with priority:
1. Environment variables (.env file)
2. ~/.h-agent/config.yaml
3. Hardcoded defaults

Supports multiple config profiles and import/export.
"""

import os
import sys
import json
import yaml
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List

from h_agent.platform_utils import get_config_dir, IS_WINDOWS

# ============================================================
# Paths
# ============================================================

AGENT_CONFIG_DIR = get_config_dir()
AGENT_CONFIG_FILE = AGENT_CONFIG_DIR / "config.yaml"
AGENT_SECRETS_FILE = AGENT_CONFIG_DIR / "secrets.yaml"
AGENT_CONFIG_INDEX = AGENT_CONFIG_DIR / "config_index.json"
AGENT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Multi-Config Profile Support
# ============================================================

def _get_config_index() -> Dict[str, Any]:
    """Load config index (which maps profile names to config files)."""
    if AGENT_CONFIG_INDEX.exists():
        try:
            with open(AGENT_CONFIG_INDEX) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"current": "default", "profiles": {"default": str(AGENT_CONFIG_FILE)}}


def _save_config_index(idx: Dict[str, Any]) -> None:
    """Save config index."""
    with open(AGENT_CONFIG_INDEX, "w") as f:
        json.dump(idx, f, indent=2)


def _get_profile_config_path(profile: str) -> Path:
    """Get the config file path for a given profile."""
    idx = _get_config_index()
    path = idx.get("profiles", {}).get(profile)
    if path:
        return Path(path)
    # Create new profile path
    return AGENT_CONFIG_DIR / f"config.{profile}.yaml"


def get_current_profile() -> str:
    """Get the currently active config profile."""
    return _get_config_index().get("current", "default")


def set_current_profile(profile: str) -> bool:
    """Switch to a different config profile."""
    idx = _get_config_index()
    if profile not in idx.get("profiles", {}):
        # Create the profile with default values
        create_profile(profile)
    idx["current"] = profile
    _save_config_index(idx)
    return True


def create_profile(profile: str, copy_from: str = None) -> bool:
    """Create a new named config profile."""
    idx = _get_config_index()
    if profile in idx.get("profiles", {}):
        return False  # Already exists

    src_path = None
    if copy_from and copy_from in idx.get("profiles", {}):
        src_path = Path(idx["profiles"][copy_from])
    elif "default" in idx.get("profiles", {}):
        src_path = Path(idx["profiles"]["default"])

    new_path = AGENT_CONFIG_DIR / f"config.{profile}.yaml"
    new_path.parent.mkdir(parents=True, exist_ok=True)

    if src_path and src_path.exists():
        shutil.copy2(src_path, new_path)
    else:
        # Create with defaults
        with open(new_path, "w") as f:
            yaml.dump({
                "model_id": "gpt-4o",
                "api_base_url": "https://api.openai.com/v1",
            }, f)

    idx.setdefault("profiles", {})[profile] = str(new_path)
    _save_config_index(idx)
    return True


def delete_profile(profile: str) -> bool:
    """Delete a config profile."""
    if profile == "default":
        return False  # Can't delete default
    idx = _get_config_index()
    if profile not in idx.get("profiles", {}):
        return False

    path = Path(idx["profiles"][profile])
    if path.exists():
        path.unlink()

    del idx["profiles"][profile]
    if idx.get("current") == profile:
        idx["current"] = "default"
    _save_config_index(idx)
    return True


def list_profiles() -> List[str]:
    """List all available config profiles."""
    return list(_get_config_index().get("profiles", {}).keys())


def _load_yaml_config(path: Path) -> dict:
    """Load a YAML config file."""
    if path.exists():
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


def _load_secrets() -> dict:
    """Load secrets from secrets file."""
    return _load_yaml_config(AGENT_SECRETS_FILE)


def _save_secrets(secrets: dict) -> None:
    """Save secrets with restricted permissions."""
    AGENT_SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AGENT_SECRETS_FILE, "w") as f:
        yaml.dump(secrets, f)
    try:
        os.chmod(AGENT_SECRETS_FILE, 0o600)
    except OSError:
        pass


def _load_current_config() -> dict:
    """Load the current profile's YAML config."""
    profile = get_current_profile()
    path = _get_profile_config_path(profile)
    return _load_yaml_config(path)


# Lazy-loaded YAML config
_yaml_config = None


def _get_yaml_config() -> dict:
    """Get the current profile's YAML config (lazy loading)."""
    global _yaml_config
    if _yaml_config is None:
        _yaml_config = _load_current_config()
    return _yaml_config


# ============================================================
# API Configuration
# ============================================================

def _get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret from secrets file, with .env fallback."""
    env_val = os.getenv(key)
    if env_val:
        return env_val
    secrets = _load_secrets()
    yaml_val = secrets.get(key.lower()) or secrets.get(key)
    if yaml_val:
        return yaml_val
    return default


def _set_secret(key: str, value: str) -> None:
    """Securely store a secret."""
    secrets = _load_secrets()
    secrets[key.upper()] = value
    _save_secrets(secrets)


OPENAI_API_KEY = _get_secret("OPENAI_API_KEY", "sk-dummy")

OPENAI_BASE_URL = os.getenv(
    "OPENAI_BASE_URL",
    _get_yaml_config().get("api_base_url", "https://api.openai.com/v1")
)

MODEL_ID = os.getenv(
    "MODEL_ID",
    _get_yaml_config().get("model_id", "gpt-4o")
)

MODEL = MODEL_ID


# ============================================================
# Workspace Configuration
# ============================================================

WORKSPACE_DIR = Path(os.getenv(
    "WORKSPACE_DIR",
    str(Path.cwd() / ".agent_workspace")
))
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Context Limits
# ============================================================

CONTEXT_SAFE_LIMIT = int(os.getenv(
    "CONTEXT_SAFE_LIMIT",
    _get_yaml_config().get("context_safe_limit", 180000)
))
MAX_TOOL_OUTPUT = int(os.getenv(
    "MAX_TOOL_OUTPUT",
    _get_yaml_config().get("max_tool_output", 50000)
))
TOOL_TIMEOUT = int(os.getenv(
    "H_AGENT_TOOL_TIMEOUT",
    _get_yaml_config().get("tool_timeout", 120)
))


# ============================================================
# Skills Directory
# ============================================================

SKILLS_DIR = Path(__file__).parent.parent / "skills"


# ============================================================
# Session Configuration
# ============================================================

SESSION_DIR = WORKSPACE_DIR / "sessions"


# ============================================================
# Config Management API (for CLI)
# ============================================================

def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a configuration value from any source."""
    env_val = os.getenv(key.upper())
    if env_val:
        return env_val
    secrets = _load_secrets()
    if key.upper() in secrets or key.lower() in secrets:
        return secrets.get(key.upper()) or secrets.get(key.lower())
    yaml_val = _get_yaml_config().get(key.lower())
    if yaml_val:
        return str(yaml_val)
    return default


def set_config(key: str, value: str, secure: bool = False) -> None:
    """Set a configuration value in the current profile.

    Args:
        key: Configuration key (e.g., 'OPENAI_API_KEY')
        value: Configuration value
        secure: If True, store in secrets file (for API keys)
    """
    if secure or key.upper() in ("OPENAI_API_KEY", "API_KEY", "SECRET_KEY"):
        _set_secret(key.upper(), value)
    else:
        config = _load_current_config()
        config[key.lower()] = value
        profile = get_current_profile()
        path = _get_profile_config_path(profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(config, f)


def list_config() -> dict:
    """List all configuration values for current profile (secrets masked)."""
    config = dict(_get_yaml_config())

    # Add env overrides
    for key in ["OPENAI_BASE_URL", "MODEL_ID", "OPENAI_API_KEY"]:
        val = os.getenv(key)
        if val:
            config[key.lower()] = val

    # Mask secrets
    for key in list(config.keys()):
        if key.upper() in ("OPENAI_API_KEY", "API_KEY", "SECRET_KEY") or "KEY" in key.upper():
            val = str(config[key])
            if len(val) > 8:
                config[key] = val[:4] + "..." + val[-4:]
            else:
                config[key] = "****"

    return config


def list_all_config() -> Dict[str, Any]:
    """List ALL configuration for all profiles (for --list-all flag)."""
    result = {
        "current_profile": get_current_profile(),
        "profiles": {},
    }
    idx = _get_config_index()
    for name in idx.get("profiles", {}):
        path = Path(idx["profiles"][name])
        cfg = _load_yaml_config(path)
        # Mask secrets
        for key in list(cfg.keys()):
            if "key" in key.lower():
                val = str(cfg[key])
                if len(val) > 8:
                    cfg[key] = val[:4] + "..." + val[-4:]
                else:
                    cfg[key] = "****"
        result["profiles"][name] = cfg
    return result


def clear_secret(key: str) -> None:
    """Remove a secret from the secrets file."""
    secrets = _load_secrets()
    upper_key = key.upper()
    lower_key = key.lower()
    if upper_key in secrets:
        del secrets[upper_key]
    elif lower_key in secrets:
        del secrets[lower_key]
    _save_secrets(secrets)


# ============================================================
# Config Import / Export
# ============================================================

def export_config(path: Path = None, profile: str = None) -> Path:
    """Export current config (or specified profile) to a JSON file."""
    profile = profile or get_current_profile()
    path = path or AGENT_CONFIG_DIR / f"h-agent-config-export-{profile}.json"

    idx = _get_config_index()
    if profile == "default":
        cfg_path = Path(idx.get("profiles", {}).get("default", AGENT_CONFIG_FILE))
    else:
        cfg_path = Path(idx.get("profiles", {}).get(profile, _get_profile_config_path(profile)))

    cfg = _load_yaml_config(cfg_path)
    secrets = _load_secrets()

    export_data = {
        "profile": profile,
        "config": cfg,
        "secrets": {k: v for k, v in secrets.items()},  # Full secrets for export
        "version": "1.0",
    }

    with open(path, "w") as f:
        json.dump(export_data, f, indent=2)

    return path


def import_config(path: Path, profile: str = None, merge: bool = False) -> bool:
    """Import config from a JSON export file."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False

    profile = profile or data.get("profile", "imported")
    secrets = data.get("secrets", {})
    config = data.get("config", {})

    if merge:
        # Merge into current profile
        current = _load_current_config()
        current.update(config)
        config = current
        s = _load_secrets()
        s.update(secrets)
        secrets = s

    # Save config
    cfg_path = _get_profile_config_path(profile)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w") as f:
        yaml.dump(config, f)

    # Save secrets
    _save_secrets(secrets)

    # Register profile
    idx = _get_config_index()
    idx.setdefault("profiles", {})[profile] = str(cfg_path)
    _save_config_index(idx)

    return True
