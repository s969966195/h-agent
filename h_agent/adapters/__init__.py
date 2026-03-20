"""
h_agent/adapters/__init__.py - Agent Adapter Package

Unified interface for calling external CLI coding agents.
"""

from h_agent.adapters.base import BaseAgentAdapter, AgentResponse, ToolCall
from h_agent.adapters.opencode_adapter import OpencodeAdapter
from h_agent.adapters.claude_adapter import ClaudeAdapter
from h_agent.adapters.zoo_adapter import ZooAdapter, get_zoo_animal, list_zoo_animals

# Registry of available adapters
ADAPTER_REGISTRY: dict[str, type[BaseAgentAdapter]] = {
    "opencode": OpencodeAdapter,
    "claude": ClaudeAdapter,
    "zoo": ZooAdapter,
}

# Registry of zoo animals
ZOO_ANIMALS: dict[str, type[BaseAgentAdapter]] = {
    f"zoo:{animal}": lambda **kw: ZooAdapter(animal=animal, **kw)
    for animal in ["xueqiu", "liuliu", "xiaohuang", "heibai", "xiaozhu"]
}
ADAPTER_REGISTRY.update(ZOO_ANIMALS)


def get_adapter(name: str, **kwargs) -> BaseAgentAdapter:
    """Get an agent adapter by name."""
    adapter_cls = ADAPTER_REGISTRY.get(name.lower())
    if not adapter_cls:
        available = ", ".join(ADAPTER_REGISTRY.keys())
        raise ValueError(f"Unknown adapter '{name}'. Available: {available}")
    return adapter_cls(**kwargs)


def list_adapters() -> list[str]:
    """List available adapter names."""
    return list(ADAPTER_REGISTRY.keys())
