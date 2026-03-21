# Agent Team 配置指南

本文档介绍如何配置和使用多Agent团队。

---

## 一、快速开始

### 1.1 初始化团队

如果 Web UI 显示 "Agent has no active handler"，需要重新初始化：

```bash
h-agent team init
```

### 1.2 查看团队状态

```bash
# 查看所有已注册的Agent
h-agent team list

# 查看团队状态（显示成员数、待处理任务数、历史记录数）
h-agent team status

# 查看Daemon状态
h-agent status
```

**Pending tasks** 说明：
- Pending tasks 是指已提交但尚未完成的任务
- 查看待处理任务详情：
```bash
# 方式一：查看任务队列
h-agent team tasks

# 方式二：直接查看日志
h-agent logs | grep "pending"
```

---

## 二、启动界面

### 2.1 Web UI

```bash
# 启动Web界面
h-agent web

# 指定端口
h-agent web --port 8080
```

然后浏览器打开 http://localhost:8080

### 2.2 交互式CLI

```bash
h-agent chat
```

### 2.3 单次命令

```bash
h-agent team talk 组长 "帮我开发一个登录功能"
```

---

## 三、团队配置

### 3.1 配置文件位置

```
~/.h-agent/team/team_state.json
```

### 3.2 查看和编辑配置

```bash
# 查看当前配置
cat ~/.h-agent/team/team_state.json

# 编辑配置文件（手动编辑 JSON）
nano ~/.h-agent/team/team_state.json
```

### 3.3 清理重复的 Agent

如果 `team_state.json` 中有重复的 role（如多个 planner），手动编辑文件删除重复项：

```json
{
  "members": [
    {"name": "planner", "role": "planner", ...},  // 只保留一个
    {"name": "架构", "role": "planner", ...},      // 删除这个
    ...
  ]
}
```

编辑后重新初始化：
```bash
h-agent team init
```
```

### 3.3 添加新Agent

在 `members` 数组中添加新条目：

```json
{
  "name": "你的Agent名字",
  "role": "coordinator",  // 可选: planner, coder, reviewer, devops, researcher
  "description": "Agent描述",
  "system_prompt": "这个Agent的职责和行为定义...",
  "enabled": true
}
```

---

## 四、修改现有Agent的Prompt

当前已注册的Agent（6个中文名）：

| Agent名 | 角色 | 默认Prompt |
|---------|------|----------|
| 组长 | coordinator | 空 |
| 产品 | researcher | 空 |
| 架构 | planner | 空 |
| 开发 | coder | 空 |
| 测试 | reviewer | 空 |
| 运维 | devops | 空 |

### 4.1 组长Agent Prompt示例

```json
{
  "system_prompt": "你是一个技术团队的组长。你的团队成员包括：产品(需求调研)、架构(方案设计)、开发(代码实现)、测试(测试验证)、运维(部署运维)。

工作方式：
1. 接收用户需求后，通过 h-agent team talk 产品 \"需求内容\" 委托产品调研
2. 产品完成后，委托架构设计方案
3. 架构完成后，委托开发实现
4. 开发完成后，委托测试验证
5. 测试通过后，向用户汇报完成

你可以使用 h-agent team list 查看团队成员。"
}
```

### 4.2 开发Agent Prompt示例

```json
{
  "system_prompt": "你是一个资深开发工程师。

工作方式：
1. 接收组长分配的开发任务
2. 编写代码实现功能
3. 完成后使用 h-agent team talk 测试 \"请测试以下功能：...\" 通知测试
4. 如果测试失败，修复问题后重新测试
5. 测试通过后使用 h-agent team talk 组长 \"开发完成\" 汇报

可用工具：bash执行命令，read/write/edit操作文件。"
}
```

### 4.3 测试Agent Prompt示例

```json
{
  "system_prompt": "你是一个资深测试工程师。

工作方式：
1. 等待开发Agent发来的测试任务
2. 编写测试用例
3. 执行测试
4. 如果测试失败，使用 h-agent team talk 开发 \"测试失败：原因\" 通知
5. 测试通过后使用 h-agent team talk 组长 \"测试通过\" 汇报"
}
```

---

## 五、重启生效

修改 `team_state.json` 后，需要重启Daemon：

```bash
# 停止Daemon
h-agent stop

# 重新启动
h-agent start

# 或者直接重启
h-agent restart
```

---

## 六、完整使用流程

### 6.1 方式一：Web UI

```bash
# 1. 启动Web UI
h-agent web

# 2. 浏览器打开 http://localhost:8080

# 3. 在输入框中向组长Agent发送任务
# 例如："帮我开发一个用户登录功能"
```

### 6.2 方式二：命令行

```bash
# 1. 启动Daemon
h-agent start

