## 产品设计

### 命令清单

#### 核心服务命令
- `h-agent start` - 启动后台服务
  - `--port PORT` - 指定服务端口（默认：8080）
  - `--host HOST` - 指定绑定地址（默认：127.0.0.1）
  - `--daemon` - 以守护进程模式运行（可选）
- `h-agent status` - 查看服务状态
  - 显示是否运行、PID、端口、启动时间等信息
- `h-agent stop` - 停止后台服务
  - 安全关闭所有会话并保存状态

#### Session 管理命令
- `h-agent session list` - 列出所有 session
  - `--agent AGENT_ID` - 指定 agent（默认：default）
  - `--limit N` - 限制返回数量（默认：10）
- `h-agent session create --name "project-x"` - 创建新 session
  - `--agent AGENT_ID` - 指定 agent（默认：default）
  - 返回创建的 session ID
- `h-agent session history project-x` - 查看 session 历史
  - `--limit N` - 限制消息数量（默认：50）
  - `--format FORMAT` - 输出格式（jsonl, json, text）
- `h-agent session delete project-x` - 删除指定 session
  - `--force` - 强制删除（不确认）

#### 对话命令
- `h-agent chat --session project-x "帮我分析代码"` - 在指定 session 中对话
  - `--stream` - 流式输出响应
  - `--timeout SECONDS` - 设置超时时间
- `h-agent run --session project-x "继续完成任务"` - 发送单次消息到指定 session
  - 非交互式，适合脚本调用
  - `--output FILE` - 将响应保存到文件

#### 配置命令（现有基础上扩展）
- `h-agent config --show` - 显示配置
- `h-agent config --api-key KEY` - 设置 API key
- `h-agent config --base-url URL` - 设置 API 基础 URL
- `h-agent config --model MODEL` - 设置模型

### 架构设计

#### 后台服务架构

**分层架构：**

1. **CLI 层** (`h_agent.cli.commands`)
   - 解析命令行参数
   - 路由到对应的服务端点或本地操作
   - 支持两种模式：
     - **本地模式**：直接调用核心功能（无后台服务时）
     - **客户端模式**：通过 HTTP API 调用后台服务

2. **HTTP API 层** (`h_agent.api.server`)
   - FastAPI/Flask 服务器
   - RESTful API 端点
   - WebSocket 支持流式响应
   - 进程管理（启动/停止/状态）

3. **核心服务层** (`h_agent.core.service`)
   - Agent 实例管理
   - Session 生命周期管理
   - 请求队列和并发控制
   - 资源清理和监控

4. **持久化层** (`h_agent.features.sessions`)
   - 基于现有的 SessionStore 扩展
   - 支持多 agent 多 session
   - JSONL 文件存储格式保持不变

**进程模型：**
- 主进程：HTTP 服务器 + Agent 管理器
- 工作进程：每个活跃 session 可能有自己的上下文
- 守护进程：定期清理过期资源

**通信协议：**
- HTTP/REST for commands
- WebSocket for streaming responses
- Unix socket as alternative for local communication

**关键组件：**

```python
# h_agent.api.server
class AgentAPIServer:
    def __init__(self):
        self.agent_manager = AgentManager()
        self.session_store = SessionStore()
    
    def start(self, host="127.0.0.1", port=8080):
        # 启动 HTTP 服务器
    
    def stop(self):
        # 停止服务器并保存状态

# h_agent.core.service
class AgentManager:
    def __init__(self):
        self.agents = {}  # agent_id -> AgentInstance
    
    def get_or_create_agent(self, agent_id: str) -> AgentInstance:
        if agent_id not in self.agents:
            self.agents[agent_id] = AgentInstance(agent_id)
        return self.agents[agent_id]
    
    def cleanup_inactive_agents(self):
        # 清理长时间不活跃的 agent

class AgentInstance:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.session_store = SessionStore(agent_id)
        self.context_guard = ContextGuard()
```

### 数据存储

#### Session 持久化方案

**存储位置：**
- 默认：`~/.h-agent/sessions/`（全局）或项目目录下的 `.agent_workspace/sessions/`
- 可配置：通过环境变量或配置文件指定

**文件结构：**
```
sessions/
├── default/
│   ├── index.json          # 会话索引
│   ├── sess-abc123.jsonl   # 会话数据
│   └── sess-def456.jsonl
├── project-x/
│   ├── index.json
│   └── sess-xyz789.jsonl
└── ...
```

**SessionStore 增强：**
1. **线程安全**：添加文件锁机制防止并发写入冲突
2. **自动清理**：支持 TTL（Time To Live）自动删除过期会话
3. **压缩优化**：大文件自动压缩（gzip）节省空间
4. **备份机制**：重要会话自动备份

**数据格式：**
- **index.json**：会话元数据索引
  ```json
  {
    "sess-abc123": {
      "session_id": "sess-abc123",
      "agent_id": "default",
      "created_at": "2026-03-20T14:00:00",
      "updated_at": "2026-03-20T14:30:00",
      "message_count": 25,
      "token_count": 15000,
      "name": "project-x"
    }
  }
  ```
- **sess-*.jsonl**：每行一个消息对象，保持现有格式兼容性

**性能优化：**
- 内存缓存：活跃会话的消息历史缓存在内存中
- 延迟加载：非活跃会话按需从磁盘加载
- 批量写入：减少频繁的小文件写入

### 任务拆分

#### 可分配给艾克的任务

**第一阶段：基础架构（高优先级）**
1. **实现 HTTP API 服务器**
   - 创建 `h_agent/api/server.py`
   - 实现基本的启动/停止/状态端点
   - 集成现有的 SessionStore
   
2. **扩展 CLI 命令解析**
   - 修改 `h_agent/cli/commands.py`
   - 添加新的子命令：start, stop, status, session, chat, run
   - 实现客户端模式（检测后台服务是否存在）

3. **Agent 管理器核心**
   - 创建 `h_agent/core/service.py`
   - 实现 AgentManager 和 AgentInstance 类
   - 支持多 agent 隔离

**第二阶段：Session 功能增强（中优先级）**
4. **SessionStore 线程安全改造**
   - 添加文件锁机制
   - 实现并发安全的读写操作
   
5. **会话命名和管理**
   - 扩展 SessionStore 支持自定义会话名称
   - 实现 session create/delete/list/history 命令

6. **数据持久化优化**
   - 添加自动清理和 TTL 支持
   - 实现压缩和备份机制

**第三阶段：高级功能（低优先级）**
7. **WebSocket 流式响应**
   - 实现流式对话 API
   - CLI 支持 --stream 参数
   
8. **配置管理扩展**
   - 支持服务级别的配置（端口、主机等）
   - 实现配置热重载

9. **监控和日志**
   - 添加详细的日志记录
   - 实现基本的监控指标

**技术栈建议：**
- Web 框架：FastAPI（异步支持好，类型提示完善）
- 进程管理：使用标准库 multiprocessing 或第三方如 uvicorn
- 文件锁：fcntl（Unix）或 portalocker（跨平台）
- 配置：继续使用现有的配置系统，扩展支持服务配置

**验收标准：**
- 所有期望的使用方式命令都能正常工作
- 后台服务稳定运行，资源占用合理
- Session 数据持久化可靠，不会丢失
- 向后兼容现有的交互模式