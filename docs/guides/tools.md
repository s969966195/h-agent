# 内置工具

*"我宁愿犯错，也不愿什么都不做。"* — 艾克

h-agent 内置 36+ 个工具，覆盖 Shell、Git、文件、Docker、HTTP、JSON 等常用操作。所有工具均以 OpenAI function calling 格式定义，可被 Agent 自动调用。

---

## 工具总览

| 类别 | 工具数 | 工具名 |
|------|--------|--------|
| Shell | 4 | bash, shell_run, shell_env, shell_cd, shell_which |
| 文件 | 6 | read, write, edit, glob, file_read, file_write, file_edit, file_glob, file_exists, file_info |
| Git | 6 | git_status, git_commit, git_push, git_pull, git_log, git_branch |
| Docker | 6 | docker_ps, docker_logs, docker_exec, docker_images, docker_build, docker_pull |
| HTTP | 3 | http_get, http_post, http_head |
| JSON | 4 | json_parse, json_format, json_query, json_validate |
| 核心 | 5 | bash, read, write, edit, glob |

**注**：核心工具（bash/read/write/edit/glob）与扩展模块中的同名工具功能重叠，扩展模块提供更丰富的参数选项。

---

## 1. Shell 工具

### bash / shell_run — 执行命令

**bash**（核心工具，最常用）：

```python
# 基本用法
bash(command="ls -la")

# 带超时（秒）
bash(command="sleep 5 && echo done", timeout=10)

# 大文件输出自动流式处理
bash(command="find . -name '*.py' | wc -l")
```

**shell_run**（扩展工具，更多参数）：

```python
shell_run(
    command="git status",
    cwd="/path/to/repo",    # 指定工作目录
    timeout=60,              # 超时秒数
    shell=True               # 是否通过 shell 执行
)
```

**注意事项**：
- 危险命令（`rm -rf /`、`mkfs` 等）会被自动拦截
- 超时上限 300 秒（5 分钟）
- 输出超过 50000 字符会被截断

---

### shell_env — 环境变量

```python
# 查看所有环境变量
shell_env()

# 过滤查看（如只看 PATH 相关）
shell_env(filter="PATH")

# JSON 格式输出
shell_env(filter="", json=True)
```

---

### shell_cd — 切换目录

```python
# 切换 Agent 工作目录（影响后续 bash 等命令的默认 cwd）
shell_cd(path="/path/to/project")

# 相对路径
shell_cd(path="./src")
```

---

### shell_which — 查找命令

```python
# 查找可执行文件路径
shell_which(command="python3")

# 返回示例：/usr/bin/python3
```

---

## 2. 文件工具

### read / file_read — 读取文件

**read**（核心工具）：

```python
# 基本读取（前 2000 行）
read(path="README.md")

# 从第 10 行开始读，读 100 行
read(path="src/main.py", offset=10, limit=100)
```

**file_read**（扩展工具，更多选项）：

```python
file_read(
    path="src/main.py",
    offset=10,    # 起始行（1-indexed）
    limit=100     # 最大行数，0=全部
)
```

**注意事项**：
- 文件超过 10MB 自动显示进度
- 支持大文件分片读取
- 路径支持绝对路径和相对路径

---

### write / file_write — 写入文件

**write**（核心工具）：

```python
# 创建或覆盖文件
write(path="output.txt", content="Hello, world!")

# 追加模式（扩展参数）
file_write(path="log.txt", content="new line\n", append=True)
```

**注意事项**：
- 父目录不存在时自动创建
- 大文件（>5MB）写入会显示进度
- 覆盖前不会备份，请注意

---

### edit / file_edit — 精确编辑

**edit**（核心工具）：

```python
# 替换精确匹配的文本
edit(
    path="src/config.py",
    old_text="# DEBUG = False",
    new_text="DEBUG = True"
)
```

**file_edit**（扩展工具）：

```python
file_edit(
    path="src/config.py",
    old_text="# DEBUG = False",
    new_text="DEBUG = True"
)
```

**注意事项**：
- `old_text` 必须**精确匹配**（含所有空格和换行）
- 如果文件中有多个匹配会报错
- 适合小范围精确修改，大范围建议用 `write`

---

### glob / file_glob — 文件查找

**glob**（核心工具）：

```python
# 查找所有 Python 文件
glob(pattern="**/*.py")

# 在指定目录查找
glob(pattern="**/*.py", path="./src")
```

**file_glob**（扩展工具）：

```python
file_glob(
    pattern="**/*.md",
    path="/Users/sy/Projects"
)
```

---

### file_exists — 检查文件

```python
# 检查文件或目录是否存在
file_exists(path="src/main.py")
# 返回：True 或 False
```

---

### file_info — 文件元信息

```python
# 获取文件大小、修改时间等
file_info(path="src/main.py")
# 返回示例：{"size": 4096, "mtime": "2024-01-15T10:30:00", "type": "file"}
```

---

## 3. Git 工具

### git_status — 查看状态

```python
# 查看当前仓库状态
git_status()

# 指定仓库路径
git_status(path="/path/to/repo", short=True)
```

---

### git_commit — 提交更改

