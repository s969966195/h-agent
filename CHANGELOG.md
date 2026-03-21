# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2025-03-21

### Added
- **Singleton OpenAI Client** (`h_agent/core/client.py`): 中央化的 `@lru_cache` 单例客户端，所有模块共用一个连接池
- **Shared Agent Loop** (`h_agent/core/loop.py`): 提取通用的 `run_agent_loop()` 函数，消除代码重复

### Changed
- **Lazy Loading**: 插件和扩展工具改为首次使用时加载，非模块导入时加载，显著提升启动速度
- **Config Lazy Loading**: 配置文件改为首次 `get_config()` 调用时加载，减少不必要的文件 I/O
- **Parallel Tool Execution**: 只读工具（read, glob, git_status, docker_ps 等 12 个）使用 `ThreadPoolExecutor` 并行执行，延迟从 sum(times) 降为 max(times)
- **Dotenv Deduplication**: 移除重复的 `load_dotenv()` 调用，统一在 `client.py` 中调用一次

### Fixed
- **Session File Locking**: 添加跨平台文件锁（Unix `fcntl.flock` / Windows `msvcrt.locking`），防止多进程并发访问 JSONL 文件导致数据损坏

### Performance Improvements
| 优化项 | 效果 |
|--------|------|
| 单例客户端 | 内存占用降低 ~50%，连接池统一 |
| 懒加载 | 启动时间减少 200-500ms |
| 并行工具执行 | 多工具调用延迟降低 |
| Session 文件锁 | 并发安全 |

## [0.2.0] - 2024-03-20

### Added
- **Test Coverage**: Added comprehensive test suite using pytest with tests for:
  - `SessionManager` (CRUD, tags, groups, search, rename)
  - `ContextGuard` (token estimation, truncation, compaction)
  - `SessionStore` (JSONL persistence)
  - File operation tools (`file_read`, `file_write`, `file_edit`, `file_glob`, `file_exists`, `file_info`)
  - Shell tools (`shell_run`, `shell_env`, `shell_cd`, `shell_which`)
  - JSON utility tools (`json_parse`, `json_format`, `json_query`, `json_validate`)
  - Platform utilities (`which`, `shell_quote`, path utilities, process management)
  - Plugin system
  - Core agent imports
- **CI/CD**: GitHub Actions workflows for:
  - Automated testing on Ubuntu, macOS, Windows with Python 3.10, 3.11, 3.12
  - Automated PyPI release on version tags
- **Type Hints**: Added type annotations throughout the codebase
- **Code Formatting**: Configured `black` and `isort` for code formatting

### Changed
- **Version**: Updated from 0.1.0 to 0.2.0
- **Test Framework**: Migrated from ad-hoc tests to pytest with proper fixtures

## [0.1.0] - 2024-03-19

### Added
- Core agent loop with OpenAI API support
- Tool system (bash, read, write, edit, glob)
- Session management with JSONL persistence
- Context guard with overflow protection
- Multi-channel support
- RAG for codebase understanding
- Plugin system
- CLI with session, config, and daemon management
- Cross-platform support (Linux, macOS, Windows)
