# h-agent 快速开始

*"该去大闹一场喽。"* — 艾克

h-agent 是一个模块化的 AI 编程智能体框架，支持会话管理、工具调用、RAG、子智能体、多渠道接入。

---

## 🚀 30 秒上手

### 1. 安装

```bash
pip install h-agent
```

### 2. 配置（首次）

```bash
h-agent init
```

按提示输入 API Key，选择模型，搞定！

### 3. 开始对话

```bash
h-agent chat
```

输入你的问题，按回车发送。输入 `q` 退出。

---

## 📋 常用命令速查

| 命令 | 说明 |
|------|------|
| `h-agent init` | 首次配置向导 |
| `h-agent chat` | 交互式对话 |
| `h-agent run "..."` | 执行单次命令 |
| `h-agent start` | 启动守护进程（后台运行） |
| `h-agent stop` | 停止守护进程 |
| `h-agent status` | 查看守护进程状态 |
| `h-agent logs` | 查看守护进程日志 |
| `h-agent session list` | 查看会话列表 |
| `h-agent config --show` | 显示当前配置 |
| `h-agent plugin list` | 查看已安装插件 |
| `h-agent skill list` | 查看可用技能 |
| `h-agent rag index` | 索引代码库（启用 RAG） |
| `h-agent memory list` | 查看长期记忆 |

---

## 💬 对话模式技巧

### 切换会话

```
>> /clear          # 清空当前对话历史
>> /history        # 查看消息数量
>> q              # 退出
```

### 使用命名会话

```bash
# 创建一个叫 "review" 的会话
h-agent session create --name review

# 在 review 会话中对话
h-agent chat --session review
```

---

## 🔧 配置多模型

### DeepSeek

```bash
h-agent config --base-url https://api.deepseek.com/v1
h-agent config --model deepseek-chat
```

### 本地模型 (Ollama)

```bash
h-agent config --base-url http://localhost:11434/v1
h-agent config --model llama3
```

### Azure OpenAI

```bash
h-agent config --base-url https://<your-resource>.openai.azure.com/v1
h-agent config --model gpt-4o
```

---

## 🛠️ 工具自动调用

h-agent 会根据任务自动调用工具。例如你说：

> *"帮我读取 config.json 然后修改其中的 debug 选项"*

Agent 会：
1. 调用 `read` 读取文件
2. 调用 `edit` 修改内容
3. 返回完成结果

**可用工具类别**：

| 类别 | 工具示例 |
|------|----------|
| Shell | `bash`, `shell_run`, `shell_cd` |
| 文件 | `read`, `write`, `edit`, `glob`, `file_exists` |
| Git | `git_status`, `git_commit`, `git_push`, `git_log` |
| Docker | `docker_ps`, `docker_logs`, `docker_exec` |
| HTTP | `http_get`, `http_post` |
| JSON | `json_parse`, `json_query`, `json_format` |

---

## 🔌 守护进程模式

守护进程在后台运行，保持会话上下文，适合频繁使用的场景。

```bash
# 启动（后台运行）
h-agent start

# 查看状态
h-agent status

# 查看日志
h-agent logs --tail 50

# 停止
h-agent stop
```

启动后，所有命令都会复用同一个 Agent 实例，节省 API 调用。

---

## 📁 会话管理

```bash
# 列出所有会话
h-agent session list

# 创建会话
h-agent session create --name mytask

# 在指定会话中运行
h-agent run --session mytask "帮我写一个快速排序"

# 搜索会话
h-agent session search "登录功能"

# 会话标签
h-agent session tag add mytask bug
h-agent session list --tag bug
```

---

## 🔍 代码库 RAG

先索引代码库，之后 Agent 可以理解整个代码库：

```bash
# 索引当前目录
h-agent rag index

# 索引指定目录
h-agent rag index --directory ./src

# 语义搜索
h-agent rag search "用户认证逻辑"

# 查看索引状态
h-agent rag stats
```

---

## 🧠 长期记忆

h-agent 可以记住重要信息：

```bash
# 添加记忆
h-agent memory add decision "db-choice" "PostgreSQL" --reason "需要事务支持"
h-agent memory add fact "python-version" "3.11"

# 搜索记忆
h-agent memory search "数据库"

# 导出记忆
h-agent memory dump
```

---

## 🧩 技能 (Skills)

按需加载的扩展能力：

```bash
# 列出可用技能
h-agent skill list

# 查看技能详情
h-agent skill info github

# 启用/禁用
h-agent skill enable tavily
h-agent skill disable weather

# 安装新技能（pip）
h-agent skill install tavily

# 运行技能函数
h-agent skill run github issues owner/repo --limit 5
```

---

## 🔧 插件系统

扩展 h-agent 能力：

```bash
# 列出插件
h-agent plugin list

# 安装插件
h-agent plugin install https://github.com/user/h-agent-plugin

# 启用/禁用
h-agent plugin enable my-plugin
h-agent plugin disable my-plugin
```

---

## 📋 场景示例

### 场景 1：帮我写代码

```bash
$ h-agent run "用 Python 写一个快速排序"

def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)

print(quicksort([3, 6, 8, 10, 1, 2, 1]))
# 输出: [1, 1, 2, 3, 6, 8, 10]
```

### 场景 2：代码审查

```bash
$ h-agent chat
>> 帮我 review 一下 src/auth.py，重点关注安全性
```

### 场景 3：Git 操作

```
帮我看看当前 git 状态，然后提交所有更改，提交信息写 "feat: 添加用户认证"
```

### 场景 4：Docker 操作

```
帮我查看运行中的 docker 容器，然后查看 web 容器最近的日志
```

### 场景 5：多会话对比

```bash
# 创建两个会话分别做不同的分析
h-agent session create --name analysis-a
h-agent session create --name analysis-b

# 在两个会话中分别运行不同任务
h-agent run --session analysis-a "分析前端代码的架构"
h-agent run --session analysis-b "分析后端代码的架构"
```

---

## 📚 更多文档

| 文档 | 说明 |
|------|------|
| [README.md](README.md) | 完整功能和配置参考 |
| [docs/guides/core.md](docs/guides/core.md) | 核心模块（agent_loop、config、tools） |
| [docs/guides/features.md](docs/guides/features.md) | 功能模块（sessions、channels、rag、skills、subagents） |
| [docs/guides/daemon.md](docs/guides/daemon.md) | 后台服务（守护进程、自动恢复、日志） |
| [docs/guides/tools.md](docs/guides/tools.md) | 36 个内置工具详解 |
| [docs/guides/plugins.md](docs/guides/plugins.md) | 插件系统（安装、开发、管理） |
| [docs/guides/planner.md](docs/guides/planner.md) | 任务规划（分解、调度、进度跟踪） |
| [docs/guides/skills-office.md](docs/guides/skills-office.md) | Windows Office/Outlook 自动化 |
| [docs/guides/cli-reference.md](docs/guides/cli-reference.md) | CLI 完整命令参考 |
| [docs/guides/installation.md](docs/guides/installation.md) | 安装部署（Windows/内网/离线） |

---

*"不要放弃，直到做对为止。"*
