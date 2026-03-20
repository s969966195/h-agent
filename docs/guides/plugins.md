# 插件系统

*"每个规则都需要被打破一次。"* — 艾克

h-agent 的插件系统允许动态加载扩展模块，为 Agent 添加新工具和能力。

---

## 1. 概述

### 插件 vs 技能 vs 内置工具

| 类型 | 加载时机 | 说明 |
|------|----------|------|
| 内置工具 | 启动时 | `h_agent/tools/` 下模块（Git、Docker、HTTP 等） |
| 技能 (Skill) | 按需 | Markdown 文件，被 `load_skill` 工具调用 |
| 插件 (Plugin) | 启动时 | Python 模块，可注册工具、处理器、Channel |

### 插件结构

```
h_agent/plugins/
├── __init__.py          # 插件管理器
├── web_tools.py         # 内置 Web 工具插件
└── <第三方插件>/         # 用户安装的插件
    ├── __init__.py
    └── ...
```

---

## 2. 安装和管理

### 命令行管理

```bash
# 列出所有插件
h-agent plugin list

# 查看插件详情
h-agent plugin info my-plugin

# 启用插件
h-agent plugin enable my-plugin

# 禁用插件
h-agent plugin disable my-plugin

# 安装插件（从 URL 或 git 仓库）
h-agent plugin install https://github.com/user/h-agent-myplugin

# 卸载插件
h-agent plugin uninstall my-plugin
```

### 插件列表输出示例

```
$ h-agent plugin list
Plugins:
  ✓ web_tools    v1.0.0  - Web 抓取和处理工具
  ✓ docker_helper v0.2.0  - Docker 扩展
  ✗ custom_auth   v0.1.0  - 自定义认证 (disabled)
```

---

## 3. 编写插件

### 最小插件示例

```python
# my_plugin/__init__.py
"""
My Custom Plugin - 为 h-agent 添加自定义工具
"""

from typing import List, Dict, Any

PLUGIN_NAME = "my_plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "自定义插件示例"
PLUGIN_AUTHOR = "Your Name"

# ─── 工具定义 (OpenAI function calling 格式) ───

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "my_tool",
            "description": "我的自定义工具，执行特定任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_text": {
                        "type": "string",
                        "description": "输入文本"
                    }
                },
                "required": ["input_text"]
            }
        }
    }
]

# ─── 工具处理器 ───

def my_tool_handler(input_text: str) -> str:
    """处理输入文本并返回结果"""
    return f"处理结果: {input_text.upper()}"

TOOL_HANDLERS = {
    "my_tool": my_tool_handler,
}

# ─── 初始化函数（可选）───

def on_load():
    """插件加载时调用"""
    print(f"{PLUGIN_NAME} v{PLUGIN_VERSION} loaded!")

def on_unload():
    """插件卸载时调用"""
    print(f"{PLUGIN_NAME} unloaded!")
```

### 注册到插件系统

插件被 `h_agent/plugins/__init__.py` 自动发现和加载：

```python
from h_agent.plugins import Plugin, _discover_plugins, load_plugin

# 发现 plugins/ 目录下的插件
plugin_paths = _discover_plugins()
for path in plugin_paths:
    plugin = load_plugin(path)
    print(f"Loaded: {plugin.name}")
```

---

## 4. 插件工具加载流程

```
启动时:
  1. h_agent.core.tools 导入 h_agent.plugins
  2. plugins/__init__.py 执行 load_all_plugins()
  3. 遍历 ~/.h-agent/plugins.json 中的启用插件
  4. 调用 get_enabled_tools() 获取所有插件工具
  5. 合并到 TOOLS 列表（去重）
  6. 调用 get_enabled_handlers() 获取处理器
  7. 合并到 TOOL_HANDLERS 字典

运行时:
  - Agent 调用工具 → execute_tool_call()
  → 在 TOOL_HANDLERS 中查找处理器
  → 执行并返回结果
```

---

## 5. 插件配置

### 插件状态存储

插件启用/禁用状态保存在 `~/.h-agent/plugins.json`：

```json
{
  "plugins": {
    "web_tools": true,
    "docker_helper": true,
    "custom_auth": false
  }
}
```

### 程序化配置

```python
from h_agent.plugins import (
    get_plugin_state, save_plugin_state,
    enable_plugin, disable_plugin
)

# 获取所有插件状态
state = get_plugin_state()
print(state)

# 启用插件
enable_plugin("my_plugin")

# 禁用插件
disable_plugin("my_plugin")

# 保存状态
save_plugin_state({"web_tools": True, "custom": False})
```

---

## 6. 内置插件：web_tools

`h_agent/plugins/web_tools.py` 是默认内置插件，提供 Web 相关工具：

### 可用工具

| 工具 | 说明 |
|------|------|
| `web_fetch` | 获取 URL 内容（提取可读文本） |
| `web_search` | 搜索引擎查询 |

### 使用示例

```python
# 抓取网页内容
from h_agent.plugins.web_tools import web_fetch_tool

result = web_fetch_tool(
    url="https://example.com",
    max_chars=5000
)
print(result)

# Web 搜索
from h_agent.plugins.web_tools import web_search_tool

results = web_search_tool(
    query="Python async tutorial",
    count=5
)
print(results)
```

---

## 7. 插件发布与分发

### 发布到插件市场

插件可以发布到 `h-agent-plugins` 仓库：

```bash
# 目录结构
h-agent-plugins/
└── index.json    # 插件索引
    ├── my_plugin/
    │   ├── __init__.py
    │   └── README.md
    └── another_plugin/
```

### index.json 格式

```json
{
  "plugins": [
    {
      "name": "my_plugin",
      "version": "1.0.0",
      "description": "我的自定义插件",
      "author": "Your Name",
      "url": "https://github.com/user/h-agent-my-plugin",
      "tools": ["my_tool"],
      "dependencies": []
    }
  ]
}
```

---

## 8. 注意事项

- 插件工具名不能与内置工具同名（同名的会被忽略）
- 插件加载失败不会导致主程序崩溃，只会在日志中记录错误
- 插件可以注册 Channel 扩展，实现自定义消息渠道
- 插件的 `on_load()` 函数在插件启用时调用，`on_unload()` 在禁用时调用
- 第三方插件来源需谨慎，建议只在可信来源安装
