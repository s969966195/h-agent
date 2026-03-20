# 功能模块

*"不要放弃，直到做对为止。"* — 艾克

h-agent 提供五大功能模块：会话管理（sessions）、多渠道（channels）、代码库 RAG、动态技能（skills）、子智能体（subagents）。

---

## 1. sessions — 会话持久化

### 功能概述

会话系统基于 JSONL 文件持久化存储，支持：
- 多会话并行管理
- 上下文自动加载/保存
- 上下文溢出时自动摘要压缩
- 会话标签和分组管理

### 核心组件

```
SessionStore   — JSONL 持久化（写入追加，读取重放）
ContextGuard   — 三阶段溢出重试（截断 → 摘要 → 重试）
```

### 命令行使用

```bash
# 列出所有会话
h-agent session list

# 创建新会话
h-agent session create
h-agent session create --name myproject

# 创建带分组的会话
h-agent session create --name review --group code

# 查看会话历史
h-agent session history <session_id>

# 删除会话
h-agent session delete <session_id>

# 搜索会话
h-agent session search "登录功能"

# 重命名会话
h-agent session rename <session_id> new-name

# 标签管理
h-agent session tag list           # 列出所有标签
h-agent session tag add <id> bug   # 添加标签
h-agent session tag remove <id> bug # 删除标签
h-agent session tag get <id>       # 查看会话标签

# 分组管理
h-agent session group list         # 列出所有分组
h-agent session group set <id> frontend  # 设置分组
h-agent session group sessions frontend   # 查看分组下的会话
```

### 程序化使用

```python
from h_agent.session.manager import SessionManager, get_manager

mgr = get_manager()

# 创建会话
session_id = mgr.create_session(name="my-task", group="work")
print(f"Created: {session_id}")

# 保存用户消息
mgr.save_turn(session_id, role="user", content="帮我实现用户登录")

# 保存助手回复
mgr.save_turn(session_id, role="assistant", content="好的，开始实现...")

# 获取会话历史
messages = mgr.load_session(session_id)
for msg in messages:
    print(f"[{msg['role']}]: {msg['content'][:50]}")

# 列出所有会话
sessions = mgr.list_sessions()
for s in sessions:
    print(f"{s['session_id']} - {s.get('name', 'unnamed')}")

# 删除会话
mgr.delete_session(session_id)
```

### 会话过滤

```bash
# 按标签过滤
h-agent session list --tag bug

# 按分组过滤
h-agent session list --group frontend
```

### 注意事项

- 会话文件存储在 `~/.agent_workspace/sessions/<agent_id>/`
- 上下文超限时自动进行摘要压缩
- 会话 ID 支持名称匹配（优先精确匹配，再按名称匹配）
- JSONL 格式支持追加写入，断电不丢数据

---

## 2. channels — 多渠道支持

### 功能概述

同一 Agent 大脑，多个通信渠道。Channel 抽象统一了不同平台的消息格式。

### 支持的渠道

| 渠道 | 说明 | 触发条件 |
|------|------|---------|
| CLI | 标准输入输出 | 直接运行 `h-agent chat` |
| Telegram | 电报机器人 | 设置 `TELEGRAM_BOT_TOKEN` |
| 扩展渠道 | 可插拔 | 实现 `Channel` 抽象类 |

### 消息格式抽象

```python
from h_agent.features.channels import InboundMessage, OutboundMessage, Channel

@dataclass
class InboundMessage:
    text: str          # 消息文本
    sender_id: str     # 发送者 ID
    channel: str        # 渠道名称
    account_id: str     # 账号标识
    peer_id: str        # 群组/频道 ID
    is_group: bool      # 是否群组消息
    metadata: dict      # 附加元数据
```

### 实现自定义渠道

```python
from h_agent.features.channels import Channel, InboundMessage

class MyChannel(Channel):
    def __init__(self, account_id: str = "default"):
        super().__init__(account_id)
    
    def start(self):
        # 启动渠道监听
        pass
    
    def stop(self):
        # 停止渠道
        pass
    
    def send(self, message: OutboundMessage):
        # 发送消息到目标
        pass
```

### Telegram 渠道配置

```bash
export TELEGRAM_BOT_TOKEN=your-bot-token
export TELEGRAM_ADMIN_IDS=123456,789012  # 管理员 ID 列表
h-agent start
```

### 注意事项

- Channel 抽象统一了平台差异，Agent 循环只看到 `InboundMessage`
- 扩展新渠道只需实现 `Channel` 抽象类并注册
- Telegram 渠道需要公网可访问的 Webhook 或长轮询

---

## 3. rag — 代码库 RAG

### 功能概述

为 h-agent 添加代码库理解和语义搜索能力：
- 文件结构和符号索引
- 语义向量搜索（依赖 ChromaDB）
- 代码片段检索

### 命令行使用

```bash
# 索引代码库
h-agent rag index --directory ./src

# 搜索代码库
h-agent rag search "用户认证逻辑"
h-agent rag search "邮件发送" --limit 10

# 查看索引统计
h-agent rag stats
h-agent rag stats --directory ./src
```

### 程序化使用

