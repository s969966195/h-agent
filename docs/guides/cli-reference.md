# CLI 完整命令参考

*"我宁愿犯错，也不愿什么都不做。"* — 艾克

h-agent CLI 所有命令的完整参考。

---

## 全局命令

### h-agent --version

显示版本号并退出。

```bash
h-agent --version
# 输出: h-agent 1.2.3
```

### h-agent init

首次配置向导。

```bash
h-agent init                    # 完整交互式配置向导
h-agent init --quick           # 快速配置（最小化提示）
```

### h-agent (无参数)

默认启动交互式聊天模式，等价于 `h-agent chat`。

```bash
h-agent
# 等价于:
h-agent chat
```

---

## 守护进程

### h-agent start

启动后台守护进程。

```bash
h-agent start
```

**输出示例**：
```
Daemon started (PID: 12345, Port: 19527)
```

### h-agent stop

停止守护进程。

```bash
h-agent stop
```

### h-agent status

查看守护进程运行状态。

```bash
h-agent status
```

**输出示例**：
```
Daemon running (PID: 12345, Port: 19527)
  Current session: sess-abc123
  Total sessions: 3
```

### h-agent logs

查看守护进程日志。

```bash
h-agent logs                          # 查看全部日志
h-agent logs --tail 50               # 最后 50 行
h-agent logs --lines 100             # 最后 100 行
```

### h-agent autostart install

安装开机自启动。

```bash
h-agent autostart install            # 安装（自动检测平台）
h-agent autostart uninstall         # 卸载
h-agent autostart status            # 查看状态
```

---

## 对话和运行

### h-agent chat

交互式聊天模式。

```bash
h-agent chat                          # 使用默认会话
h-agent chat --session my-session    # 使用指定会话
```

**聊天内命令**：
- `/clear` — 清空当前对话历史
- `/history` — 查看消息数量
- `q` / `exit` / 空行 — 退出

### h-agent run

单次命令模式，执行完退出。

```bash
h-agent run "帮我写一个快速排序"
h-agent run --session my "解释这段代码的含义"
h-agent run "查看 git 状态并提交"
```

---

## 会话管理

### h-agent session list

列出所有会话。

```bash
h-agent session list                     # 列出所有
h-agent session list --tag bug          # 按标签过滤
h-agent session list --group frontend   # 按分组过滤
```

### h-agent session create

创建新会话。

```bash
h-agent session create                  # 创建未命名会话
h-agent session create --name my-task  # 创建命名会话
h-agent session create --name review --group code  # 带分组
```

### h-agent session history

查看会话历史。

```bash
h-agent session history <session_id>    # 按 ID
h-agent session history my-task         # 按名称（自动匹配）
```

### h-agent session delete

删除会话。

```bash
h-agent session delete <session_id>
h-agent session delete old-session
```

### h-agent session search

搜索会话内容。

```bash
h-agent session search "登录功能"
h-agent session search "git commit" --days 30  # 近 30 天
```

### h-agent session rename

重命名会话。

```bash
h-agent session rename <session_id> new-name
```

### h-agent session tag

会话标签管理。

```bash
h-agent session tag list                        # 列出所有标签
h-agent session tag add <session_id> bug        # 添加标签
h-agent session tag remove <session_id> bug     # 删除标签
h-agent session tag get <session_id>            # 查看会话标签
```

### h-agent session group

会话分组管理。

```bash
h-agent session group list                      # 列出所有分组
h-agent session group set <session_id> frontend # 设置分组
h-agent session group set <session_id> ""      # 清除分组
h-agent session group sessions frontend         # 查看分组下的会话
```

---

## RAG（代码库搜索）

### h-agent rag index

索引代码库。

```bash
h-agent rag index                          # 索引当前目录
h-agent rag index --directory ./src       # 索引指定目录
```

### h-agent rag search

搜索代码库。

```bash
h-agent rag search "用户认证"              # 语义搜索
h-agent rag search "邮件发送" --limit 10  # 限制结果数
```

### h-agent rag stats

查看索引统计。

```bash
h-agent rag stats
h-agent rag stats --directory ./src
```

---

## 配置管理

### h-agent config --show

显示当前配置。

```bash
h-agent config --show
```

### h-agent config --api-key

设置 API Key。

```bash
h-agent config --api-key sk-xxxx        # 直接设置
h-agent config --api-key __prompt__     # 交互式安全输入
h-agent config --clear-key              # 清除 API Key
```

### h-agent config --base-url

设置 API Base URL。

```bash
h-agent config --base-url https://api.deepseek.com/v1
h-agent config --base-url http://localhost:11434/v1  # Ollama
```

### h-agent config --model

设置模型。

```bash
h-agent config --model gpt-4o
h-agent config --model deepseek-chat
```

### h-agent config --profile

Profile 管理。

```bash
h-agent config --list-all                  # 列出所有 Profile
h-agent config --profile work              # 切换到 work Profile
h-agent config --profile-create new-profile # 创建新 Profile
h-agent config --profile-delete old-profile # 删除 Profile
```

### h-agent config --wizard

交互式配置向导。

```bash
h-agent config --wizard
```

### h-agent config --export / --import

配置导入导出。

```bash
h-agent config --export            # 导出到 JSON
h-agent config --import config.json  # 从 JSON 导入
```

---

