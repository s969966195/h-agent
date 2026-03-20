# 安装部署

*"如果存在限制的话，那我怎么没找到它们呢？"* — 艾克

本文档涵盖 h-agent 的完整安装流程，包括 Windows、Linux/macOS、内网环境和离线部署。

---

## 1. 前置要求

### 系统要求

| 要求 | 说明 |
|------|------|
| Python | 3.10+ |
| pip | 最新版（`pip install --upgrade pip`） |
| 磁盘空间 | 约 100 MB（含依赖） |
| 网络 | 需要访问 OpenAI API（国内需代理或使用国内模型） |

### API Key 准备

h-agent 支持所有 OpenAI 兼容 API，以下是常见配置：

| 服务商 | Base URL | 模型示例 |
|--------|----------|----------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 智谱 AI | `https://open.bigmodel.cn/api/paas/v4` | `glm-4` |
| Azure OpenAI | `https://<resource>.openai.azure.com/v1` | `gpt-4o` |
| 本地 Ollama | `http://localhost:11434/v1` | `llama3`, `qwen2` |

---

## 2. 标准安装

### pip 安装（推荐）

```bash
pip install h-agent
```

### 源码安装（开发版）

```bash
git clone https://github.com/ekko-ai/h-agent.git
cd h-agent
pip install -e .
```

### 带可选依赖安装

```bash
# RAG 支持
pip install h-agent[rag]

# 开发依赖
pip install h-agent[dev]

# 全部依赖
pip install h-agent[all]
```

---

## 3. Windows 安装

### PowerShell（推荐）

```powershell
# 1. 克隆项目
git clone https://github.com/ekko-ai/h-agent.git
cd h-agent

# 2. 创建虚拟环境（推荐）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 安装
pip install -e .

# 4. 初始化配置
h-agent init
```

### CMD

```cmd
git clone https://github.com/ekko-ai/h-agent.git
cd h-agent
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e .
h-agent init
```

### Windows 注意事项

1. **Python PATH**：安装时务必勾选 "Add Python to PATH"
2. **PowerShell 执行策略**：如果遇到脚本运行限制：
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
3. **配置文件位置**：`%APPDATA%\h-agent\`
4. **端口**：Windows 使用 TCP 端口（19527），不使用 Unix Socket
5. **中文路径**：项目路径包含中文可能引发编码问题，建议使用纯英文路径

### Windows 依赖问题

部分依赖在 Windows 上需要编译工具，如遇问题：

```powershell
# 安装 Visual Studio Build Tools（仅 C++ 构建工具）
# 或使用预编译 wheel
pip install --only-binary :all: h-agent
```

---

## 4. Linux/macOS 安装

### 标准安装

```bash
pip install h-agent
```

### 源码安装

```bash
git clone https://github.com/ekko-ai/h-agent.git
cd h-agent
pip install -e .

# 或安装开发版
pip install -e ".[dev]"
```

### macOS Apple Silicon (M1/M2/M3)

```bash
# 确保使用 ARM 版 Python
 arch -arm64 /usr/bin/python3 -m pip install h-agent
```

---

## 5. 内网/离线部署

### 方案一：离线 pip 包

1. **在外网机器下载**：

```bash
# 创建离线包目录
mkdir h-agent-offline && cd h-agent-offline

# 下载 h-agent 及所有依赖
pip download h-agent \
    --destination-dir . \
    --no-deps

# 递归下载依赖（需要多次执行直到无新包）
pip download \
    openai python-dotenv pyyaml \
    --destination-dir . \
    --no-deps
```

2. **传输到内网机器**：
   ```bash
   # 打包
   tar -czvf h-agent-offline.tar.gz h-agent-offline/
   
   # 复制到内网（U盘/SMB/SCP等）
   scp h-agent-offline.tar.gz user@内网服务器:/tmp/
   ```

3. **在内网机器安装**：
   ```bash
   cd /tmp/h-agent-offline
   pip install --no-index --find-links=. h-agent
   ```

### 方案二：虚拟环境打包

```bash
# 在外网机器
python -m venv h-agent-venv
source h-agent-venv/bin/activate
pip install h-agent

# 打包虚拟环境
tar -czvf h-agent-venv.tar.gz h-agent-venv/

# 在内网解压并使用
tar -xzf h-agent-venv.tar.gz
source h-agent-venv/bin/activate
h-agent init
```

### 内网配置

内网无法访问 OpenAI API 时，配置本地模型：

```bash
# 方案 1: Ollama 本地模型
h-agent config --base-url http://localhost:11434/v1
h-agent config --model llama3