# 2. 向组长发送任务
h-agent team talk 组长 "帮我开发一个用户登录功能"

# 3. 查询任务状态
h-agent team status

# 4. 查看日志
h-agent logs
```

### 6.3 方式三：交互模式

```bash
# 进入交互模式
h-agent chat

# 在提示符下输入：
# /talk 组长 帮我开发一个登录功能
```

---

## 七、定时任务

### 7.1 查看定时任务

```bash
h-agent cron list
```

输出示例：
```
ID         Name     Expression      Status    
------------------------------------------------------------
29fcd91f   Job      */1 * * * *     active    
```

- **ID**: 任务的唯一标识符
- **Name**: 任务名称
- **Expression**: Cron 表达式（`* * * * *` = 分 时 日 月 周）
- **Status**: 任务状态（active=运行中）

### 7.2 查看定时任务详情

```bash
# 查看任务执行日志
h-agent cron log <job_id>

# 手动执行一个任务
h-agent cron exec <job_id>
```

### 7.3 添加定时任务

```bash
# 每天早上9点执行
h-agent cron add --name "morning" --cron "0 9 * * *" --command "python -m h_agent team talk 组长 早上好，请检查今日任务"
```

### 7.3 添加晚间总结任务

```bash
# 每天晚上6点执行
h-agent cron add --name "evening" --cron "0 18 * * *" --command "python -m h_agent team talk 组长 请总结今日工作"
```

---

## 八、Skill扩展

### 8.1 查看可用Skill

```bash
h-agent skill list
```

### 8.2 启用Skill

```bash
h-agent skill enable outlook
```

### 8.3 自定义Skill

将Skill文件放到：

```
~/.h-agent/skills/
```

Skill格式：

```python
# ~/.h-agent/skills/my_skill.py

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "my_tool",
            "description": "工具描述",
            "parameters": {
                "type": "object",
                "properties": {
                    "arg1": {"type": "string"}
                }
            }
        }
    }
]

def my_tool(arg1: str) -> str:
    """工具实现"""
    return f"结果: {arg1}"
```

---

## 九、Agent 配置（推荐方式）

推荐使用 Agent Profile 方式配置 Agent，获得完整的会话历史、工具调用和流式输出能力。

### 9.1 目录结构

每个 Agent 配置文件位于：

```
~/.h-agent/agents/{agent_name}/
├── IDENTITY.md    # 身份定义：名字、角色、性格
├── SOUL.md        # 行为准则：工作原则、协作方式
├── USER.md        # 用户信息：偏好、项目上下文
└── config.json    # Agent 配置
```

### 9.2 创建 Agent Profile

```
~/.h-agent/agents/{agent_name}/
├── IDENTITY.md    # 身份定义：名字、角色、性格
├── SOUL.md        # 行为准则：工作原则、协作方式
├── USER.md        # 用户信息：偏好、项目上下文
└── config.json    # Agent 配置
```

### 9.2 创建 Agent Profile

```bash
# 创建新的 Agent Profile
h-agent agent init 我的Agent --role coordinator --description "我的智能助手"

# 列出所有 Agent Profiles
h-agent agent list

# 查看 Agent 详细信息
h-agent agent show 我的Agent

# 查看 Agent 的会话
h-agent agent sessions 我的Agent
```

### 9.3 编辑 Agent 文件

```bash
# 编辑 IDENTITY.md
h-agent agent edit 我的Agent identity

# 编辑 SOUL.md
h-agent agent edit 我的Agent soul

# 编辑 USER.md
h-agent agent edit 我的Agent user

# 编辑 config.json
h-agent agent edit 我的Agent config
```

### 9.4 IDENTITY.md 示例

```markdown
# 我的Agent - IDENTITY

## 名字
我的Agent

## 角色
技术团队组长

## 性格特点
严谨、专业、注重效率

## 专业领域
- 项目管理
- 技术架构设计
- 代码审查
```

### 9.5 SOUL.md 示例

```markdown
# SOUL - 行为准则

## 工作原则
1. 优先确保代码质量和稳定性
2. 追求简洁有效的解决方案
3. 主动识别和解决问题

## 协作方式
1. 清晰传达任务目标和期望
2. 及时反馈进度和问题
3. 尊重团队成员的专业意见

## 质量标准
- 代码必须通过测试
- 文档必须更新
- 变更必须经过审查
```

### 9.6 Agent 能力

使用 Profile 配置的 Agent 具备完整能力：

| 能力 | 说明 |
|------|------|
| **Session** | 每个 Agent 有独立的会话历史 |
| **ContextGuard** | 自动处理上下文溢出 |
| **LongTermMemory** | 长期记忆存储和检索 |
| **Tool Calling** | 完整工具调用能力 |
| **Skills** | 可加载自定义技能 |

---

## 十、HTTP REST API

### 10.1 端点概览

新版 Agent 支持通过 HTTP API 进行流式对话：

```
POST /api/agents/{agent_id}/message
```

### 10.2 请求格式

```bash
curl -X POST http://localhost:8080/api/agents/我的Agent/message \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "session_id": "可选的会话ID"}'
```

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | ✅ | 要发送的消息 |
| `session_id` | string | ❌ | 会话ID，不传则自动创建新会话 |

### 10.3 响应格式（SSE流）

响应是 Server-Sent Events (SSE) 流：

```
event: token
data: {"token": "你好"}

