# 任务规划

*"不要放弃，直到做对为止。"* — 艾克

h-agent 内置任务规划模块，提供任务分解、调度执行、进度跟踪三大能力。

---

## 1. 任务分解 (decomposer)

### 功能概述

将复杂任务自动分解为可执行的子任务树：

```
任务 "重构用户模块"
  ├─ T1: 分析现有代码结构
  ├─ T2: 设计新架构
  ├─ T3: 实现 UserService
  ├─ T4: 编写单元测试
  └─ T5: 更新 API 文档
```

### 核心组件

```python
from h_agent.planner.decomposer import Task, TaskStatus, TaskTree
```

### Task 数据结构

```python
@dataclass
class Task:
    task_id: str              # 唯一 ID，格式 t-xxxxxxxx
    parent_id: Optional[str]   # 父任务 ID（None 表示根任务
    
    # 任务内容
    title: str                # 简短标题
    description: str          # 详细描述
    instructions: str          # 给 Agent 的具体指令
    expected_output: str       # 期望输出
    
    # 元数据
    status: TaskStatus        # PENDING/RUNNING/DONE/FAILED/BLOCKED/SKIPPED
    priority: int             # 0=正常, 1=高, 2=紧急
    tags: List[str]           # 标签
    
    # 分配
    assigned_to: Optional[str]  # Agent 名称
    role_hint: Optional[str]    # 建议分配的角色
    
    # 执行
    result: Any               # 执行结果
    error: Optional[str]      # 错误信息
    retry_count: int          # 当前重试次数
    max_retries: int          # 最大重试次数（默认 2）
    
    # 时间戳
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
```

### 任务树操作

```python
from h_agent.planner.decomposer import TaskTree, Task, TaskStatus

# 创建任务树
tree = TaskTree()

# 添加根任务
root = tree.add_task(
    title="重构用户模块",
    description="将 monolith user 模块拆分为独立微服务",
    instructions="参考 src/users/ 现有实现，设计 RESTful API",
    expected_output="新的 users-service 代码",
    priority=1,
    tags=["refactor", "backend"]
)

# 添加子任务
t1 = tree.add_task(
    title="分析现有代码",
    description="了解当前用户模块的结构和依赖",
    parent_id=root.task_id,
)
t2 = tree.add_task(
    title="设计新架构",
    description="设计微服务架构，包括 API 和数据模型",
    parent_id=root.task_id,
)

# 添加兄弟任务（同一父任务下的顺序任务）
t3 = tree.add_task(
    title="实现 UserService",
    description="实现核心业务逻辑",
    after_task_ids=[t2.task_id],  # 依赖 t2
    parent_id=root.task_id,
)

# 设置任务状态
tree.update_status(t1.task_id, TaskStatus.DONE)
tree.update_status(t2.task_id, TaskStatus.RUNNING)

# 查看任务树
tree.print_tree()
```

### 自动分解

```python
from h_agent.planner.decomposer import auto_decompose

# 自动将自然语言任务分解为子任务
tasks = auto_decompose(
    task="实现一个博客系统，包含用户注册、文章发布、评论功能",
    context="使用 FastAPI + PostgreSQL",
    max_depth=2,
)
for t in tasks:
    print(f"{t.task_id}: {t.title}")
```

### 任务状态流转

```
PENDING → RUNNING → DONE
                ↘ FAILED → (retry) → RUNNING
                ↘ BLOCKED → (unblock) → PENDING
PENDING → SKIPPED (手动跳过)
```

### 注意事项

- `task_id` 全局唯一，格式为 `t-` + 8 位十六进制字符串
- 子任务完成后，父任务不会自动完成，需手动标记
- 任务状态保存在 `~/.h-agent/planner/` 目录

---

## 2. 任务调度 (scheduler)

### 功能概述

并发任务调度器，按依赖关系执行任务：

```
调度器特点:
- 维护待执行队列
- 按依赖顺序调度
- 控制并发数（默认 3）
- 失败自动重试
- 进度回调通知
- 状态持久化
```

### 基本使用

```python
from h_agent.planner.scheduler import TaskScheduler, SchedulerConfig
from h_agent.planner.decomposer import Task, TaskStatus

config = SchedulerConfig(
    max_workers=3,         # 最大并发数
    task_timeout=300,     # 单任务超时（秒）
    retry_delay=5,        # 重试间隔（秒）
    poll_interval=1.0,    # 队列轮询间隔
    save_interval=30.0,   # 状态保存间隔
)

scheduler = TaskScheduler(config=config)

# 定义任务执行函数
def run_task(task: Task) -> str:
    if task.title == "编译代码":
        return "编译成功"
    elif task.title == "运行测试":
        return "全部通过"
    return "完成"

# 添加任务
scheduler.add_task(task1)
scheduler.add_task(task2)
scheduler.add_task(task3)

# 启动调度（阻塞）
scheduler.start()

# 获取结果
for task_id, result in scheduler.get_results().items():
    print(f"{task_id}: {result}")
```

