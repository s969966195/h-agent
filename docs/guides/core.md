# 核心模块

*"时间不在于你拥有多少，而在于你如何使用。"* — 艾克

本文档介绍 h-agent 的三大核心模块：`agent_loop`（智能体循环）、`config`（配置管理）、`tools`（工具系统）。

---

## 1. agent_loop — 核心智能体循环

### 功能概述

`agent_loop` 是 h-agent 的核心引擎，负责：
- 调用 LLM API 并处理响应
- 检测和执行工具调用
- 管理多轮对话消息流
- 处理 OpenAI 兼容格式的工具调用

### 工作原理

```
用户输入 → 消息历史 → LLM (带工具) → 
  ├─ 无 tool_calls → 返回最终回答
  └─ 有 tool_calls → 执行工具 → 结果作为 tool 消息 → 再次调用 LLM → ...
```

### 基本使用

```python
from h_agent.core.agent_loop import agent_loop

# 准备消息历史
messages = [
    {"role": "system", "content": "你是一个代码助手。"},
    {"role": "user", "content": "帮我读取当前的 README.md"}
]

# 启动智能体循环
agent_loop(messages)

# 消息历史已被修改，包含完整的 tool 调用记录
print(messages[-1]["content"])
```

### 程序化调用

```python
from h_agent.core.agent_loop import agent_loop, client, MODEL

messages = [{"role": "user", "content": "列出当前目录下所有 .py 文件"}]
agent_loop(messages)
```

### 手动单步调用

```python
from openai import OpenAI
import os, json

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)

response = client.chat.completions.create(
    model=os.getenv("MODEL_ID", "gpt-4o"),
    messages=[{"role": "user", "content": "你好"}],
    tools=[],  # 无工具调用
)
print(response.choices[0].message.content)
```

### 注意事项

- `agent_loop` 会**修改传入的 `messages` 列表**，追加 assistant 和 tool 消息
- 危险命令（`rm -rf /`、`mkfs` 等）会被自动拦截
- 默认超时 120 秒，超时可通过 `timeout` 参数调整（最大 300 秒）
- 输出超过 50000 字符会被截断
- 支持所有 OpenAI 兼容 API（DeepSeek、Azure、Ollama 等）

---

## 2. config — 配置管理系统

### 功能概述

配置系统支持多配置Profile、环境变量、YAML 文件三层优先级：

```
环境变量 (.env) > ~/.h-agent/secrets.yaml > ~/.h-agent/config.yaml > 默认值
```

### 核心配置项

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | API Key | - |
| `OPENAI_BASE_URL` | API Base URL | `https://api.openai.com/v1` |
| `MODEL_ID` | 模型 ID | `gpt-4o` |
| `WORKSPACE_DIR` | 工作目录 | `.agent_workspace` |
| `CONTEXT_SAFE_LIMIT` | 上下文安全限制 | `180000` tokens |
| `H_AGENT_PORT` | Daemon 通信端口 | `19527` |
| `H_AGENT_TOOL_TIMEOUT` | 工具默认超时 | `120` 秒 |
| `MAX_TOOL_OUTPUT` | 工具输出最大长度 | `50000` 字符 |

### 查看配置

```bash
# 显示当前完整配置
h-agent config --show

# 列出所有配置Profile
h-agent config --list-all

# 导出配置为 JSON
h-agent config --export
```

### 设置配置

```bash
# 设置 API Key（直接输入）
h-agent config --api-key sk-xxxx

# 安全输入 API Key（交互式提示）
h-agent config --api-key __prompt__

# 设置 Base URL（用于 DeepSeek、Ollama 等）
h-agent config --base-url https://api.deepseek.com/v1

# 设置模型
h-agent config --model deepseek-chat

# 清除 API Key
h-agent config --clear-key

# 交互式配置向导
h-agent config --wizard
```

### 程序化使用

```python
from h_agent.core.config import (
    MODEL, OPENAI_BASE_URL, OPENAI_API_KEY,
    list_config, get_current_profile, set_current_profile,
    create_profile
)

# 读取当前配置
print(f"Model: {MODEL}")
print(f"API URL: {OPENAI_BASE_URL}")

# 查看所有配置项
all_config = list_config()
print(all_config)

# 切换 Profile
set_current_profile("deepseek")

# 创建新 Profile
create_profile("azure", copy_from="default")
```

### 多 Profile 管理

```bash
# 创建新 Profile
h-agent config --profile-create work

# 切换到指定 Profile
h-agent config --profile work

# 删除 Profile
h-agent config --profile-delete old-profile
```

### 注意事项

- API Key 建议通过 `h-agent config --api-key __prompt__` 交互输入，避免泄露
- Profile 配置文件存储在 `~/.h-agent/config.<name>.yaml`
- `.env` 文件优先级最高，适合项目级配置覆盖
- Windows 配置文件在 `%APPDATA%\h-agent\`

---

## 3. tools — 工具系统

### 功能概述

h-agent 的工具系统基于**分发映射（Dispatch Map）** 架构：

```
工具定义 (TOOLS) + 工具处理器 (TOOL_HANDLERS) = 完整工具
```

添加新工具只需注册 handler，循环逻辑不变。

### 内置核心工具

| 工具名 | 说明 | 核心参数 |
|--------|------|---------|
| `bash` | 执行 Shell 命令 | `command`, `timeout` |
| `read` | 读取文件 | `path`, `offset`, `limit` |
| `write` | 写入文件 | `path`, `content` |
| `edit` | 精确编辑文件 | `path`, `old_text`, `new_text` |
| `glob` | 查找匹配文件 | `pattern`, `path` |

### 工具调用执行

```python
from h_agent.core.tools import execute_tool_call, TOOL_HANDLERS

# 单个工具调用
tool_call = ...  # 从 LLM 响应中获取
result = execute_tool_call(tool_call)
print(result)
```

### 扩展工具注册

```python
from h_agent.core.tools import TOOL_HANDLERS, TOOLS

# 注册自定义工具处理器
def my_tool(arg1: str, arg2: int) -> str:
    return f"处理了 {arg1}, {arg2}"

TOOL_HANDLERS["my_tool"] = my_tool

# 注册工具定义（OpenAI 格式）
TOOLS.append({
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "我的自定义工具",
        "parameters": {
            "type": "object",
            "properties": {
                "arg1": {"type": "string"},
                "arg2": {"type": "integer"}
            },
            "required": ["arg1"]
        }
    }
})
```

### 扩展工具模块

`h_agent/tools/` 下的扩展模块会自动合并：

```python
# 实际等效于执行了以下合并：
from h_agent.tools import ALL_TOOLS, ALL_HANDLERS
# ALL_TOOLS = GIT_TOOLS + FILE_TOOLS + SHELL_TOOLS + DOCKER_TOOLS + HTTP_TOOLS + JSON_TOOLS
# ALL_HANDLERS 包含所有工具的处理器
```

### 注意事项

- 工具名必须全局唯一，重复会覆盖
- `bash` 工具危险命令黑名单：`rm -rf /`、`sudo rm`、`mkfs`、`dd if=`、`> /dev/sd`
- 大文件（>10MB）读取会自动流式处理并显示进度条
- 插件工具也会被自动加载到工具列表

---

## 三者关系

```
config.py          ← 配置加载（API Key、模型、超时等）
    ↓
agent_loop.py      ← 核心循环（调用 LLM + 分发工具）
    ↓
tools.py           ← 工具执行（bash/read/write/edit/glob + 扩展 + 插件）
```

`config` 提供运行时参数，`agent_loop` 驱动对话流程，`tools` 提供实际操作能力。三者协同工作，构成 h-agent 的核心骨架。
