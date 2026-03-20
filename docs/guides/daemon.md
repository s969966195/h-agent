# 后台服务

*"该去大闹一场喽。"* — 艾克

h-agent 的守护进程（daemon）在后台持续运行，保持会话上下文，支持多会话管理和自动恢复。

---

## 1. 启动与停止

### 基本操作

```bash
# 启动守护进程（后台运行）
h-agent start

# 查看运行状态
h-agent status

# 停止守护进程
h-agent stop

# 查看日志
h-agent logs
h-agent logs --tail 50        # 最后 50 行
h-agent logs --lines 100      # 同上
```

### 启动输出示例

```
$ h-agent start
Daemon started (PID: 12345, Port: 19527)
```

### 状态输出示例

```
$ h-agent status
Daemon running (PID: 12345, Port: 19527)
  Current session: sess-abc123
  Total sessions: 3
```

### 程序化操作

```python
from h_agent.daemon.client import DaemonClient
from h_agent.daemon.server import DaemonServer

# 连接 daemon
client = DaemonClient()

# 检查连接
if client.ping():
    print("Daemon is alive")

# 获取状态
status = client.status()
print(status)

# 发送命令
result = client.call("session.list")
print(result)

# 获取当前会话
current = client.call("session.current")
print(current)
```

---

## 2. 自动恢复

### 功能概述

Daemon 崩溃后能自动重启，支持会话状态恢复：

```
Daemon 崩溃 → 检测到 → 等待 N 秒 → 重启 → 恢复会话 → 继续工作
```

### SessionRecovery 组件

```python
from h_agent.daemon.recovery import SessionRecovery, CrashHandler, AutoStartManager

recovery = SessionRecovery()

# 恢复所有会话
sessions = recovery.restore_all_sessions()
for session_id, messages in sessions.items():
    print(f"Restored: {session_id} ({len(messages)} messages)")
```

### CrashHandler — 崩溃处理

```python
from h_agent.daemon.recovery import CrashHandler

handler = CrashHandler()

# 注册崩溃回调
def on_crash(session_id: str, exception: Exception):
    print(f"Session {session_id} crashed: {exception}")
    # 保存现场日志等

handler.register_callback(on_crash)

# 启动崩溃监控
handler.start_monitoring()
```

---

## 3. 自动启动（开机自启）

### 功能概述

支持跨平台自动启动：

| 平台 | 机制 |
|------|------|
| macOS | LaunchAgents plist |
| Linux | systemd user service |
| Windows | 注册表 Run key |

### 安装自动启动

```bash
# 安装（自动检测平台）
h-agent autostart install

# 卸载
h-agent autostart uninstall

# 查看状态
h-agent autostart status
```

### 配置自动启动行为

```python
from h_agent.daemon.recovery import AutoStartManager, AutoStartConfig

config = AutoStartConfig(
    enabled=True,
    launch_on_login=True,       # 登录时启动
    restart_on_crash=True,      # 崩溃后重启
    restart_delay_seconds=5,     # 重启延迟
    max_restart_attempts=3,      # 最大重启次数
    start_timeout_seconds=10,   # 启动超时
)

manager = AutoStartManager(config)

# 注册开机自启（macOS）
manager.install_macos()

# 卸载（所有平台）
manager.uninstall()
```

---

## 4. 日志管理

### 日志文件位置

| 平台 | 路径 |
|------|------|
| Linux/macOS | `~/.h-agent/daemon.log` |
| Windows | `%APPDATA%\h-agent\daemon.log` |

### 查看日志

```bash
# 最后 100 行
h-agent logs --tail 100

# 从头查看
h-agent logs

# 实时跟踪日志
tail -f ~/.h-agent/daemon.log
```

### 程序化获取日志

```python
from pathlib import Path
from h_agent.platform_utils import get_config_dir

log_file = get_config_dir() / "daemon.log"

# 读取最后 N 行
def tail_log(n: int = 100) -> str:
    with open(log_file) as f:
        lines = f.readlines()
    return "".join(lines[-n:])

print(tail_log(50))
```

### 日志级别配置

```bash
# 通过环境变量控制
export H_AGENT_LOG_LEVEL=DEBUG
h-agent start
```

---

## 5. 进程间通信

### 通信机制

Daemon 使用 TCP Socket（端口 19527）进行进程间通信，支持 JSON-RPC 风格请求。

### 可用 RPC 方法

| 方法 | 说明 | 参数 |
|------|------|------|
| `ping` | 健康检查 | - |
| `status` | 守护进程状态 | - |
| `session.list` | 列出所有会话 | `tag`, `group` |
| `session.create` | 创建会话 | `name`, `group` |
| `session.get` | 获取会话 | `session_id` |
| `session.delete` | 删除会话 | `session_id` |
| `session.add_message` | 添加消息 | `session_id`, `role`, `content` |

### RPC 调用示例

```python
from h_agent.daemon.client import DaemonClient
import asyncio

async def demo():
    client = DaemonClient()
    
    # 健康检查
    result = await client._send_request("ping")
    print(result)  # {'success': True, 'result': 'pong'}
    
    # 获取状态
    result = await client._send_request("status")
    print(result)

asyncio.run(demo())

# 同步调用
result = client.call("session.list")
print(result)
```

---

## 6. 跨平台注意事项

### Unix (Linux/macOS)

- 使用 Unix Domain Socket（`~/.h-agent/daemon.sock`）优先
- 端口 19527 作为备选
- 信号处理（SIGTERM、SIGINT）正常响应

### Windows

- 仅使用 TCP 端口通信（Unix Socket 不支持）
- 默认端口 19527
- 配置文件存储在 `%APPDATA%\h-agent\`
- PID 文件存储在 `%LOCALAPPDATA%\h-agent\`

### 端口冲突

如果端口 19527 被占用：

```bash
# 使用自定义端口
export H_AGENT_PORT=19528
h-agent start
```

---

## 7. 注意事项

- **先启动再使用**：大部分 CLI 命令会先检查 daemon 是否运行，必要时自动启动
- **单实例**：同一端口只能运行一个 daemon 实例，重复启动会报错
- **权限问题**：Linux/macOS 普通用户无法使用 1024 以下端口
- **防火墙**：Telegram 等远程渠道需要开放对应端口
- **PID 文件**：异常退出时 PID 文件可能残留，手动清理即可
- **日志大小**：长期运行日志会增长，可用 `logrotate` 或定期 `> daemon.log` 清理