### 非阻塞调度

```python
# 启动调度器（非阻塞）
scheduler.start(blocking=False)

# 等待所有任务完成
scheduler.wait_for_completion(timeout=600)

# 检查状态
if scheduler.is_done():
    print("All tasks completed!")
else:
    pending = scheduler.get_pending()
    running = scheduler.get_running()
    print(f"Pending: {len(pending)}, Running: {len(running)}")
```

### 进度回调

```python
from h_agent.planner.scheduler import SchedulerEvent

def on_event(event: SchedulerEvent, task: Task = None):
    if event == SchedulerEvent.TASK_STARTED:
        print(f"▶ 开始: {task.title}")
    elif event == SchedulerEvent.TASK_COMPLETED:
        print(f"✓ 完成: {task.title}")
    elif event == SchedulerEvent.TASK_FAILED:
        print(f"✗ 失败: {task.title} - {task.error}")

scheduler.on(SchedulerEvent.TASK_STARTED, on_event)
scheduler.on(SchedulerEvent.TASK_COMPLETED, on_event)
scheduler.on(SchedulerEvent.TASK_FAILED, on_event)
```

### 调度配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_workers` | 3 | 最大并发任务数 |
| `task_timeout` | 300 秒 | 单任务超时 |
| `retry_delay` | 5 秒 | 重试前等待 |
| `poll_interval` | 1 秒 | 队列检查间隔 |
| `save_interval` | 30 秒 | 状态持久化间隔 |

---

## 3. 进度跟踪 (progress)

### 功能概述

实时计算任务进度百分比，支持 ETA 估算和里程碑检测：

```python
from h_agent.planner.progress import ProgressTracker, Milestone
```

### 基本使用

```python
tracker = ProgressTracker(scheduler=scheduler)

# 定义里程碑
tracker.define_milestone(
    name="开发完成",
    task_ids=["t-abc12345", "t-def67890"],
    description="所有功能开发完成"
)
tracker.define_milestone(
    name="上线",
    task_ids=["t-xyz11111"],
    description="系统正式上线"
)

# 获取进度
progress = tracker.get_progress()
print(f"进度: {progress * 100:.1f}%")

# 获取 ETA
eta = tracker.get_eta()
if eta:
    print(f"预计完成: {eta}")

# 检测里程碑
milestone = tracker.check_milestone("开发完成")
if milestone and milestone.reached:
    print(f"🎉 {milestone.name} 已达成！")
```

### 格式化报告

```python
# 生成文本报告
report = tracker.generate_report()
print(report)

# 报告示例:
# 进度: 60.0%
# 耗时: 120s
# ETA: 80s
# 里程碑: [✓] 开发完成 [ ] 上线
# 当前任务:
#   ▶ 实现用户认证 (RUNNING)
#   ○ 编写 API 文档 (PENDING)
```

### 保存报告

```python
# 保存到文件
tracker.save_report("/path/to/report.json")

# 保存进度快照
tracker.snapshot()  # 保存到 ~/.h-agent/planner/progress_report.json
```

---

## 4. 三者协同

```
用户输入任务
     ↓
decomposer.decompose()     ← 分解任务为树
     ↓
scheduler.add_task()       ← 加入调度队列
     ↓
scheduler.start()          ← 按依赖并发执行
     ↓
progress.track()           ← 实时跟踪进度
     ↓
agent_loop 调用 tools       ← 实际执行工作
     ↓
scheduler.on(EVENT)        ← 事件回调更新进度
     ↓
progress.check_milestone()  ← 里程碑检测
     ↓
完成 / 失败 / 重试
```

---

## 5. 命令行使用

```bash
# 调度器状态文件
ls ~/.h-agent/planner/

# 调度器状态
cat ~/.h-agent/planner/scheduler_state.json

# 进度报告
cat ~/.h-agent/planner/progress_report.json
```

---

## 6. 注意事项

- **依赖循环检测**：`add_task` 时如果检测到循环依赖会抛出异常
- **超时不杀死进程**：超时后标记任务为失败，但不会强制终止进程
- **状态持久化**：调度器状态每 30 秒保存一次，崩溃后可恢复
- **里程碑是软检测**：里程碑到达只是检查相关任务状态，不触发特殊行为
- **并发数设置**：并发数过高可能导致资源竞争，建议 3-5
