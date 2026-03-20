"""
h_agent/team/ - Agent Team System

多 agent 协作框架:
- AgentTeam: 团队管理器，注册成员、分发任务、汇总结果
- AgentRole: agent 角色定义（planner/coder/reviewer/devops）
- TeamMessage: agent 间通信协议
- TaskBroadcast: 广播式任务分发
"""

from .team import AgentTeam, TeamMessage, TaskResult, AgentRole, MessageBus
from .protocol import TeamProtocol, ProtocolMessage, TaskSpec, MessageType

__all__ = [
    "AgentTeam",
    "TeamMessage",
    "TaskResult",
    "AgentRole",
    "MessageBus",
    "TeamProtocol",
    "ProtocolMessage",
    "TaskSpec",
    "MessageType",
]
