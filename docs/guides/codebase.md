# Codebase Guide

代码库索引和语义搜索，让 AI 能够理解你的项目结构。

## 概述

Codebase 模块提供：
- **项目索引** - 扫描和索引项目文件
- **语义搜索** - 用自然语言搜索代码
- **上下文生成** - 为开发任务生成完整上下文

## 快速开始

```python
from h_agent.codebase import CodebaseIndex, CodeSearch, ContextGenerator

# 1. 索引项目
index = CodebaseIndex("/path/to/project")
info = index.scan()
print(f"索引了 {info['file_count']} 个文件, {info['chunk_count']} 个代码块")

# 2. 搜索代码
search = CodeSearch()
results = search.search("用户认证逻辑")

# 3. 生成开发上下文
generator = ContextGenerator()
ctx = generator.generate_context(
    project_path="/path/to/project",
    task="添加用户评论功能"
)
print(ctx.to_markdown())
```

## 项目索引

### 基本用法

```python
from h_agent.codebase import CodebaseIndex

# 创建索引
index = CodebaseIndex("/path/to/project")

# 全量扫描
info = index.scan(incremental=False)

# 增量更新（只重新索引修改过的文件）
info = index.scan(incremental=True)

# 获取项目信息
info = index.get_info()
print(info)
# {
#     'project_name': 'myapp',
#     'file_count': 150,
#     'chunk_count': 892,
#     'languages': {'python': 450, 'javascript': 442},
#     'scan_time': 1699999999.0
# }
```

### 支持的语言

自动识别并提取代码块：

| 语言 | 支持的块类型 |
|------|-------------|
| Python | class, function, method |
| JavaScript/TypeScript | function, class |
| Go | function |
| Rust | function, struct |
| Java | class, method |
| Ruby | method, class |
| Vue | script, template |

### 手动扫描

```python
from h_agent.codebase.indexer import FileIndexer

# 只扫描文件不过索引
indexer = FileIndexer("/path/to/project")
files = indexer.scan_project()

# 查看目录树
tree = indexer.get_directory_tree()

# 获取修改的文件
import time
since = time.time() - 86400  # 过去24小时
changed = indexer.get_changed_files(since)
```

## 语义搜索

### 基本搜索

```python
from h_agent.codebase import CodeSearch

search = CodeSearch()

# 自然语言查询
results = search.search("处理用户登录")

# 搜索结果
for result in results:
    print(f"{result.name} ({result.similarity:.2%})")
    print(f"  {result.file_path}:{result.start_line}")
    print(f"  {result.source_code[:100]}...")
```

### 过滤搜索

```python
# 按文件类型过滤
results = search.search(
    "数据库操作",
    chunk_types=["function", "method"],  # 只搜索函数/方法
)

# 按语言过滤
results = search.search(
    "API 路由",
    languages=["python", "go"],  # 只搜索 Python 和 Go
)

# 按相似度过滤
results = search.search(
    "认证",
    min_similarity=0.5,  # 至少 50% 相似度
)
```

### 项目特定搜索

```python
# 只在特定项目中搜索
results = search.search(
    "缓存实现",
    project_path="/path/to/project",
    top_k=10,  # 返回更多结果
)
```

### 查找相似代码

```python
# 找到某个代码块相似的其他代码
similar = search.find_similar_chunks(
    chunk_id="auth.user_login",
    project_path="/path/to/project",
)

# 查看某个文件的所有代码块
file_chunks = search.search_by_file(
    file_path="src/auth.py",
    project_path="/path/to/project",
)
```

## 上下文生成

### 生成任务上下文

```python
from h_agent.codebase import ContextGenerator

generator = ContextGenerator()

# 为开发任务生成上下文
ctx = generator.generate_context(
    project_path="/path/to/project",
    task="添加社交分享功能",
    top_k=5,  # 相关代码数量
    min_similarity=0.3,  # 最低相似度
)

# 输出为 Markdown
print(ctx.to_markdown())
```

### 输出格式

Markdown 输出包含：

```
# Development Context: 添加社交分享功能

**Project:** myapp
**Path:** /path/to/project

## Project Overview
- Files: 150
- Code chunks: 892
- Total lines: 45,230

### Languages
- python: 450 chunks
- javascript: 442 chunks

## Relevant Files
- `src/share.py` (python) - 1 class(es), including ShareService
- `src/models/post.py` (python) - 1 class(es), including Post

## Relevant Code

### 1. ShareService (class)
**File:** `src/share.py` (lines 15-80)
**Similarity:** 85.2%

```python
class ShareService:
    def __init__(self, db):
        self.db = db
    
    def share_to_social(self, platform, content):
        ...
```

## Cross-Project Patterns

### class: service
**Similarity:** 82.5%
**Files:** src/share.py, src/email.py, src/notification.py

Found 3 similar class(es) named 'service'
```

### 快速上下文

```python
# 一行代码获取上下文
generator = ContextGenerator()
markdown = generator.quick_context(
    project_path="/path/to/project",
    task="添加评论功能",
)
print(markdown)
```

## CLI 用法

```bash
# 索引项目
python -m h_agent.codebase /path/to/project scan

# 搜索代码
python -m h_agent.codebase /path/to/project search "用户认证"

# 生成上下文
python -m h_agent.codebase /path/to/project context "添加分享功能"
```

## 配置

### 索引存储

默认存储在 `~/.h-agent/codebase_index/`

```python
from h_agent.codebase import CodebaseIndex
from pathlib import Path

# 自定义索引目录
index = CodebaseIndex(
    "/path/to/project",
    index_dir=Path("/custom/path"),
)
```

### 嵌入模型

```python
from h_agent.codebase import CodeSearch

# 使用高级嵌入（需要 sentence-transformers）
search = CodeSearch(
    embedder_model="all-MiniLM-L6-v2",  # 默认
    use_advanced_embeddings=True,
)

# 或使用简单的 TF-IDF 嵌入（无依赖）
search = CodeSearch(
    use_advanced_embeddings=False,
)
```

安装 sentence-transformers:
```bash
pip install sentence-transformers
```

## 最佳实践

### 1. 定期增量索引

```python
# CI/CD 中增量索引
index = CodebaseIndex(project_path)
index.scan(incremental=True)  # 只更新修改的文件
```

### 2. 限制结果数量

```python
# 避免返回过多结果
results = search.search(
    "认证",
    top_k=5,  # 限制数量
    min_similarity=0.4,  # 提高阈值
)
```

### 3. 结合上下文使用

```python
# 搜索 + 上下文生成
search = CodeSearch()
ctx = generator.generate_context(
    project_path=project,
    task=task_description,
    top_k=3,  # 少量相关代码即可
)

# 将上下文传给 AI
response = openai.chat.completions.create(
    messages=[
        {"role": "system", "content": "你是一个助手。"},
        {"role": "user", "content": ctx.to_markdown()},
    ],
)
```
