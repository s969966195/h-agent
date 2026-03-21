# Agent Team 配置最佳实践

本文档教你如何从零配置一个完整的多Agent团队。

---

## 一、项目结构

建议按以下结构组织配置：

```
h-agent-config/
├── __init__.py
├── agents/                 # Agent定义
│   ├── __init__.py
│   ├── prompts.py         # 所有Agent的System Prompt
│   └── roles.py           # Agent角色配置
├── team.py                # 团队初始化
├── workflows/             # 工作流配置
│   ├── __init__.py
│   ├── morning.py         # 早晨routine
│   └── evening.py        # 晚间routine
├── skills/               # 自定义Skill（可选）
│   ├── __init__.py
│   └── email_check.py
└── main.py               # 入口
```

---

## 二、定义Agent角色

### 2.1 角色枚举

```python
# agents/roles.py
from h_agent.team.team import AgentRole

# 扩展角色枚举（可选，如果需要更多角色）
class MyAgentRole(AgentRole):
    PRODUCT = "product"
    ARCHITECT = "architect"
    OPERATIONS = "operations"
```

### 2.2 预定义角色映射

| 你需要的角色 | h-agent预定义角色 | 说明 |
|------------|------------------|------|
| 组长 | COORDINATOR | 协调工作 |
| 产品 | RESEARCHER | 调研分析 |
| 架构 | PLANNER | 任务规划 |
| 开发 | CODER | 代码实现 |
| 测试 | REVIEWER | 审查验证 |
| 运维 | DEVOPS | 部署运维 |

---

## 三、编写System Prompt

这是**最核心**的配置。每个Agent的能力和性格都由它决定。

### 3.1 Prompt结构

```python
# agents/prompts.py

# ============ 组长Agent ============
LEADER_PROMPT = """你是一个技术团队的组长，负责协调团队工作。

团队成员：
- 产品(Researcher)：负责需求调研，输出PRD
- 架构(Planner)：负责技术方案设计
- 开发(Coder)：负责代码实现
- 测试(Reviewer)：负责测试验证
- 运维(DevOps)：负责部署运维

你的职责：
1. 理解用户需求
2. 分解任务，委托给合适的Agent
3. 跟踪进度，协调问题
4. 向用户汇报结果

【关键规则】
- 通过 team.delegate("Agent名", "任务类型", "任务内容") 委托任务
- 通过 team.query("Agent名", "问题") 查询状态
- 通过 team.talk_to("Agent名", "消息") 与Agent对话
- 开发完成后自动委托测试，不要等待

【早晨Routine】
每天开始工作时，你应该：
1. 检查各Agent昨日工作总结
2. 查看是否有紧急任务
3. 向用户简报今日计划

【晚间Routine】
每天结束时，你应该：
1. 收集各Agent的工作总结
2. 汇总成日报告
3. 压缩memory
"""

# ============ 产品Agent ============
PRODUCT_PROMPT = """你是一个资深产品经理。

职责：接收需求调研任务，输出产品需求文档（PRD）

输出格式：
## 需求背景
[为什么需要这个功能]

## 功能列表
1. [功能1]：描述
2. [功能2]：描述

## 用户故事
- 作为[用户]，我想要[功能]，以便[收益]

## 优先级
- P0：[必须有的]
- P1：[重要的]
- P2：[可选的]

【工作流程】
1. 接收组长委托
2. 分析需求
3. 输出PRD
4. 通过 team.delegate("组长", "完成", PRD内容) 汇报
"""

# ============ 架构Agent ============
ARCHITECT_PROMPT = """你是一个资深架构师。

职责：根据需求和PRD，设计技术方案

输出格式：
## 技术选型
- 语言/框架
- 数据库
- 中间件

## 系统设计
[架构图或文字描述]

## 接口设计
[API接口列表]

## 数据模型
[核心数据表结构]

【工作流程】
1. 接收组长委托
2. 参考产品PRD
3. 输出技术方案
4. 通过 team.delegate("组长", "完成", 方案内容) 汇报
"""

# ============ 开发Agent ============
DEVELOPER_PROMPT = """你是一个资深开发工程师。

职责：根据需求和架构方案，实现代码

【关键规则】
1. 完成后必须自动通知测试：
   team.delegate("测试", "测试", "测试内容")
2. 如果测试失败，修复后重新测试
3. 测试通过后汇报组长

【可用工具】
- bash：执行命令
- read/write/edit：文件操作
- glob：查找文件

【工作流程】
1. 接收组长委托
2. 参考架构方案
3. 编写代码
4. 执行测试验证
5. 通知测试Agent
6. 收到测试反馈后修复（如有）
7. 测试通过后汇报组长
"""

# ============ 测试Agent ============
TESTER_PROMPT = """你是一个资深测试工程师。

职责：测试开发提交的代码

输出格式：
## 测试结果
- 通过：✓
- 失败：✗（附原因）

## 测试用例
1. [用例1]：通过/失败
2. [用例2]：通过/失败

【工作流程】
1. 等待开发Agent的测试请求
2. 编写测试用例
3. 执行测试
4. 报告结果给开发Agent：
   team.talk_to("开发", "测试失败：原因")
5. 或汇报组长：
   team.delegate("组长", "完成", "测试通过")
"""

# ============ 运维Agent ============
OPS_PROMPT = """你是一个资深运维工程师。

职责：部署方案、运维文档

【工作流程】
1. 接收组长委托
2. 输出部署方案
3. 汇报组长
"""

# ============ 汇总 ============
PROMPTS = {
    "组长": LEADER_PROMPT,
    "产品": PRODUCT_PROMPT,
    "架构": ARCHITECT_PROMPT,
    "开发": DEVELOPER_PROMPT,
    "测试": TESTER_PROMPT,
    "运维": OPS_PROMPT,
}
```