```python
# 提交所有更改
git_commit(message="feat: 添加用户登录功能", path="/path/to/repo")

# 允许空提交（触发 CI 等）
git_commit(message="chore: trigger CI", allow_empty=True)
```

---

### git_push — 推送到远程

```python
# 推送到默认远程
git_push(path="/path/to/repo")

# 推送到指定分支
git_push(remote="origin", branch="develop", path="/path/to/repo")
```

---

### git_pull — 从远程拉取

```python
# 从默认远程拉取
git_pull(path="/path/to/repo")

# 指定远程和分支
git_pull(remote="origin", branch="main", path="/path/to/repo")
```

---

### git_log — 查看提交历史

```python
# 最近 10 条提交
git_log(path="/path/to/repo", limit=10)

# 完整日志
git_log(path="/path/to/repo", limit=0)

# 指定作者
git_log(path="/path/to/repo", author="alice@example.com")
```

---

### git_branch — 分支管理

```python
# 列出所有分支
git_branch(path="/path/to/repo")

# 创建分支
git_branch(action="create", name="feature/login", path="/path/to/repo")

# 删除分支
git_branch(action="delete", name="old-feature", path="/path/to/repo")
```

---

## 4. Docker 工具

### docker_ps — 列出容器

```python
# 列出运行中的容器
docker_ps()

# 列出所有容器（包括已停止）
docker_ps(all=True)

# JSON 格式输出
docker_ps(format="json")
```

---

### docker_logs — 查看日志

```python
# 获取容器最近 100 行日志
docker_logs(container="web", lines=100)

# 实时跟踪日志
docker_logs(container="web", follow=True, lines=50)

# 显示时间戳
docker_logs(container="web", timestamps=True)
```

---

### docker_exec — 容器内执行命令

```python
# 在容器中执行命令
docker_exec(
    container="web",
    command="ls /app",
    user="appuser",       # 可选：以指定用户执行
    workdir="/app"        # 可选：工作目录
)
```

---

### docker_images — 列出镜像

```python
# 列出所有镜像
docker_images()

# JSON 格式
docker_images(format="json")

# 按名称过滤
docker_images(filter="python")
```

---

### docker_build — 构建镜像

```python
# 构建镜像
docker_build(
    tag="myapp:latest",
    path="/path/to/dockerfile",  # Dockerfile 路径
    no_cache=False
)
```

---

### docker_pull — 拉取镜像

```python
# 从 Docker Hub 拉取镜像
docker_pull(image="nginx:latest")

# 指定 registry
docker_pull(image="registry.example.com/app:latest")
```

---

## 5. HTTP 工具

### http_get — GET 请求

```python
# 基本 GET
http_get(url="https://api.example.com/data")

# 带自定义 header
http_get(
    url="https://api.example.com/data",
    headers='{"Authorization": "Bearer token123"}',
    timeout=30
)
```

---

### http_post — POST 请求

```python
# 基本 POST（JSON）
http_post(
    url="https://api.example.com/users",
    data='{"name": "Alice", "email": "alice@example.com"}',
    content_type="application/json"
)

# 表单数据
http_post(
    url="https://form.example.com/submit",
    data="name=Alice&email=alice@example.com",
    content_type="application/x-www-form-urlencoded"
)
```

---

### http_head — HEAD 请求

```python
# 获取响应头（不获取 body）
http_head(url="https://example.com/large-file.zip")
# 用于检查资源是否存在、大小等
```

---

## 6. JSON 工具

### json_parse — 解析 JSON

```python
# 解析 JSON 字符串
json_parse(text='{"name": "Alice", "age": 30}')

# 格式化输出
json_parse(text='{"name":"Alice"}', pretty=True)
```

---

### json_format — 格式化 JSON

```python
# 美化输出
json_format(text='{"a":1,"b":2}', indent=4)
```

---

### json_query — JSON 路径查询

```python
# 使用点路径查询
json_query(
    text='{"result": {"users": [{"name": "Alice"}, {"name": "Bob"}]}}',
    path="result.users[0].name"
)
# 返回："Alice"
```

---

### json_validate — 验证 JSON

```python
# 验证并返回元信息
json_validate(text='{"valid": true}')
# 返回：{"valid": true, "is_valid": true, "type": "object"}
```

---

## 7. Agent 调用工具

### 工具注册到 Agent

所有工具通过 `h_agent/core/tools.py` 的 `TOOLS` 列表注册：

```python
# 查看所有可用工具
from h_agent.core.tools import TOOLS, TOOL_HANDLERS
print(f"共 {len(TOOLS)} 个工具")
print(f"共 {len(TOOL_HANDLERS)} 个处理器")
for t in TOOLS:
    print(f"  - {t['function']['name']}")
```

---

## 注意事项

1. **工具名冲突**：扩展模块和插件工具名可能与核心工具重叠，后者优先
2. **参数校验**：LLM 传入的参数会自动校验，格式错误会返回错误信息而非崩溃
3. **超时处理**：网络类工具（HTTP、Docker）有各自超时限制
4. **危险命令**：Shell 类工具内置危险命令黑名单，但无法覆盖所有边界情况
5. **大文件**：超过 10MB 的文件操作会自动流式处理
6. **编码**：所有文件操作默认 UTF-8 编码，读取时 `errors='replace'` 处理乱码