## 插件管理

### h-agent plugin list

列出所有插件。

```bash
h-agent plugin list
```

### h-agent plugin info

查看插件详情。

```bash
h-agent plugin info <plugin_name>
```

### h-agent plugin enable

启用插件。

```bash
h-agent plugin enable <plugin_name>
```

### h-agent plugin disable

禁用插件。

```bash
h-agent plugin disable <plugin_name>
```

### h-agent plugin install

安装插件（从 URL）。

```bash
h-agent plugin install https://github.com/user/h-agent-myplugin
```

### h-agent plugin uninstall

卸载插件。

```bash
h-agent plugin uninstall <plugin_name>
```

---

## 技能管理

### h-agent skill list

列出所有技能。

```bash
h-agent skill list              # 仅可用技能
h-agent skill list --all        # 包含禁用技能
```

### h-agent skill info

查看技能详情。

```bash
h-agent skill info coding-agent
```

### h-agent skill enable

启用技能。

```bash
h-agent skill enable github
```

### h-agent skill disable

禁用技能。

```bash
h-agent skill disable weather
```

### h-agent skill install

安装技能（通过 pip）。

```bash
h-agent skill install tavily
h-agent skill install myskill --package h_agent_skill_myskill
```

### h-agent skill uninstall

卸载技能。

```bash
h-agent skill uninstall old-skill
```

### h-agent skill run

运行技能函数。

```bash
h-agent skill run github issues owner/repo --limit 5
h-agent skill run weather "Beijing"
```

---

## 长期记忆

### h-agent memory list

列出记忆。

```bash
h-agent memory list                        # 全部
h-agent memory list --type decision        # 按类型过滤
```

### h-agent memory add

添加记忆。

```bash
h-agent memory add fact "python-version" "3.11"
h-agent memory add decision "db-choice" "PostgreSQL" --reason "需要事务支持"
h-agent memory add user "boss-name" "张三" --tags personal,work
```

**类型选项**：`user` | `project` | `decision` | `fact` | `error`

### h-agent memory get

获取记忆。

```bash
h-agent memory get fact python-version
```

### h-agent memory delete

删除记忆。

```bash
h-agent memory delete decision db-choice
```

### h-agent memory search

搜索记忆。

```bash
h-agent memory search "Python"                  # 搜索关键词
h-agent memory search "部署" --days 30         # 近 30 天
h-agent memory search "" --sessions            # 也搜索会话历史
```

### h-agent memory dump

导出记忆为文本。

```bash
h-agent memory dump                  # 全部
h-agent memory dump --type decision # 按类型
```

---

## Agent 团队

### h-agent team

团队管理。

```bash
h-agent team list          # 列出团队成员
h-agent team status       # 查看团队状态
h-agent team init         # 初始化团队工作空间
```

---

## 模型管理

### h-agent model list

列出可用模型。

```bash
h-agent model list
```

### h-agent model switch

切换模型。

```bash
h-agent model switch gpt-4o-mini
```

### h-agent model info

查看模型信息。

```bash
h-agent model info gpt-4o
```

### h-agent model add

添加自定义模型。

```bash
h-agent model add
# 交互式添加（名称、Base URL 等）
```

---

## 模板管理

### h-agent template list

列出所有模板。

```bash
h-agent template list
```

### h-agent template show

查看模板详情。

```bash
h-agent template show code-review
```

### h-agent template apply

应用模板。

```bash
h-agent template apply code-review
```

### h-agent template create

创建新模板。

```bash
h-agent template create my-template
```

### h-agent template delete

删除模板。

```bash
h-agent template delete old-template
```

---

## Web UI

### h-agent web

启动 Web UI 服务器。

```bash
h-agent web                           # 默认 8080 端口
h-agent web --port 9000              # 指定端口
h-agent web --no-browser             # 不自动打开浏览器
```

---

## 命令速查表

| 命令 | 说明 |
|------|------|
| `h-agent init` | 首次配置 |
| `h-agent chat` | 交互式聊天 |
| `h-agent run "..."` | 单次命令 |
| `h-agent start/stop/status/logs` | 守护进程管理 |
| `h-agent session list/create/history/delete/search/rename/tag/group` | 会话管理 |
| `h-agent rag index/search/stats` | 代码库搜索 |
| `h-agent config --show` | 查看配置 |
| `h-agent plugin list/info/enable/disable/install/uninstall` | 插件管理 |
| `h-agent skill list/info/enable/disable/install/uninstall/run` | 技能管理 |
| `h-agent memory list/add/get/delete/search/dump` | 长期记忆 |
| `h-agent team list/status/init` | 团队管理 |
| `h-agent model list/switch/info/add` | 模型管理 |
| `h-agent template list/show/apply/create/delete` | 模板管理 |
| `h-agent web [--port]` | Web UI |
| `h-agent --version` | 版本信息 |

---

## 注意事项

- **会话名称匹配**：所有接受 `session_id` 的命令都支持名称自动匹配
- **Tab 补全**：支持 bash/zsh Tab 补全（首次运行 `h-agent init` 后自动配置）
- **进度条**：大文件操作和索引任务会自动显示进度条
- **Ctrl+C**：大部分命令支持 `Ctrl+C` 中断，不会产生僵尸进程
- **退出码**：成功返回 `0`，失败返回 `1`