---

## 四、初始化团队

```python
# team.py
from h_agent.team.team import AgentTeam, AgentRole
from h_agent.core.client import get_client
from h_agent.core.config import MODEL
from agents.prompts import PROMPTS

def create_llm_handler(name: str, prompt: str):
    """为Agent创建LLM Handler"""
    client = get_client()
    
    def handler(msg) -> dict:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"任务类型: {msg.type}\n任务内容: {msg.content}"}
            ],
            max_tokens=4096,
        )
        return {
            "agent_name": name,
            "role": "coordinator",
            "success": True,
            "content": response.choices[0].message.content,
        }
    return handler

def init_team(team_id: str = "my-team") -> AgentTeam:
    """初始化团队"""
    team = AgentTeam(team_id=team_id)
    
    role_map = {
        "组长": AgentRole.COORDINATOR,
        "产品": AgentRole.RESEARCHER,
        "架构": AgentRole.PLANNER,
        "开发": AgentRole.CODER,
        "测试": AgentRole.REVIEWER,
        "运维": AgentRole.DEVOPS,
    }
    
    for name, role in role_map.items():
        team.register(
            name=name,
            role=role,
            handler=create_llm_handler(name, PROMPTS[name]),
            description=f"{name}Agent",
        )
        print(f"✓ 注册 {name}Agent")
    
    return team

# 快捷函数
def get_team() -> AgentTeam:
    """获取已初始化的团队（单例）"""
    if not hasattr(get_team, "_team"):
        get_team._team = init_team()
    return get_team._team
```

---

## 五、基础使用

```python
# main.py
from team import get_team

def main():
    team = get_team()
    
    # 向组长下达任务
    result = team.delegate("组长", "任务", "帮我开发一个用户登录功能")
    print(result.content)

if __name__ == "__main__":
    main()
```

运行：
```bash
python main.py
```

---

## 六、早晨/晚间Routine

### 6.1 早晨Routine

```python
# workflows/morning.py
from team import get_team

def morning_brief():
    """早晨简报"""
    team = get_team()
    
    print("="*50)
    print("🌅 早晨简报")
    print("="*50)
    
    # 查询各Agent昨日工作总结
    for agent in ["产品", "开发", "测试", "运维"]:
        result = team.query(agent, "请简述你昨天完成的工作")
        print(f"\n【{agent}】:\n{result.content[:300]}...")
    
    # 向组长获取今日计划
    plan = team.query("组长", "根据昨日情况，列出今日工作计划")
    print(f"\n【今日计划】:\n{plan.content}")

    return plan.content
```

### 6.2 晚间Routine

```python
# workflows/evening.py
from team import get_team

def evening_summary():
    """晚间总结"""
    team = get_team()
    
    print("="*50)
    print("🌙 晚间总结")
    print("="*50)
    
    # 收集各Agent工作总结
    summaries = {}
    for agent in ["产品", "开发", "测试", "运维"]:
        result = team.query(agent, "请总结你今天完成的工作")
        summaries[agent] = result.content
        print(f"\n【{agent}】:\n{result.content[:200]}...")
    
    # 组长汇总
    summary_prompt = "汇总以下工作总结，生成日报告：\n" + "\n".join([
        f"{k}：{v}" for k, v in summaries.items()
    ])
    report = team.query("组长", summary_prompt)
    print(f"\n【日报告】:\n{report.content}")
    
    return report.content
```

---

## 七、定时任务配置

### 7.1 使用Heartbeat

```python
# scheduler.py
from h_agent.scheduler.heartbeat import HeartbeatMonitor
from workflows.morning import morning_brief
from workflows.evening import evening_summary

def start_scheduler():
    """启动定时任务"""
    scheduler = HeartbeatMonitor()
    
    # 每天早上9点执行早晨简报
    scheduler.add_job(
        name="morning_brief",
        cron="@daily",
        command="python -c 'from workflows.morning import morning_brief; morning_brief()'",
        enabled=True,
    )
    
    # 每天晚上6点执行晚间总结
    scheduler.add_job(
        name="evening_summary", 
        cron="0 18 * * *",  # 每天18:00
        command="python -c 'from workflows.evening import evening_summary; evening_summary()'",
        enabled=True,
    )
    
    # 启动（守护进程模式）
    scheduler.start(daemon=True)
```

