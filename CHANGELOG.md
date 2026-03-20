# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
