# Web Automation Guide

使用 Playwright 进行浏览器自动化和网页交互。

## 概述

h-agent 的 Web 模块提供：
- **浏览器控制** - 自动化浏览器操作
- **MCP 服务器** - Model Context Protocol 服务器
- **Playwright 集成** - 高级浏览器自动化

## 快速开始

```python
from h_agent.web.players.playwright_client import PlaywrightClient

# 创建客户端
client = PlaywrightClient()

# 打开浏览器
await client.start()

# 导航到页面
await client.navigate("https://example.com")

# 执行操作
await client.click("button#submit")
await client.fill("input#email", "user@example.com")

# 获取页面内容
content = await client.get_content()
print(content)

# 截图
await client.screenshot("screenshot.png")

# 关闭
await client.stop()
```

## PlaywrightClient

### 初始化

```python
from h_agent.web.players.playwright_client import PlaywrightClient

client = PlaywrightClient(
    headless=True,      # 无头模式
    browser="chromium", # 浏览器类型: chromium, firefox, webkit
    timeout=30000,      # 超时时间(ms)
)
```

### 导航操作

```python
# 打开 URL
await client.navigate("https://example.com")

# 返回
await client.go_back()

# 前进
await client.go_forward()

# 刷新
await client.reload()

# 滚动
await client.scroll_to(0, 500)      # 滚动到位置
await client.scroll_by(0, 200)       # 相对滚动
```

### 元素操作

```python
# 点击
await client.click("button.submit")
await client.click("a[href='/about']", button="right")  # 右键

# 填写表单
await client.fill("input#name", "John Doe")
await client.fill("textarea#message", "Hello!")

# 选择
await client.select("select#country", "CN")
await client.check("input#agree")
await client.uncheck("input#newsletter")

# 悬停
await client.hover("div.dropdown")

# 拖拽
await client.drag_and_drop("#source", "#target")
```

### 页面查询

```python
# 获取元素文本
text = await client.text("h1.title")

# 获取元素属性
href = await client.get_attribute("a.link", "href")

# 检查元素存在
exists = await client.is_visible("button#next")

# 获取输入值
value = await client.input_value("input#search")

# 获取页面标题
title = await client.title()

# 获取当前 URL
url = client.url()
```

### 等待

```python
# 等待元素出现
await client.wait_for_selector("div.loaded", timeout=5000)

# 等待元素消失
await client.wait_for_selector("div.loading", state="hidden")

# 等待页面加载
await client.wait_for_load_state("networkidle")

# 等待函数返回 true
await client.wait_for_function("() => document.querySelector('.ready')")
```

### 截图和截图

```python
# 截图（整页）
await client.screenshot("page.png")

# 截图（单个元素）
await client.screenshot("button.png", element="button#logo")

# 获取页面内容
content = await client.get_content()
inner_html = await client.inner_html("div.content")
outer_html = await client.outer_html("div.content")
```

### 执行 JavaScript

```python
# 执行脚本
result = await client.evaluate("""
    () => {
        return document.title;
    }
""")

# 带参数
result = await client.evaluate("""
    (x, y) => x + y
""", 1, 2)
```

## 上下文管理

```python
# 创建新上下文（隔离 cookie）
context = await client.new_context()
page = await context.new_page()

# 使用现有上下文
await client.use_context(context)

# 关闭上下文
await context.close()
```

### 上下文持久化

```python
# 保存上下文到文件
storage = await context.storage_state()
with open("state.json", "w") as f:
    json.dump(storage, f)

# 加载上下文
with open("state.json") as f:
    storage = json.load(f)
context = await client.new_context(storage_state=storage)
```

## 等待条件

```python
from h_agent.web.players.playwright_client import wait_for

# 预定义等待条件
await client.wait_for(
    wait_for.selector("button.ready"),
    wait_for.function(lambda: client.title() == "Done"),
    timeout=10000,
)
```

## 错误处理

```python
try:
    await client.click("button#nonexistent")
except PlaywrightError as e:
    print(f"操作失败: {e}")

# 检查元素是否存在
if await client.is_visible("button#submit"):
    await client.click("button#submit")
```

## MCP 服务器

### 启动 MCP 服务器

```python
from h_agent.web.players.mcp_server import MCPBrowserServer

server = MCPBrowserServer(port=8765)
await server.start()

# 服务器提供 WebDriver BIDI API
```

### 连接到 MCP 服务器

```python
from h_agent.web.players.playwright_client import PlaywrightClient

client = PlaywrightClient(
    ws_url="ws://localhost:8765",  # MCP 服务器地址
)
```

## CLI 用法

```bash
# 启动浏览器
python -m h_agent.web.players.playwright_client --headless

# 截图
python -m h_agent.web.players.playwright_client screenshot https://example.com
```

## 最佳实践

### 1. 使用选择器

```python
# 优先使用更具体的选择器
await client.click("button#submit-form")      # ✅ ID
await client.click("button.primary")         # ✅ Class
await client.click("[data-testid='submit']")  # ✅ Data attribute

# 避免过长的选择器
await client.click("body > div > form > button")  # ❌
```

### 2. 正确等待

```python
# ✅ 等待元素可操作
await client.wait_for_selector("button#next")
await client.click("button#next")

# ❌ 不等待直接操作
await client.click("button#next")  # 可能失败
```

### 3. 处理弹窗

```python
# 等待并处理对话框
async def handle_dialog(dialog):
    print(f"对话框: {dialog.message}")
    await dialog.accept()  # 或 dialog.dismiss()

client.on("dialog", handle_dialog)
await client.click("button#trigger-dialog")
```

### 4. 资源清理

```python
# ✅ 使用 context manager
async with PlaywrightClient() as client:
    await client.navigate("https://example.com")
    # 自动清理

# ✅ 或手动清理
client = PlaywrightClient()
try:
    await client.start()
    # ... 操作
finally:
    await client.stop()
```