# 方案 2: 离线镜像（企业私有模型服务）
h-agent config --base-url https://your-internal-model-server/v1
h-agent config --model your-internal-model
```

### 离线验证

```bash
# 验证安装
h-agent --version

# 验证配置（无需 API 调用）
h-agent config --show

# 测试离线模式（假设使用 Ollama）
ollama serve &
h-agent chat
```

---

## 6. Docker 部署

### 使用 Docker 运行

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
RUN pip install h-agent

# 配置文件
COPY .env /root/.h-agent/.env

ENTRYPOINT ["h-agent", "start"]
```

```bash
# 构建
docker build -t h-agent .

# 运行
docker run -d \
    --name h-agent \
    -p 19527:19527 \
    -v ~/.h-agent:/root/.h-agent \
    -e OPENAI_API_KEY=sk-xxx \
    h-agent
```

### docker-compose 部署

```yaml
version: '3.8'

services:
  h-agent:
    image: h-agent:latest
    container_name: h-agent
    ports:
      - "19527:19527"
    volumes:
      - ~/.h-agent:/root/.h-agent
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_BASE_URL=${OPENAI_BASE_URL}
      - MODEL_ID=${MODEL_ID}
    restart: unless-stopped
    networks:
      - h-agent-net

networks:
  h-agent-net:
    driver: bridge
```

```bash
# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

---

## 7. 服务化部署

### systemd (Linux)

```ini
# ~/.config/systemd/user/h-agent.service
[Unit]
Description=h-agent Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m h_agent.daemon.server
Restart=on-failure
RestartSec=5
Environment="OPENAI_API_KEY=sk-xxx"
Environment="OPENAI_BASE_URL=https://api.openai.com/v1"

[Install]
WantedBy=default.target
```

```bash
# 重新加载 systemd
systemctl --user daemon-reload

# 启用开机自启
systemctl --user enable h-agent

# 启动服务
systemctl --user start h-agent

# 查看状态
systemctl --user status h-agent
```

### launchd (macOS)

```xml
<!-- ~/Library/LaunchAgents/com.h-agent.daemon.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.h-agent.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>h_agent.daemon.server</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OPENAI_API_KEY</key>
        <string>sk-xxx</string>
    </dict>
</dict>
</plist>
```

```bash
# 安装
launchctl load ~/Library/LaunchAgents/com.h-agent.daemon.plist

# 卸载
launchctl unload ~/Library/LaunchAgents/com.h-agent.daemon.plist
```

---

## 8. 代理配置

### HTTP 代理

```bash
# 设置代理环境变量
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080

# 或在 .env 中配置
echo 'HTTP_PROXY=http://proxy.example.com:8080' >> ~/.h-agent/.env
echo 'HTTPS_PROXY=http://proxy.example.com:8080' >> ~/.h-agent/.env
```

### 程序化设置

```python
import os
os.environ["HTTP_PROXY"] = "http://proxy:8080"
os.environ["HTTPS_PROXY"] = "http://proxy:8080"

# 或使用 urllib
import urllib.request
proxy = urllib.request.ProxyHandler({'http': 'http://proxy:8080'})
opener = urllib.request.build_opener(proxy)
urllib.request.install_opener(opener)
```

---

## 9. 常见问题

### Q: 安装时报错 `Microsoft Visual C++ 14.0 is required`

**解决**：Windows 上安装预编译 wheel，或安装 [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)。

### Q: `h-agent: command not found`

**解决**：检查 pip 安装路径是否在 PATH 中：
```bash
python -m pip install h-agent
python -m h_agent --version
```

### Q: 内网部署 API Key 怎么传？

**解决**：使用环境变量或 `.env` 文件：
```bash
export OPENAI_API_KEY=sk-xxx
h-agent start
```

### Q: 离线环境下 RAG 功能还能用吗？

**解决**：RAG 的文件索引功能仍然可用，但语义搜索（向量检索）需要 OpenAI API 生成 embedding，离线无法使用。

### Q: 多机器共享配置？

**解决**：通过 `--config-dir` 指定配置目录，或用 NFS/同步工具共享 `~/.h-agent/`。

---

## 10. 快速验证安装

```bash
# 1. 验证版本
h-agent --version

# 2. 初始化（如首次）
h-agent init

# 3. 检查配置
h-agent config --show

# 4. 启动 daemon
h-agent start
h-agent status

# 5. 测试对话
h-agent run "1+1 等于几？"
```
