"""
h_agent/core/config.py - Configuration module

Central configuration for the h_agent system.
Loads from multiple sources with priority:
1. Environment variables (.env file)
2. ~/.h-agent/config.yaml
3. Hardcoded defaults
"""

import os
import yaml
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from h_agent.platform_utils import get_config_dir, IS_WINDOWS

# ============================================================
# Paths
# ============================================================

# Use platform-aware config directory (~/.h-agent on Unix, %APPDATA%/h-agent on Windows)
AGENT_CONFIG_DIR = get_config_dir()
AGENT_CONFIG_FILE = AGENT_CONFIG_DIR / "config.yaml"
AGENT_SECRETS_FILE = AGENT_CONFIG_DIR / "secrets.yaml"

# Ensure config directory exists
AGENT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Load Configuration
# ============================================================

def _load_yaml_config(path: Path) -> dict:
    """Load a YAML config file."""
    if path.exists():
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


def _load_secrets() -> dict:
    """Load secrets (API keys) from encrypted/secrets file."""
    return _load_yaml_config(AGENT_SECRETS_FILE)


def _save_secrets(secrets: dict) -> None:
    """Save secrets to file with restricted permissions."""
    AGENT_SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Set file permissions to owner-read/write only (600)
    with open(AGENT_SECRETS_FILE, "w") as f:
        yaml.dump(secrets, f)
    os.chmod(AGENT_SECRETS_FILE, 0o600)


# Load .env first (overrides env vars already set)
load_dotenv(override=True)

# Load YAML config (lower priority than .env)
_yaml_config = _load_yaml_config(AGENT_CONFIG_FILE)

# ============================================================
# API Configuration
# ============================================================

def _get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret from secrets file, with .env fallback."""
    # Priority: .env > secrets.yaml > default
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


# API Key - the most important secret
# Tries: OPENAI_API_KEY env > secrets.yaml > default
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY", "sk-dummy")

# API Base URL
OPENAI_BASE_URL = os.getenv(
    "OPENAI_BASE_URL",
    _yaml_config.get("api_base_url", "https://api.openai.com/v1")
)

# Model ID
MODEL_ID = os.getenv(
    "MODEL_ID",
    _yaml_config.get("model_id", "gpt-4o")
)

# Alias for convenience
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
    _yaml_config.get("context_safe_limit", 180000)
))
MAX_TOOL_OUTPUT = int(os.getenv(
    "MAX_TOOL_OUTPUT",
    _yaml_config.get("max_tool_output", 50000)
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
    
    yaml_val = _yaml_config.get(key.lower())
    if yaml_val:
        return str(yaml_val)
    
    return default


def set_config(key: str, value: str, secure: bool = False) -> None:
    """Set a configuration value.
    
    Args:
        key: Configuration key (e.g., 'OPENAI_API_KEY')
        value: Configuration value
        secure: If True, store in secrets file (for API keys)
    """
    if secure or key.upper() in ("OPENAI_API_KEY", "API_KEY", "SECRET_KEY"):
        _set_secret(key.upper(), value)
    else:
        # Update YAML config
        config = _load_yaml_config(AGENT_CONFIG_FILE)
        config[key.lower()] = value
        AGENT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AGENT_CONFIG_FILE, "w") as f:
            yaml.dump(config, f)


def list_config() -> dict:
    """List all configuration values (secrets masked)."""
    config = dict(_yaml_config)
    
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
