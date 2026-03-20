# Agent Team Guide

多 agent 协作系统，让不同的 agent 可以协同工作。

## 快速开始

```python
from h_agent.team.team import AgentTeam, AgentRole
from h_agent.team.protocol import get_zoo_animal

# 创建团队
team = AgentTeam("my-project")

# 注册本地 handler
def planner_handler(msg):
    return TaskResult(success=True, content="任务已规划")

team.register("planner", AgentRole.PLANNER, planner_handler)

# 注册外部 adapter
team.register_adapter("coder", AgentRole.CODER, "opencode", {"agent": "code"})
team.register_adapter("reviewer", AgentRole.REVIEWER, "claude")

# 使用 zoo animals
team.register_zoo_animal("xueqiu")  # 自动选择 RESEARCHER 角色
team.register_zoo_animal("liuliu", AgentRole.CODER)  # 自定义角色
```

## 团队角色

| 角色 | 说明 | 默认动物 |
|------|------|----------|
| PLANNER | 任务规划、分解 | heibai |
| CODER | 编码实现 | liuliu |
| REVIEWER | 代码审查 | xiaohuang |
| DEVOPS | 部署运维 | xiaozhu |
| RESEARCHER | 调研分析 | xueqiu |

## 任务分发

### 单个分发 (delegate)

```python
# 指定 agent 执行任务
result = team.delegate("coder", "task", "实现用户登录功能")
print(result.content)
```

### 广播 (broadcast)

```python
# 多个 agent 同时处理
results = team.broadcast(
    task_type="review",
    task_content="检查代码安全性",
    target_roles=[AgentRole.REVIEWER, AgentRole.DEVOPS],  # 可选：筛选角色
)
```

### 查询 (query)

```python
# 向单个 agent 发送查询
result = team.query("xueqiu", "Python 异步编程的最佳实践")
```

## Zoo Animals

### 可用动物

| 动物 | 名称 | 特点 |
|------|------|------|
| xueqiu | 雪球猴 | 研究专家，擅长搜索和分析 |
| liuliu | 流水獭 | 代码架构，擅长系统设计和重构 |
| xiaohuang | 小黄狗 | QA 测试，擅长测试和边缘案例 |
| heibai | 黑白熊 | 文档专家，擅长写文档和注释 |
| xiaozhu | 小猪 | DevOps，擅长容器化和 CI/CD |

### 直接调用

```python
from h_agent.adapters.zoo_adapter import ZooAdapter, list_zoo_animals

# 列出所有动物
animals = list_zoo_animals()
for animal in animals:
    print(f"{animal.name}: {animal.description}")

# 直接调用
adapter = ZooAdapter(animal="xueqiu")
response = adapter.chat("搜索 React 状态管理的最佳实践")
print(response.content)
```

### 团队集成

```python
# 快速注册整个动物园
team.register_zoo_animal("xueqiu")
team.register_zoo_animal("liuliu")
team.register_zoo_animal("xiaohuang")

# 使用
result = team.delegate("xueqiu", "research", "前端状态管理方案调研")
```

## 结果聚合

```python
# 分发任务给多个 agent
results = team.broadcast("implement", "实现某个功能")

# 聚合结果
summary = team.aggregate_results(results)
print(f"成功: {summary['succeeded']}/{summary['total']}")

# 按角色统计
for role, stats in summary['by_role'].items():
    print(f"{role}: {stats['success']} 成功, {stats['failed']} 失败")
```

## 进度跟踪

```python
# 查看待处理任务
pending = team.list_pending_tasks()

# 查看历史
history = team.list_history(limit=50)

# 查看任务状态
status = team.get_task_status(task_id)
```

## 完整示例

```python
from h_agent.team.team import AgentTeam, AgentRole, TaskResult
from h_agent.adapters.zoo_adapter import ZooAdapter

# 创建团队
team = AgentTeam("web-app")

# 注册不同角色的 agent
team.register_adapter("arch", AgentRole.PLANNER, "opencode", {
    "agent": "architect",
    "model": "gpt-4o"
})
team.register_adapter("dev", AgentRole.CODER, "zoo", {"animal": "liuliu"})
team.register_adapter("tester", AgentRole.REVIEWER, "zoo", {"animal": "xiaohuang"})
team.register_zoo_animal("xueqiu", AgentRole.RESEARCHER)

# 协调工作流程
print("1. 调研阶段...")
research = team.delegate("xueqiu", "research", "React vs Vue for enterprise app")

print("2. 规划阶段...")
plan = team.delegate("arch", "plan", f"基于以下调研结果设计系统架构: {research.content}")

print("3. 开发阶段...")
dev_result = team.delegate("dev", "implement", plan.content)

print("4. 测试阶段...")
test_result = team.delegate("tester", "test", dev_result.content)

# 汇总
if test_result.success:
    print("✅ 项目完成!")
else:
    print(f"❌ 需要修复: {test_result.error}")
```

## 配置

### 环境变量

```bash
# Zoo 配置
export ZOO_PATH=zoo
export ZOO_TIMEOUT=300
export ZOO_API_KEY=your_key

# Adapter 配置
export OPENCODE_PATH=opencode
export ANTHROPIC_API_KEY=your_key
```

### Team 持久化

团队状态保存在 `~/.h-agent/team/team_state.json`

- 成员列表
- 待处理任务
- 历史记录（最近 100 条）
