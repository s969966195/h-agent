# Memory Guide

h-agent 的记忆系统，支持短期、长期和上下文记忆。

## 概述

记忆系统分为三层：
1. **上下文记忆** - 当前会话的上下文
2. **短期记忆** - 最近交互的摘要
3. **长期记忆** - 跨会话的持久化知识

## 快速开始

```python
from h_agent.memory import Memory, LongTermMemory

# 创建记忆实例
memory = Memory()

# 添加记忆
memory.add("用户询问了 Python 异步编程", importance=8)

# 获取相关记忆
context = memory.get_relevant("异步编程")
print(context)

# 保存会话
memory.save_session("session-123", summary="讨论了异步编程")
```

## 上下文记忆

### 管理上下文

```python
from h_agent.memory.context import ContextManager

ctx = ContextManager(
    max_tokens=100000,  # 最大 token 数
    reserved_tokens=5000,  # 保留空间
)

# 添加上下文
ctx.add("系统: 你是一个助手", role="system")
ctx.add("用户: 帮我写个函数", role="user")
ctx.add("助手: 当然可以...", role="assistant")

# 获取完整上下文
messages = ctx.get_messages()

# 获取压缩上下文（超限时）
compressed = ctx.get_compressed()

# 估计当前 token 数
tokens = ctx.estimate_tokens()
```

### 上下文窗口

```python
# 设置上下文窗口
ctx.set_window(
    system="你是一个 Python 助手",
    max_history=10,  # 最近 10 轮对话
)

# 添加对话
ctx.add_message("用户", "什么是装饰器?")
ctx.add_message("助手", "装饰器是...")
ctx.add_message("用户", "给个例子")

# 获取窗口内容
messages = ctx.get_window()
```

## 短期记忆

### 记忆管理器

```python
from h_agent.memory import Memory

memory = Memory(
    max_items=100,  # 最大记忆条目
    importance_threshold=5,  # 重要性阈值
)

# 添加记忆
memory.add(
    "用户喜欢使用 Python",
    importance=7,
    tags=["python", "preference"],
)

memory.add(
    "项目使用 FastAPI 框架",
    importance=9,
    tags=["project", "fastapi"],
)

# 获取最近记忆
recent = memory.get_recent(limit=10)

# 搜索相关记忆
relevant = memory.get_relevant("Python 异步")

# 总结记忆
summary = memory.summarize()
```

### 记忆结构

```python
# 记忆条目
memory.add(
    content="用户工作邮箱是 user@company.com",
    importance=8,
    category="user_info",
    tags=["email", "work"],
    metadata={"source": "conversation"},
)

# 获取分类记忆
email_memories = memory.get_by_category("user_info")

# 获取带标签的记忆
python_memories = memory.get_by_tags(["python"])
```

## 长期记忆

### 持久化存储

```python
from h_agent.memory.long_term import LongTermMemory

# 创建长期记忆存储
ltm = LongTermMemory(
    db_path="~/.h-agent/memory/long_term.db",
)

# 添加记忆
ltm.add(
    content="用户偏好深色主题",
    memory_type="preference",
    importance=7,
)

# 搜索记忆
results = ltm.search("主题 配色")
for result in results:
    print(f"{result['content']} (相关度: {result['score']})")

# 获取记忆
memory = ltm.get(memory_id)

# 更新记忆
ltm.update(memory_id, content="新内容")

# 删除记忆
ltm.delete(memory_id)
```

### 记忆检索

```python
# 语义搜索
results = ltm.search(
    "用户在哪个城市",
    limit=5,
    memory_types=["personal"],
)

# 时间范围搜索
from datetime import datetime, timedelta
recent = ltm.search_by_time(
    start=datetime.now() - timedelta(days=7),
    end=datetime.now(),
)

# 统计
stats = ltm.get_stats()
print(f"总记忆数: {stats['total']}")
print(f"按类型: {stats['by_type']}")
```

## 记忆总结

### 自动总结

