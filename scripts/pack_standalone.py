#!/usr/bin/env python3
"""
scripts/pack_standalone.py - Standalone 打包脚本

用法:
  # 在线环境打包
  pip install h-agent[standalone]
  python scripts/pack_standalone.py

  # 离线环境打包（先在有网环境打包，再拷贝）
  # 打包后生成 dist/h-agent（Linux/macOS）或 dist/h-agent.exe（Windows）

输出:
  dist/h-agent/           # 绿色二进制，独立运行
  dist/h-agent-macos/     # macOS 版本
  dist/h-agent-linux/     # Linux 版本
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST = ROOT / "dist"
SPEC = ROOT / "h-agent.spec"


def build_spec():
    """生成 PyInstaller spec 文件。"""
    python = sys.executable

    # 检测平台
    is_macos = sys.platform == "darwin"
    is_linux = sys.platform == "linux"
    is_win = sys.platform == "win32"

    # 收集数据文件
    data_files = []
    for src in [
        "h_agent/skills",
        "h_agent/features/skills_templates",
    ]:
        src_path = ROOT / src
        if src_path.exists():
            data_files.append((str(src_path), src.replace("h_agent/", "h_agent/")))

    # CLI 入口
    main_script = ROOT / "h_agent" / "__main__.py"

    # hidden imports（避免动态导入失败）
    hidden = [
        "openai",
        "dotenv",
        "flask",
        "h_agent.core.agent_loop",
        "h_agent.features.subagents",
        "h_agent.session.manager",
        "h_agent.memory.long_term",
        "h_agent.memory.summarizer",
        "h_agent.daemon.server",
        "h_agent.team.team",
        "h_agent.team.protocol",
        "h_agent.planner.decomposer",
        "h_agent.planner.scheduler",
        "h_agent.planner.progress",
    ]

    hidden_imports = "\n".join(f"    '{x}'," for x in hidden)

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    [{repr(str(main_script))}],
    pathex=[{repr(str(ROOT))}],
    binaries=[],
    datas={data_files},
    hiddenimports=[
{hidden_imports}
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",   # 不需要数值计算
        "pandas",
        "scipy",
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='h-agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
'''

    if is_macos:
        spec_content += f'''    appname='h-agent',
'''
    spec_content += ''')

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='h-agent',
)
'''

    SPEC.write_text(spec_content, encoding="utf-8")
    print(f"[+] Generated {SPEC}")


def run_pyinstaller(platform: str = None):
    """运行 PyInstaller 打包。"""
    target = platform or sys.platform

    cmd = [sys.executable, "-m", "PyInstaller", "--clean", str(SPEC)]
    print(f"[+] Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"[!] PyInstaller failed with code {result.returncode}")
        return False

    print(f"[+] Build complete → {DIST / 'h-agent'}")
    return True


def pack(clean: bool = True):
    """执行完整打包流程。"""
    print("=" * 50)
    print("h-agent Standalone Packer")
    print("=" * 50)

    # 清理
    if clean:
        print("[*] Cleaning previous build...")
        for p in [DIST, ROOT / "build", SPEC]:
            if p.exists():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()

    # 生成 spec
    print("[*] Generating spec file...")
    build_spec()

    # 打包
    print("[*] Running PyInstaller...")
    if not run_pyinstaller():
        return False

    # 复制 .env.example
    env_example = ROOT / ".env.example"
    if env_example.exists():
        dest = DIST / "h-agent" / ".env.example"
        shutil.copy2(env_example, dest)

    # 创建离线安装说明
    readme = DIST / "h-agent" / "OFFLINE_INSTALL.md"
    readme.write_text("""# Offline Installation

## Requirements
- Python 3.10+ (standalone binary has Python bundled)

## Quick Start
1. Copy `h-agent` directory to target machine
2. Copy `.env.example` to `.env` and fill in your API keys
3. Run: `./h-agent start` (Linux/macOS) or `h-agent.exe start` (Windows)

## Offline Usage
The binary includes all core dependencies. Optional features (RAG) require online installation:
  pip install h-agent[rag]

## Configuration
Config lives in: ~/.h-agent/
Session data:   ~/.h-agent/sessions/
Team data:      ~/.h-agent/team/
Planner data:   ~/.h-agent/planner/

## Autostart (optional)
- macOS:  ./h-agent autostart install
- Linux:  ./h-agent autostart install
- Windows: h-agent.exe autostart install
""", encoding="utf-8")

    print()
    print("[+] Packing complete!")
    print(f"    Output: {DIST / 'h-agent'}")
    print()
    print("    To install offline:")
    print(f"    1. Copy {DIST / 'h-agent'} to target machine")
    print("    2. Copy .env.example → .env and configure API keys")
    print("    3. Run: ./h-agent start")

    return True


if __name__ == "__main__":
    clean = "--no-clean" not in sys.argv
    success = pack(clean=clean)
    sys.exit(0 if success else 1)
