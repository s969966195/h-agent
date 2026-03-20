"""
h_agent.memory - Memory subsystem for h-agent.

Submodules:
  - summarizer: LLM-based intelligent context summarization
  - long_term: Persistent memory for user preferences, project info, decisions
  - retriever: Search and retrieve relevant memories from history
  - context: Fine-grained context control (budget, layering, key info)
"""

from h_agent.memory.summarizer import SmartSummarizer, summarize_messages
from h_agent.memory.long_term import (
    LongTermMemory, remember, recall, forget, list_memories,
    search_memory, memory_dump, memory_stats, MemoryType
)
from h_agent.memory.retriever import MemoryRetriever, search_memory as search_mem_sources
from h_agent.memory.context import (
    ContextManager,
    ContextBudget,
    LayeredSummarizer,
    KeyInfoKeeper,
)

__all__ = [
    "SmartSummarizer",
    "summarize_messages",
    "LongTermMemory",
    "remember",
    "recall",
    "forget",
    "list_memories",
    "search_memory",
    "memory_dump",
    "memory_stats",
    "MemoryType",
    "MemoryRetriever",
    "search_mem_sources",
    "ContextManager",
    "ContextBudget",
    "LayeredSummarizer",
    "KeyInfoKeeper",
]