```python
from h_agent.features.rag import (
    CodebaseRAG, get_rag_dir, get_rag_index_path
)

# 初始化 RAG
rag = CodebaseRAG()

# 索引目录
rag.index_directory("./src", file_types=[".py", ".js", ".go"])

# 语义搜索
results = rag.search("用户登录验证", top_k=5)
for r in results:
    print(f"{r['file']}:{r['line']} - {r['preview']}")

# 基于文件路径搜索
results = rag.search_by_path("./src/auth.py")

# 提取代码符号
symbols = rag.extract_symbols("./src/models.py")
for s in symbols:
    print(f"{s['type']}: {s['name']}")
```

### 注意事项

- 向量搜索需要安装 ChromaDB：`pip install chromadb`
- 语义嵌入需要 OpenAI API Key（用于生成 embedding）
- 大型代码库索引会有进度显示
- 索引文件存储在 `~/.h-agent/rag/`

---

## 4. skills — 动态技能

### 功能概述

技能是按需加载的知识模块。不同于启动时全部加载，skills 在需要时才注入上下文。

### 内置技能

| 技能 | 说明 |
|------|------|
| `coding-agent` | 委托编码任务到 Codex/Claude Code |
| `github` | GitHub 操作（issues、PRs、CI） |
| `gog` | Google Workspace（Gmail、Calendar、Drive） |
| `weather` | 天气查询 |
| `tavily` | AI 优化的网络搜索 |
| `find-skills` | 技能发现与安装 |

### 命令行使用

```bash
# 列出所有技能
h-agent skill list

# 包含禁用技能的完整列表
h-agent skill list --all

# 查看技能详情
h-agent skill info coding-agent

# 启用/禁用技能
h-agent skill enable github
h-agent skill disable weather

# 安装技能（通过 pip）
h-agent skill install tavily

# 卸载技能
h-agent skill uninstall old-skill

# 运行技能函数
h-agent skill run github issues --repo owner/repo --limit 5
```

### 程序化使用

```python
from h_agent.features.skills import (
    list_available_skills, load_skill_content, get_skill_info,
    call_skill_function, load_all_skills
)

# 列出可用技能
skills = list_available_skills()
print(skills)

# 获取技能信息
info = get_skill_info("github")
print(info)

# 加载技能内容（注入到 Agent 上下文）
content = load_skill_content("github")
print(content)

# 调用技能函数
load_all_skills()
result = call_skill_function("github", "list_issues", repo="owner/repo", limit=5)
print(result)
```

### 技能文件格式

技能以 Markdown 文件存储在 `skills/` 目录：

```markdown
# Skill Name

技能描述。

## 使用方法

### 函数名

```python
def my_function(arg1: str, arg2: int) -> str:
    # 实现
    pass
```

## 示例

...
```

### 注意事项

- 技能在 `skills/` 目录下以 `.md` 文件存在
- 技能通过 `load_skill()` 工具按需加载到 Agent 上下文
- 安装的 pip 包技能以 `h_agent_skill_<name>` 命名

---

## 5. subagents — 子智能体

### 功能概述

将复杂任务分解为独立子任务，每个子任务在干净上下文中执行，只返回结果摘要。

### 核心功能

- 独立消息历史（干净上下文）
- 聚焦任务描述
- 可配置工具集
- 执行步骤数限制
- 错误处理和超时

### 程序化使用

```python
from h_agent.features.subagents import run_subagent, SubagentResult

# 基本用法
result: SubagentResult = run_subagent(
    task="实现用户登录 API",
    context="参考 src/auth/login.py 的现有实现",
    max_steps=20,
)

if result.success:
    print(f"完成！用 {result.steps} 步")
    print(result.content)
else:
    print(f"失败: {result.error}")

# 指定工具
result = run_subagent(
    task="审查代码安全性",
    tools=[bash_tool, read_tool, git_tool],  # 只给这些工具
    max_steps=10,
)

# 带详细日志的运行
result = run_subagent(
    task="重构 UserService 类",
    context="src/services/user.py 需要抽取到独立模块",
    max_steps=30,
)
```

### 返回值

```python
@dataclass
class SubagentResult:
    success: bool       # 是否成功
    content: str        # 执行结果内容
    steps: int          # 消耗的步数
    error: Optional[str] = None  # 错误信息（如有）
```

### 注意事项

- 子智能体有独立上下文，主 Agent 的对话历史不会被污染
- 适合多步骤探索性任务（如调研、审查）
- 不适合短小任务，开销过大
- `max_steps` 默认 20，设置过小会导致任务无法完成

---

## 模块关系图

```
features/
├── sessions.py   ← 持久化 + 上下文管理（所有功能的基础）
├── channels.py   ← 多渠道接入（Telegram 等）
├── rag.py        ← 代码库理解（被 Agent 调用）
├── skills.py     ← 按需加载知识（被 Agent 调用）
└── subagents.py  ← 任务隔离执行（被 Agent 调用）
```

所有功能模块围绕 `agent_loop` 协同工作，sessions 提供持久化基础，channels/skills/rag/subagents 分别解决不同场景问题。
