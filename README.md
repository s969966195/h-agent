# h-agent

OpenAI-powered coding agent harness with modular architecture.

## 项目介绍

`h-agent` 是一个基于 OpenAI API 的编程智能体框架，提供模块化架构，支持 CLI 交互、工具调用、会话管理、子智能体等特性。

## 安装

```bash
pip install h-agent
```

或从源码安装：

```bash
git clone https://github.com/user/h-agent.git
cd h-agent
pip install -e .
```

## 快速开始

```bash
# 交互模式
h-agent

# 单次命令模式
h-agent "帮我写一个快速排序"
```

## 配置

### 方式一：.env 文件

在项目根目录创建 `.env`：

```env
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_ID=gpt-4o
```

### 方式二：~/.h-agent/config.yaml

```yaml
api_base_url: https://api.openai.com/v1
model_id: gpt-4o
context_safe_limit: 180000
```

### 方式三：CLI 命令

```bash
# 设置 API Key（安全存储）
h-agent config --api-key YOUR_KEY

# 显示当前配置
h-agent config --show

# 设置其他选项
h-agent config --base-url https://api.deepseek.com/v1
h-agent config --model deepseek-chat
```

**配置优先级**：`.env` > `~/.h-agent/secrets.yaml` > `~/.h-agent/config.yaml` > 默认值

## 项目结构

```
h-agent/
├── h_agent/
│   ├── __init__.py
│   ├── __main__.py
│   ├── core/
│   │   ├── agent_loop.py    # 核心智能体循环
│   │   ├── config.py        # 配置管理
│   │   └── tools.py         # 工具定义
│   ├── features/
│   │   ├── sessions.py      # 会话持久化
│   │   ├── channels.py      # 多渠道支持
│   │   ├── rag.py           # 代码 RAG
│   │   ├── subagents.py     # 子智能体
│   │   └── skills.py        # 动态技能
│   └── cli/
│       └── commands.py      # CLI 命令
├── pyproject.toml
├── README.md
└── tests/
```

## 核心模块

### h_agent.core

- `agent_loop` - 核心循环，工具执行
- `tools` - 工具定义（bash, read, write, edit, glob）
- `config` - 配置管理，支持多来源加载

### h_agent.features

- `sessions` - 会话持久化
- `channels` - 多渠道通信
- `rag` - 代码语义搜索
- `subagents` - 隔离子智能体
- `skills` - 动态技能加载

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/

# 带 RAG 支持安装
pip install -e ".[rag]"
```

## License

MIT
