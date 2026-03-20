# CLI Adapters Guide

外部 CLI Agent 适配器，让 h-agent 能够调用各种 AI 编程工具。

## 概述

适配器将外部 CLI 工具（如 opencode、Claude CLI）包装成统一的接口。

```
h-agent
├── opencode_adapter  →  opencode CLI
├── claude_adapter   →  Claude CLI  
├── zoo_adapter      →  agent-zoo
└── [你可以添加更多]
```

## 快速开始

```python
from h_agent.adapters import get_adapter, list_adapters

# 列出所有可用适配器
print(list_adapters())
# ['opencode', 'claude', 'zoo', 'zoo:xueqiu', 'zoo:liuliu', ...]

# 获取适配器
adapter = get_adapter("opencode")

# 发送消息
response = adapter.chat("实现一个计算器")
print(response.content)
```

## Opencode Adapter

### 基本用法

```python
from h_agent.adapters import get_adapter

# 获取 opencode 适配器
adapter = get_adapter("opencode")

# 发送消息
response = adapter.chat("""
创建一个简单的待办事项应用：
- 添加待办
- 列出待办
- 删除待办
""")

print(response.content)
print(f"工具调用: {len(response.tool_calls)}")
```

### 配置选项

```python
from h_agent.adapters.opencode_adapter import OpencodeAdapter

adapter = OpencodeAdapter(
    cwd="/path/to/project",     # 工作目录
    timeout=300,                # 超时时间(秒)
    agent="code",               # 使用的 agent
    model="gpt-4o",             # 模型
    opencode_path="opencode",   # CLI 路径
)

# 继续之前的会话
adapter.attach_session("session-id")

# 列出所有会话
sessions = adapter.get_session_list()
```

### 流式响应

```python
for token in adapter.stream_chat("写一个 hello world"):
    print(token, end="", flush=True)
```

## Claude Adapter

### 基本用法

```python
from h_agent.adapters import get_adapter

adapter = get_adapter("claude")

response = adapter.chat("""
审查以下代码并提出改进建议：
```python
def get_user(id):
    return db.query(id)
```
""")

print(response.content)
```

### 配置选项

```python
from h_agent.adapters.claude_adapter import ClaudeAdapter

adapter = ClaudeAdapter(
    cwd="/path/to/project",
    timeout=300,
    model="claude-sonnet-4-20250514",  # Claude 模型
    claude_path="claude",              # CLI 路径
    extra_args=["--no-stream"],         # 额外参数
)
```

### 会话管理

```python
# 获取会话 ID
print(adapter.session_id)

# 继续会话
adapter.attach_session("previous-session-id")

# 停止正在运行的请求
adapter.stop()
```

## Zoo Adapter

### 基本用法

```python
from h_agent.adapters import get_adapter

# 使用特定动物
adapter = get_adapter("zoo:xueqiu")

response = adapter.chat("搜索 React hooks 的最佳实践")
print(response.content)
```

### 可用动物

| 适配器名称 | 动物 | 特点 |
|-----------|------|------|
| zoo:xueqiu | 雪球猴 | 研究、搜索 |
| zoo:liuliu | 流水獭 | 架构、设计 |
| zoo:xiaohuang | 小黄狗 | 测试、调试 |
| zoo:heibai | 黑白熊 | 文档 |
| zoo:xiaozhu | 小猪 | DevOps |

### 配置

```python
from h_agent.adapters.zoo_adapter import ZooAdapter

adapter = ZooAdapter(
    animal="xueqiu",         # 动物名称
    cwd="/path/to/project",
    timeout=300,
    model="glm-4",           # 模型
    zoo_path="zoo",          # CLI 路径
)
```

## 团队集成

### 注册为团队成员

```python
from h_agent.team.team import AgentTeam, AgentRole

team = AgentTeam("my-project")

# 注册为适配器
team.register_adapter(
    name="coder",
    role=AgentRole.CODER,
    adapter_name="opencode",
    adapter_kwargs={"agent": "code"},
)

# 使用
result = team.delegate("coder", "task", "实现登录功能")
```