```python
from h_agent.memory.summarizer import Summarizer

summarizer = Summarizer(
    model="gpt-4o-mini",
    api_key="sk-...",
)

# 总结对话
summary = await summarizer.summarize_conversation(messages)

# 增量总结（适用于长对话）
previous_summary = "用户问了一些 Python 问题"
new_summary = await summarizer.summarize_incremental(
    previous_summary,
    new_messages,
)

# 提取关键信息
entities = await summarizer.extract_entities(messages)
# {'people': ['John'], 'organizations': [], 'topics': ['Python']}
```

### 记忆压缩

```python
# 压缩低重要性记忆
memory.compact(
    keep_high_importance=True,
    target_size=50,
)

# 按时间压缩
memory.compact_by_time(
    older_than=datetime.now() - timedelta(days=30),
)
```

## 会话管理

### 保存和加载会话

```python
# 保存会话
from h_agent.memory import SessionManager

sm = SessionManager()

session_id = sm.save_session(
    messages=[
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
    ],
    metadata={
        "user_id": "user-123",
        "topic": "general",
    },
)

# 加载会话
session = sm.load_session(session_id)
messages = session["messages"]

# 列出会话
sessions = sm.list_sessions(
    limit=10,
    filter_by={"user_id": "user-123"},
)
```

### 会话摘要

```python
# 自动生成摘要
summary = sm.generate_summary(session_id)

# 更新摘要
sm.update_summary(session_id, "用户询问了 API 使用方法")

# 搜索会话
found = sm.search_sessions("API 使用")
```

## 检索增强

### RAG 检索

```python
from h_agent.features.rag import MemoryRetriever

retriever = MemoryRetriever(
    memory_backend="chroma",  # 或 "sqlite"
    embedding_model="all-MiniLM-L6-v2",
)

# 添加到检索索引
retriever.add_memory(
    content="用户使用 FastAPI 框架",
    metadata={"source": "conversation"},
)

# 检索
results = retriever.retrieve(
    query="用户用什么框架?",
    limit=3,
)

# 为 agent 提供上下文
context = retriever.get_context_for_agent(query)
```

## 最佳实践

### 1. 重要性评分

```python
# 高重要性 (>7): 关键决策、用户偏好、任务目标
memory.add("用户要在月底前完成项目", importance=9)

# 中等重要性 (4-6): 一般信息、临时状态
memory.add("当前在讨论认证模块", importance=5)

# 低重要性 (<4): 闲聊、日常交互
memory.add("用户说了谢谢", importance=2)
```

### 2. 标签使用

```python
# 使用标签组织记忆
memory.add("用户在中国", tags=["location", "personal"])

# 批量获取
relevant = memory.get_by_tags(["location", "work"])
```

### 3. 定期清理

```python
# 清理低价值记忆
memory.cleanup(min_importance=3)

# 合并相似记忆
memory.merge_similar(threshold=0.8)
```

### 4. 会话隔离

```python
# 不同用户/项目使用不同会话
session_manager = SessionManager()

# 项目 A 会话
session_a = session_manager.create_session(project="project-a")

# 项目 B 会话
session_b = session_manager.create_session(project="project-b")
```

## 配置

### 存储配置

```python
from h_agent.memory import MemoryConfig

config = MemoryConfig(
    # 存储路径
    storage_dir="~/.h-agent/memory",
    
    # 短期记忆
    short_term_max=100,
    short_term_importance_threshold=5,
    
    # 长期记忆
    long_term_enabled=True,
    long_term_db="sqlite",
    
    # RAG
    rag_enabled=True,
    embedding_model="all-MiniLM-L6-v2",
)

memory = Memory(config=config)
```

### 环境变量

```bash
# 记忆存储
export MEMORY_STORAGE_DIR=~/.h-agent/memory

# RAG 配置
export RAG_EMBEDDING_MODEL=all-MiniLM-L6-v2
export RAG_VECTOR_DB=chroma
```