### 7.2 使用系统Cron

```bash
# 添加到crontab
crontab -e

# 每天早上9点
0 9 * * * cd /path/to/project && python main.py --morning

# 每天晚上6点
0 18 * * * cd /path/to/project && python main.py --evening
```

对应的 `main.py`：
```python
import sys

def main():
    if "--morning" in sys.argv:
        from workflows.morning import morning_brief
        morning_brief()
    elif "--evening" in sys.argv:
        from workflows.evening import evening_summary
        evening_summary()
    else:
        # 交互模式
        team = get_team()
        team.talk_to("组长", input("请输入任务: "))
```

---

## 八、自定义Skill

如果需要扩展能力（如查邮件），可以创建Skill：

```python
# skills/email_check.py
"""邮件检查Skill"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_emails",
            "description": "检查邮箱中的未读邮件",
            "parameters": {
                "type": "object",
                "properties": {
                    "account": {"type": "string", "description": "邮箱账号"},
                    "limit": {"type": "integer", "description": "最多查看数量", "default": 10},
                },
                "required": ["account"],
            },
        },
    }
]

def check_emails(account: str, limit: int = 10) -> str:
    """检查邮件（实际实现需要接入邮件API）"""
    # TODO: 实现邮件检查逻辑
    return f"未读邮件: 3封\n1. [主题1]\n2. [主题2]\n3. [主题3]"

HANDLERS = {
    "check_emails": check_emails,
}
```

注册到团队：
```python
def init_team_with_skills() -> AgentTeam:
    from skills.email_check import TOOLS, HANDLERS
    
    team = init_team()
    
    # 为组长添加邮件Skill
    team.members["组长"].tools.extend(TOOLS)
    
    return team
```

---

## 九、完整项目模板

创建一个快速开始的模板项目：

```bash
mkdir my-agent-team && cd my-agent-team
```

创建以下文件：

### 9.1 agents/prompts.py
```python
# 见上文 Section 3.1
```

### 9.2 team.py
```python
# 见上文 Section 4
```

### 9.3 main.py
```python
#!/usr/bin/env python3
import sys
from team import get_team

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--morning":
            from workflows.morning import morning_brief
            morning_brief()
            return
        elif cmd == "--evening":
            from workflows.evening import evening_summary
            evening_summary()
            return
    
    # 默认：向组长发送任务
    team = get_team()
    task = input("\n请描述你的需求（输入q退出）: ")
    if task.lower() == 'q':
        return
    
    result = team.delegate("组长", "任务", task)
    print("\n" + "="*50)
    print("【组长回复】")
    print("="*50)
    print(result.content)

if __name__ == "__main__":
    main()
```

### 9.4 workflows/__init__.py
```python
# workflows包
```

### 9.5 workflows/morning.py
```python
# 见上文 Section 6.1
```

### 9.6 workflows/evening.py
```python
# 见上文 Section 6.2
```

---

## 十、运行

```bash
# 交互模式
python main.py

# 早晨简报
python main.py --morning

# 晚间总结
python main.py --evening

# 配置定时任务（添加到crontab）
echo "0 9 * * * cd $(pwd) && python main.py --morning" >> ~/.crontab
echo "0 18 * * * cd $(pwd) && python main.py --evening" >> ~/.crontab
```

---

## 十一、调试技巧

### 11.1 查看团队状态
```python
team = get_team()
print(team.list_members())  # 列出所有Agent
print(team.pending_tasks)   # 查看待处理任务
print(team.history)         # 查看历史记录
```

### 11.2 单独测试某个Agent
```python
team = get_team()
result = team.query("开发", "你好，请介绍一下你自己")
print(result.content)
```

### 11.3 查看Agent系统提示
```python
team = get_team()
print(team.members["开发"].system_prompt)
```

---

## 十二、常见问题

### Q: Agent不按预期工作怎么办？
A: 调整System Prompt，越具体越好。Prompt是唯一的控制手段。

### Q: 如何让Agent记住上下文？
A: Agent的每次调用是独立的。如果需要记忆，需要在prompt中包含上下文。

### Q: 任务委托失败怎么办？
A: 检查Agent名是否正确：`team.list_members()`

### Q: 如何增加新的Agent角色？
A: 直接在 `role_map` 中添加，使用 `AgentRole.COORDINATOR` 或扩展枚举。

---

## 总结

配置Agent Team的核心：
1. **写好System Prompt** — 决定Agent的行为和能力
2. **正确的委托调用** — `delegate()`, `query()`, `talk_to()`
3. **合理的定时任务** — 自动化早晨/晚间Routine

现在开始配置你的团队吧！