### Zoo 快速注册

```python
# 动物园成员
team.register_zoo_animal("xueqiu")     # 自动选择角色
team.register_zoo_animal("liuliu", AgentRole.CODER)
```

## 适配器状态

```python
adapter = get_adapter("opencode")

# 查看状态
print(adapter.status)  # AdapterStatus.IDLE

# 查看运行时间
print(f"运行时间: {adapter.uptime:.1f}s")

# 停止
adapter.stop()
```

## 错误处理

```python
from h_agent.adapters import get_adapter
from h_agent.adapters.base import AgentResponse

adapter = get_adapter("opencode")
response = adapter.chat("执行危险操作")

# 检查错误
if response.has_error():
    print(f"错误: {response.error}")
else:
    print(response.content)

# 检查是否完成（无 tool calls）
if response.is_complete():
    print("完成")
else:
    print(f"需要执行 {len(response.tool_calls)} 个工具")
```

## Tool Calls

```python
response = adapter.chat("创建文件")

# 遍历工具调用
for tool in response.tool_calls:
    print(f"工具: {tool.name}")
    print(f"参数: {tool.arguments}")
    print(f"结果: {tool.result}")
```

## 自定义适配器

### 创建新适配器

```python
from h_agent.adapters.base import (
    BaseAgentAdapter,
    AgentResponse,
    ToolCall,
    AdapterStatus,
)

class MyAdapter(BaseAgentAdapter):
    
    @property
    def name(self) -> str:
        return "my-adapter"
    
    def chat(self, message: str, **kwargs) -> AgentResponse:
        # 实现聊天逻辑
        return AgentResponse(
            content="响应内容",
            tool_calls=[],
        )
    
    def stream_chat(self, message: str, **kwargs):
        # 实现流式响应
        yield "部分"
        yield "响应"
    
    def stop(self):
        # 停止运行中的进程
        pass
```

### 注册适配器

```python
from h_agent.adapters import ADAPTER_REGISTRY

# 手动注册
ADAPTER_REGISTRY["my-adapter"] = MyAdapter

# 或使用装饰器
@ADAPTER_REGISTRY.register("my-adapter")
class MyAdapter(BaseAgentAdapter):
    ...
```

## CLI 用法

```bash
# 使用适配器
h-agent chat --adapter opencode "实现功能"

# 列出适配器
h-agent list-adapters

# 测试适配器
h-agent test-adapter opencode
```

## 配置

### 环境变量

```bash
# Opencode
export OPENCODE_PATH=/usr/local/bin/opencode
export OPENCODE_MODEL=gpt-4o

# Claude
export CLAUDE_PATH=/usr/local/bin/claude
export CLAUDE_MODEL=claude-sonnet-4-20250514

# Zoo
export ZOO_PATH=zoo
export ZOO_TIMEOUT=300
export ZOO_API_KEY=your_key
```

### 适配器优先级

```python
ADAPTER_PRIORITY = [
    "opencode",    # 优先使用 opencode
    "claude",
    "zoo",
]
```

## 最佳实践

### 1. 使用上下文管理器

```python
from h_agent.adapters import get_adapter

with get_adapter("opencode") as adapter:
    response = adapter.chat("实现功能")
    # 自动清理
```

### 2. 处理超时

```python
adapter = get_adapter("opencode")
adapter.timeout = 60  # 1分钟超时

try:
    response = adapter.chat("复杂任务")
except Exception as e:
    print(f"失败: {e}")
```

### 3. 并发限制

```python
import threading

# 同一适配器实例不应并发使用
adapter = get_adapter("opencode")

lock = threading.Lock()
with lock:
    response = adapter.chat("任务")
```

### 4. 会话管理

```python
# 对于需要上下文的适配器，使用会话
adapter = get_adapter("opencode")
session_id = None

for message in conversation:
    if session_id:
        adapter.attach_session(session_id)
    response = adapter.chat(message)
    session_id = adapter.session_id
```