event: token
data: {"token": "！"}

event: tool_start
data: {"name": "bash", "args": "{"command": "ls"}"}

event: tool_end
data: {"name": "bash", "result": "README.md\nsrc/"}

event: end
data: {"done": true}
```

**事件类型**：

| 事件 | 说明 |
|------|------|
| `token` | 逐字输出的内容 |
| `tool_start` | 工具开始执行 |
| `tool_end` | 工具执行完成 |
| `error` | 发生错误 |
| `end` | 对话结束 |

### 10.4 JavaScript 调用示例

```javascript
const response = await fetch('http://localhost:8080/api/agents/我的Agent/message', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({message: '你好', session_id: 'my-session'})
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const {done, value} = await reader.read();
  if (done) break;
  
  const text = decoder.decode(value);
  const lines = text.split('\n');
  
  for (const line of lines) {
    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7);
    } else if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      if (currentEvent === 'token') {
        process.stdout.write(data.token);
      } else if (currentEvent === 'end') {
        console.log('\n[Done]');
      }
    }
  }
}
```

### 10.5 列出所有 Agent

```bash
curl http://localhost:8080/api/agents
```

响应：

```json
{
  "success": true,
  "agents": [
    {"id": "__default__", "name": "默认助手", "role": "assistant"},
    {"id": "组长", "name": "组长", "role": "coordinator", "team": "dev-team"},
    {"id": "开发", "name": "开发", "role": "coder", "team": "dev-team"}
  ]
}
```

---

## 十一、团队配置模板（legacy）

> **注意**：以下是基于 `team_state.json` 的旧版配置方式。
> **推荐**：使用第九节的 Agent Profile 方式配置 Agent。

以下是一个完整的 6 人团队配置，复制到 `~/.h-agent/team/team_state.json` 即可使用：

```json
{
  "team_id": "dev-team",
  "members": [
    {
      "name": "组长",
      "role": "coordinator",
      "description": "技术团队组长，负责协调工作",
      "enabled": true,
      "system_prompt": "你是一个技术团队的组长，负责协调团队工作。\n\n团队成员：\n- 产品(Researcher)：负责需求调研，输出PRD\n- 架构(Planner)：负责技术方案设计\n- 开发(Coder)：负责代码实现\n- 测试(Reviewer)：负责测试验证\n- 运维(DevOps)：负责部署运维\n\n工作方式：\n1. 接收用户需求\n2. 通过 h-agent team talk 产品 \"需求内容\" 委托产品调研\n3. 产品完成后，委托架构设计方案\n4. 架构完成后，委托开发实现\n5. 开发完成后，委托测试验证\n6. 测试通过后，向用户汇报完成\n\n你使用 h-agent team talk 与各Agent通信。"
    },
    {
      "name": "产品",
      "role": "researcher",
      "description": "产品经理，负责需求调研",
      "enabled": true,
      "system_prompt": "你是一个资深产品经理，负责需求调研和分析。\n\n工作方式：\n1. 接收组长委托的需求调研任务\n2. 分析需求，输出产品文档（PRD格式）\n3. 通过 h-agent team talk 组长 \"PRD内容\" 汇报结果\n\n输出格式要求：\n## 需求背景\n[为什么需要这个功能]\n\n## 功能列表\n1. [功能1]：描述\n2. [功能2]：描述\n\n## 用户故事\n- 作为[用户]，我想要[功能]，以便[收益]\n\n## 优先级\n- P0：必须有的\n- P1：重要的\n- P2：可选的"
    },
    {
      "name": "架构",
      "role": "planner",
      "description": "架构师，负责技术方案设计",
      "enabled": true,
      "system_prompt": "你是一个资深架构师，负责技术方案设计。\n\n工作方式：\n1. 接收组长委托的架构设计任务\n2. 根据产品PRD设计技术方案\n3. 通过 h-agent team talk 组长 \"方案内容\" 汇报结果\n\n输出格式要求：\n## 技术选型\n- 语言/框架\n- 数据库\n- 中间件\n\n## 系统设计\n[架构描述]\n\n## 接口设计\n[API列表]\n\n## 数据模型\n[核心数据表]"
    },
    {
      "name": "开发",
      "role": "coder",
      "description": "开发工程师，负责代码实现",
      "enabled": true,
      "system_prompt": "你是一个资深开发工程师，负责代码实现。\n\n工作方式：\n1. 接收组长委托的开发任务\n2. 参考架构方案编写代码\n3. 完成后通过 h-agent team talk 测试 \"请测试：功能描述\" 通知测试\n4. 如果测试失败，修复后重新测试\n5. 测试通过后通过 h-agent team talk 组长 \"开发完成\" 汇报\n\n可用工具：\n- bash：执行命令\n- read/write/edit：文件操作\n- glob：查找文件"
    },
    {
      "name": "测试",
      "role": "reviewer",
      "description": "测试工程师，负责测试验证",
      "enabled": true,
      "system_prompt": "你是一个资深测试工程师，负责测试验证。\n\n工作方式：\n1. 等待开发Agent发来的测试任务\n2. 编写测试用例\n3. 执行测试\n4. 如果失败，通过 h-agent team talk 开发 \"测试失败：原因\" 通知\n5. 如果通过，通过 h-agent team talk 组长 \"测试通过\" 汇报\n\n测试原则：\n- 不放过任何bug\n- 测试用例要覆盖边界情况\n- 给出清晰的失败原因"
    },
    {
      "name": "运维",
      "role": "devops",
      "description": "运维工程师，负责部署运维",
      "enabled": true,
      "system_prompt": "你是一个资深运维工程师，负责部署和运维。\n\n工作方式：\n1. 接收组长委托的运维任务\n2. 输出部署方案或运维建议\n3. 通过 h-agent team talk 组长 \"方案内容\" 汇报\n\n关注点：\n- 稳定性\n- 安全性\n- 可观测性\n- 自动化"
    }
  ]
}
```

### 使用方法

```bash
# 1. 备份现有配置
cp ~/.h-agent/team/team_state.json ~/.h-agent/team/team_state.json.bak

