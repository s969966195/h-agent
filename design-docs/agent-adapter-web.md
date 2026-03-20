# Agent Adapter & Web Capability Design

## 1. CLI Agent 调研报告

### 1.1 opencode
- **调用方式**: `opencode run <message>` (非交互式), `opencode serve` (HTTP服务), `opencode acp` (ACP协议)
- **通信协议**: 
  - `run`: stdout 输出文本，结构化数据通过 ANSI 色彩编码
  - `serve`: HTTP SSE 流式输出
  - `acp`: Agent Client Protocol (JSON-RPC over HTTP)
- **进程管理**: subprocess.Popen，支持 `--print-logs --log-level`
- **输出格式**: 终端友好的彩色输出，可通过 `--print-logs` 重定向
- **状态**: 内网常用工具，已配置多种 agents (sisyphus, hephaestus, oracle等)

### 1.2 claude (Anthropic)
- **调用方式**: `claude --print <prompt>` (非交互式)
- **通信协议**: CLI 输出 JSON/文本到 stdout
- **进程管理**: subprocess.run，支持 `--output-format=stream-json`
- **输出格式**: 支持流式 JSON (`--include-partial-messages --output-format=stream-json`)
- **状态**: 已安装

### 1.3 aider
- **调用方式**: `aider --no-autocomplete --no-git --read <file> --message "<prompt>"`
- **通信协议**: CLI 输出
- **状态**: 未安装 (需要 `pip install aider`)

### 1.4 统一接口设计

```python
class BaseAgentAdapter(ABC):
    @abstractmethod
    def chat(self, message: str, **kwargs) -> AgentResponse: ...
    
    @abstractmethod
    def stream_chat(self, message: str, **kwargs) -> Iterator[str]: ...
    
    @abstractmethod
    def stop(self): ...
    
    @property
    @abstractmethod
    def name(self) -> str: ...

@dataclass
class AgentResponse:
    content: str
    tool_calls: list[ToolCall] | None
    error: str | None
    metadata: dict
```

## 2. Playwright Web 模块

### 2.1 功能列表
- `playwright_launch()` - 启动浏览器
- `playwright_navigate(url)` - 导航到 URL
- `playwright_click(selector)` - 点击元素
- `playwright_type(selector, text)` - 输入文本
- `playwright_screenshot()` - 截图
- `playwright_get_headers()` - 获取页面请求/响应 headers
- `playwright_extract_tokens()` - 从 localStorage/sessionStorage 提取 token
- `playwright_evaluate(script)` - 执行 JS

### 2.2 Token 免登录机制
- 保存已登录网站的 cookies/localStorage
- 下次启动时恢复 session state
- 支持导入/导出 session 状态

### 2.3 MCP 协议对接
- 通过 `playwright_mcp_server` 暴露为 MCP 工具
- 工具列表: `playwright_navigate`, `playwright_click`, `playwright_type`, `playwright_screenshot`, `playwright_evaluate`, `playwright_get_cookies`, `playwright_set_cookies`
