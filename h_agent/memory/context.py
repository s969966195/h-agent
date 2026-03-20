#!/usr/bin/env python3
"""
h_agent/memory/context.py - Context Manager

精细化上下文控制:
1. ContextWindow: 可配置的上下文大小限制
2. LayeredSummarizer: 分层摘要策略（保留关键信息）
3. ContextBudget: Token 预算管理
4. KeyInfoKeeper: 关键信息永久保留
"""

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable, Tuple
from pathlib import Path

from h_agent.memory.summarizer import SmartSummarizer, summarize_messages


# ============================================================
# Context Budget
# ============================================================

# 模型上下文限制预设（类常量，非 dataclass field）
_MODEL_CONTEXTS = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "glm-4": 128000,
    "glm-4-flash": 128000,
    "deepseek-chat": 16384,
}


@dataclass
class ContextBudget:
    """
    上下文预算管理器。

    使用方式:
        budget = ContextBudget(
            max_tokens=180000,
            reserve_tokens=20000,  # 为最新消息保留
        )
        can_fit, trim_count = budget.can_fit(messages)
    """
    max_tokens: int = 180000       # 最大 token 预算
    reserve_tokens: int = 20000    # 保留给最新消息
    tool_output_max: int = 50000   # 单个工具输出上限

    def can_fit(self, estimated_tokens: int) -> Tuple[bool, int]:
        """检查是否能在预算内 fit。"""
        available = self.max_tokens - self.reserve_tokens
        if estimated_tokens <= available:
            return True, 0
        return False, estimated_tokens - available

    def estimate_messages_tokens(self, messages: List[Dict]) -> int:
        """估算消息列表的总 token 数（粗略估计）。"""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total_chars += len(str(block.get("text", "")))
            # role + overhead ≈ +10 chars
            total_chars += 10
        return total_chars // 4  # rough: 1 token ≈ 4 chars


# ============================================================
# Layered Summarizer
# ============================================================

class LayeredSummarizer:
    """
    分层摘要策略。

    将消息分为三层，每层用不同的摘要策略:
    1. System层 — 系统提示（不压缩）
    2. History层 — 对话历史（智能摘要）
    3. Recent层 — 最近的消息（完整保留）

    这样可以确保:
    - 关键上下文（系统提示）永远不丢
    - 远古记忆被压缩成摘要
    - 最近几轮对话完整保留（语义连贯）
    """

    def __init__(
        self,
        recent_count: int = 6,        # 保留最近 N 条完整消息
        history_ratio: float = 0.5,   # 历史消息压缩比例
        summarizer: SmartSummarizer = None,
    ):
        self.recent_count = recent_count
        self.history_ratio = history_ratio  # 保留历史消息的比例（其余摘要）
        self.summarizer = summarizer or SmartSummarizer()

    def compress(
        self,
        messages: List[Dict],
        budget: ContextBudget,
        session_id: str = None,
    ) -> List[Dict]:
        """
        对消息列表进行分层压缩。

        Returns:
            压缩后的消息列表（格式同输入）
        """
        if not messages:
            return messages

        # 分离各层
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # 估算当前 token
        estimated = budget.estimate_messages_tokens(non_system)
        can_fit, _ = budget.can_fit(estimated)

        if can_fit:
            return messages  # 不需要压缩

        # 需要压缩
        if len(non_system) <= self.recent_count:
            return system_msgs + non_system

        recent = non_system[-self.recent_count:]
        history = non_system[:-self.recent_count]

        # 对 history 层进行摘要压缩
        compressed_history = self._compress_history(history)

        return system_msgs + compressed_history + recent

    def _compress_history(self, history: List[Dict]) -> List[Dict]:
        """压缩历史层。"""
        if not history:
            return []

        # 按比例保留一部分，摘要其余
        keep_count = max(1, int(len(history) * self.history_ratio))
        keep_msgs = history[:keep_count]
        summary_msgs = history[keep_count:]

        if not summary_msgs:
            return keep_msgs

        # 生成摘要
        try:
            summary_text = self.summarizer.summarize(summary_msgs)
            summary_msg = {
                "role": "system",
                "content": f"[Earlier conversation summary]\n{summary_text}",
            }
            return [summary_msg] + keep_msgs
        except Exception:
            # LLM 不可用时，保守地只保留最近消息
            return keep_msgs


# ============================================================
# Key Information Keeper
# ============================================================