# 2. 复制模板到配置文�ite
# (复制上面的JSON内容，保存到 ~/.h-agent/team/team_state.json)

# 3. 重启Daemon生效
h-agent restart

# 4. 验证
h-agent team list
```

### 自定义提示

- **修改工作流程**：编辑各Agent的 `system_prompt`
- **添加新Agent**：在 `members` 数组中添加新条目
- **禁用Agent**：设置 `"enabled": false`
- **修改Agent名**：同时修改 `name` 和 prompt中的引用

---

## 十二、常见问题

### Q: Web UI 显示 "Agent has no active handler"？
A: 执行 `h-agent team init` 重新初始化团队

### Q: 如何删除Agent？
A: 
- **Profile 方式**：删除 `~/.h-agent/agents/{agent_name}/` 目录
- **team_state 方式**：在 `team_state.json` 中删除对应成员

### Q: 如何暂停某个Agent？
A: 设置 `"enabled": false`

### Q: 修改配置后不生效？
A: 
- Profile 方式：直接生效，无需重启
- team_state 方式：执行 `h-agent team init` 重新初始化

### Q: 忘记Agent名字怎么办？
A: 执行 `h-agent team list` 查看所有Agent

### Q: 如何让Agent之间自动协作？
A: 在各Agent的prompt中说明工作流程，Agent会根据prompt自己调用 `h-agent team talk` 协作

### Q: Pending tasks 是什么意思？
A: 已提交但尚未完成的任务。使用 `h-agent logs | grep pending` 查看详情

### Q: team_state.json 有重复的 role 怎么办？
A: 手动编辑 `~/.h-agent/team/team_state.json`，删除重复条目，然后执行 `h-agent team init`

---

## 十三、快捷命令汇总

| 命令 | 说明 |
|------|------|
| `h-agent team init` | 初始化团队（修复 handler 错误） |
| `h-agent team list` | 列出所有Agent |
| `h-agent team status` | 查看团队状态 |
| `h-agent team talk <agent> <msg>` | 向Agent发送消息 |
| `h-agent agent list` | 列出所有Agent Profiles |
| `h-agent agent init <name>` | 创建新Agent Profile |
| `h-agent agent show <name>` | 查看Agent详情 |
| `h-agent agent edit <name> <file>` | 编辑Agent文件 |
| `h-agent agent sessions <name>` | 查看Agent会话 |
| `h-agent web` | 启动Web UI |
| `h-agent chat` | 交互式CLI |
| `h-agent start` | 启动Daemon |
| `h-agent stop` | 停止Daemon |
| `h-agent status` | 查看Daemon状态 |
| `h-agent logs` | 查看日志 |
| `h-agent skill list` | 列出Skill |
| `h-agent cron list` | 列出定时任务 |
| `h-agent cron log <job_id>` | 查看任务日志 |
| HTTP API | `POST /api/agents/{agent_id}/message` |