class KeyInfoKeeper:
    """
    关键信息永久保留器。

    功能:
    - 用户偏好（语言、风格）
    - 项目上下文（技术栈、架构）
    - 重要决策（为什么选这个方案）
    - API 密钥等敏感信息（脱敏后）

    这些信息在摘要压缩时不会被丢弃，
    而是会被注入到系统提示或摘要提示中。
    """

    CACHE_FILE = Path.home() / ".h-agent" / "memory" / "key_info.json"

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if self.CACHE_FILE.exists():
            try:
                self._data = json.loads(self.CACHE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self):
        try:
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.CACHE_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except OSError:
            pass

    # ---- Categories ----

    def set_user_pref(self, key: str, value: Any):
        """设置用户偏好。"""
        self._data.setdefault("user_prefs", {})[key] = value
        self._save()

    def get_user_pref(self, key: str, default: Any = None) -> Any:
        return self._data.get("user_prefs", {}).get(key, default)

    def set_project_info(self, key: str, value: Any):
        """设置项目信息。"""
        self._data.setdefault("project_info", {})[key] = value
        self._save()

    def get_project_info(self, key: str, default: Any = None) -> Any:
        return self._data.get("project_info", {}).get(key, default)

    def add_decision(self, decision: str, reason: str = "", tags: List[str] = None):
        """记录重要决策。"""
        self._data.setdefault("decisions", []).append({
            "decision": decision,
            "reason": reason,
            "tags": tags or [],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        self._save()

    def get_decisions(self) -> List[Dict]:
        return self._data.get("decisions", [])

    # ---- Context Injection ----

    def as_context_text(self) -> str:
        """
        生成可注入到上下文的文本。
        在压缩消息时调用此方法。
        """
        parts = []

        # 用户偏好
        prefs = self._data.get("user_prefs", {})
        if prefs:
            parts.append("[User Preferences]")
            for k, v in prefs.items():
                parts.append(f"  • {k}: {v}")

        # 项目信息
        info = self._data.get("project_info", {})
        if info:
            parts.append("[Project Context]")
            for k, v in info.items():
                parts.append(f"  • {k}: {v}")

        # 重要决策
        decisions = self._data.get("decisions", [])
        if decisions:
            parts.append("[Key Decisions]")
            for d in decisions[-5:]:  # 只保留最近 5 个
                parts.append(f"  • {d['decision']}")
                if d.get("reason"):
                    parts.append(f"    Reason: {d['reason']}")

        return "\n".join(parts) if parts else ""

    def clear(self):
        """清空所有保留信息。"""
        self._data = {}
        self._save()


# ============================================================
# Full Context Manager
# ============================================================

class ContextManager:
    """
    整合的上下文管理器。

    整合了:
    - 预算管理
    - 分层摘要
    - 关键信息保留
    - 工具输出截断

    使用方式:
        ctx = ContextManager(
            max_tokens=180000,
            model="gpt-4o",
        )

        # 消息处理
        compressed = ctx.process(messages, session_id="sess-xxx")

        # 注入关键信息
        messages = ctx.inject_key_info(compressed)
    """

    def __init__(
        self,
        max_tokens: int = 180000,
        model: str = "gpt-4o",
        recent_count: int = 6,
        key_info_keeper: KeyInfoKeeper = None,
    ):
        # 根据模型调整预算
        effective_max = min(
            max_tokens,
            _MODEL_CONTEXTS.get(model, 180000)
        )
        self.budget = ContextBudget(max_tokens=effective_max)
        self.layered = LayeredSummarizer(recent_count=recent_count)
        self.key_info = key_info_keeper or KeyInfoKeeper()

    def process(
        self,
        messages: List[Dict],
        session_id: str = None,
    ) -> List[Dict]:
        """
        处理消息列表:
        1. 截断过长的工具输出
        2. 应用分层摘要
        """
        # 第一步：截断工具输出
        truncated = self._truncate_tool_outputs(messages)

        # 第二步：分层摘要
        compressed = self.layered.compress(truncated, self.budget, session_id)

        return compressed

    def inject_key_info(self, messages: List[Dict]) -> List[Dict]:
        """
        将关键信息注入到消息中。
        通常在压缩后、系统提示之后插入。
        """
        key_text = self.key_info.as_context_text()
        if not key_text:
            return messages

        # 找到系统消息的位置
        key_info_msg = {
            "role": "system",
            "content": f"[Important Context — retained across summarization]\n{key_text}",
        }

        # 在第一个非系统消息之前插入
        result = []
        injected = False
        for msg in messages:
            if not injected and msg.get("role") != "system":
                result.append(key_info_msg)
                injected = True
            result.append(msg)

        if not injected:
            result.append(key_info_msg)

        return result

    def _truncate_tool_outputs(self, messages: List[Dict]) -> List[Dict]:
        """截断过长的工具输出。"""
        result = []
        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if len(content) > self.budget.tool_output_max:
                    half = self.budget.tool_output_max // 2
                    msg = {
                        **msg,
                        "content": (
                            content[:half]
                            + f"\n... [truncated {len(content) - self.budget.tool_output_max} chars] ...\n"
                            + content[-half:]
                        ),
                    }
            result.append(msg)
        return result

    # ---- Statistics ----

    def stats(self, messages: List[Dict]) -> Dict:
        """获取上下文统计信息。"""
        before = len(messages)
        after = len(self.process(messages))
        tokens = self.budget.estimate_messages_tokens(messages)

        return {
            "message_count": before,
            "compressed_count": after,
            "estimated_tokens": tokens,
            "within_budget": self.budget.can_fit(tokens)[0],
            "budget_max": self.budget.max_tokens,
            "key_info_items": (
                len(self.key_info._data.get("user_prefs", {}))
                + len(self.key_info._data.get("project_info", {}))
                + len(self.key_info._data.get("decisions", []))
            ),
        }
