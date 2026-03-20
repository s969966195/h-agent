#!/usr/bin/env python3
"""
h_agent/codebase/indexer.py - Project Code Indexer

Indexes project files and code chunks for semantic search.
"""

import os
import re
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Iterator, Set
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================================================
# Configuration
# ============================================================

DEFAULT_INDEX_DIR = Path.home() / ".h-agent" / "codebase_index"
DEFAULT_INDEX_DIR.mkdir(parents=True, exist_ok=True)

IGNORED_DIRS: Set[str] = {
    'node_modules', '.git', '__pycache__', 'dist', 'build',
    '.venv', 'venv', '.env', '.idea', '.vscode', '.pytest_cache',
    '.tox', '.mypy_cache', '.coverage', 'htmlcov', '.nox',
    'vendor', 'target', 'bin', 'obj', 'packages',
}

SUPPORTED_EXTENSIONS: Set[str] = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.vue',
    '.java', '.kt', '.go', '.rs', '.c', '.cpp', '.h', '.hpp',
    '.cs', '.rb', '.php', '.swift', '.m', '.mm',
    '.sh', '.bash', '.zsh', '.fish',
    '.yaml', '.yml', '.toml', '.json', '.xml',
    '.md', '.rst', '.txt',
    '.sql', '.graphql', '.proto',
    '.dockerfile', '.tf', '.cfg', '.ini', '.conf',
}


# ============================================================
# Code Chunk Types
# ============================================================

@dataclass
class CodeChunk:
    """A chunk of code (function, class, etc.)"""
    chunk_id: str
    file_path: str
    chunk_type: str  # "function", "class", "method", "module", etc.
    name: str
    start_line: int
    end_line: int
    source_code: str
    docstring: str = ""
    signature: str = ""
    language: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CodeChunk":
        return cls(**d)


# ============================================================
# File Indexer
# ============================================================

class FileIndexer:
    """
    Scans project directories and indexes files.
    
    Features:
    - Recursive directory scanning
    - File type filtering
    - Directory tree building
    - Incremental indexing
    """

    def __init__(
        self,
        project_path: str,
        index_dir: Path = None,
        ignored_dirs: Set[str] = None,
        supported_extensions: Set[str] = None,
    ):
        self.project_path = Path(project_path).resolve()
        self.index_dir = index_dir or DEFAULT_INDEX_DIR
        self.ignored_dirs = ignored_dirs or IGNORED_DIRS
        self.supported_extensions = supported_extensions or SUPPORTED_EXTENSIONS
        
        if not self.project_path.exists():
            raise FileNotFoundError(f"Project path not found: {self.project_path}")
        
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._project_index_file = self.index_dir / f"{self._project_hash()}.json"

    def _project_hash(self) -> str:
        """Generate a hash for the project path."""
        return hashlib.md5(str(self.project_path).encode()).hexdigest()[:12]

    def should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        parts = path.parts
        for part in parts:
            if part in self.ignored_dirs:
                return True
            # Check for hidden files/dirs
            if part.startswith('.') and part not in {'.env', '.gitignore'}:
                return True
        return False

    def is_supported_file(self, path: Path) -> bool:
        """Check if file has supported extension."""
        return path.suffix.lower() in self.supported_extensions

    def get_file_info(self, path: Path) -> Dict[str, Any]:
        """Get file metadata."""
        stat = path.stat()
        return {
            'path': str(path.relative_to(self.project_path)),
            'abs_path': str(path),
            'size': stat.st_size,
            'modified_time': stat.st_mtime,
            'extension': path.suffix.lower(),
        }

    def iter_files(self) -> Iterator[Path]:
        """Iterate over all supported files in the project."""
        for root, dirs, filenames in os.walk(self.project_path):
            root_path = Path(root)
            
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith('.')]
            
            if self.should_ignore(root_path):
                continue
            
            for filename in filenames:
                file_path = root_path / filename
                
                if self.is_supported_file(file_path) and not self.should_ignore(file_path):
                    yield file_path

    def scan_project(self, incremental: bool = False) -> Dict[str, Any]:
        """
        Scan the project directory and generate index.
        
        Args:
            incremental: If True, only process changed files
            
        Returns:
            Dictionary containing project structure and file metadata
        """
        previous_index: Dict[str, Any] = {}
        if incremental and self._project_index_file.exists():
            try:
                previous_index = json.loads(self._project_index_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        previous_files = previous_index.get('files', {})
        
        files: Dict[str, Any] = {}
        total_size = 0
        file_count = 0
        
        for file_path in self.iter_files():
            file_info = self.get_file_info(file_path)
            rel_path = file_info['path']
            
            # For incremental, check if file changed
            if incremental:
                prev = previous_files.get(rel_path)
                if prev and prev['modified_time'] >= file_info['modified_time']:
                    files[rel_path] = prev
                    continue
            
            files[rel_path] = file_info
            total_size += file_info['size']
            file_count += 1

        index_data = {
            'project_path': str(self.project_path),
            'project_name': self.project_path.name,
            'scan_time': time.time(),
            'file_count': len(files),
            'total_size': total_size,
            'files': files,
        }

        # Save index
        self._project_index_file.write_text(
            json.dumps(index_data, indent=2, ensure_ascii=False)
        )
        
        return index_data

    def get_changed_files(self, since_timestamp: float) -> List[Dict[str, Any]]:
        """Get files modified since a specific timestamp."""
        changed = []
        for file_path in self.iter_files():
            stat = file_path.stat()
            if stat.st_mtime > since_timestamp:
                changed.append(self.get_file_info(file_path))
        return changed

    def get_directory_tree(self) -> Dict[str, Any]:
        """Build a directory tree structure."""
        tree: Dict[str, Any] = {'_root': str(self.project_path)}
        
        for file_path in self.iter_files():
            rel_path = file_path.relative_to(self.project_path)
            parts = rel_path.parts
            
            current = tree
            for i, part in enumerate(parts[:-1]):
                if part not in current:
                    current[part] = {'_is_dir': True, '_files': []}
                current = current[part]
            
            current['_files'].append(parts[-1])
        
        return tree


# ============================================================
# Code Chunker
# ============================================================

class CodeChunker:
    """
    Splits code files into logical chunks (functions, classes, etc.).
    
    Language-specific parsing for accurate chunk extraction.
    """

    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()

    def chunk_file(self, file_path: Path) -> List[CodeChunk]:
        """Chunk a single file into logical pieces."""
        file_path = Path(file_path)
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            return []
        
        ext = file_path.suffix.lower()
        
        # Route to language-specific chunker
        chunkers = {
            '.py': self._chunk_python,
            '.js': self._chunk_js_ts,
            '.ts': self._chunk_js_ts,
            '.jsx': self._chunk_js_ts,
            '.tsx': self._chunk_js_ts,
            '.vue': self._chunk_vue,
            '.go': self._chunk_go,
            '.rs': self._chunk_rust,
            '.java': self._chunk_java,
            '.rb': self._chunk_ruby,
        }
        
        chunker = chunkers.get(ext, self._chunk_generic)
        return chunker(file_path, content)

    def _chunk_python(self, file_path: Path, content: str) -> List[CodeChunk]:
        """Chunk Python file into functions, classes, methods."""
        chunks = []
        lines = content.split('\n')
        
        # Patterns for Python definitions
        class_pattern = re.compile(r'^class\s+(\w+).*?:')
        func_pattern = re.compile(r'^((?:async\s+)?def\s+(\w+).*?):')
        method_pattern = re.compile(r'^\s+((?:async\s+)?def\s+(\w+).*?):')
        
        current_class = None
        chunk_id_prefix = f"{file_path.stem}"
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check for class
            class_match = class_pattern.match(line.strip())
            if class_match:
                current_class = class_match.group(1)
                # Find class body (next class or dedent)
                start_line = i + 1
                end_line = self._find_python_block_end(lines, i + 1)
                
                class_content = '\n'.join(lines[start_line:end_line])
                docstring = self._extract_docstring(lines[i + 1:start_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{current_class}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="class",
                    name=current_class,
                    start_line=start_line,
                    end_line=end_line,
                    source_code=class_content,
                    docstring=docstring,
                    signature=line.strip(),
                    language="python",
                ))
                i = end_line
                continue
            
            # Check for function (not in class)
            func_match = func_pattern.match(line.strip())
            if func_match and current_class is None:
                name = func_match.group(2)
                start_line = i + 1
                end_line = self._find_python_block_end(lines, i + 1)
                
                func_content = '\n'.join(lines[start_line:end_line])
                docstring = self._extract_docstring(lines[i + 1:start_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{name}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="function",
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    source_code=func_content,
                    docstring=docstring,
                    signature=line.strip(),
                    language="python",
                ))
                i = end_line
                continue
            
            # Check for method (in class)
            method_match = method_pattern.match(line)
            if method_match and current_class:
                name = method_match.group(2)
                start_line = i + 1
                end_line = self._find_python_block_end(lines, i + 1)
                
                method_content = '\n'.join(lines[start_line:end_line])
                docstring = self._extract_docstring(lines[i + 1:start_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{current_class}.{name}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="method",
                    name=f"{current_class}.{name}",
                    start_line=start_line,
                    end_line=end_line,
                    source_code=method_content,
                    docstring=docstring,
                    signature=lines[i].strip(),
                    language="python",
                ))
                i = end_line
                continue
            
            i += 1
        
        # If no chunks found, create a module-level chunk
        if not chunks:
            chunks.append(CodeChunk(
                chunk_id=chunk_id_prefix,
                file_path=str(file_path.relative_to(self.project_path)),
                chunk_type="module",
                name=file_path.stem,
                start_line=1,
                end_line=len(lines),
                source_code=content[:5000],  # Limit size
                language="python",
            ))
        
        return chunks

    def _find_python_block_end(self, lines: List[str], start: int) -> int:
        """Find where a Python block ends (dedent)."""
        if start >= len(lines):
            return start
        
        # Get indent of first non-empty line
        first_indent = 0
        for i in range(start, min(start + 10, len(lines))):
            line = lines[i]
            if line.strip():
                first_indent = len(line) - len(line.lstrip())
                break
        
        # Find dedent
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if line.strip():
                indent = len(line) - len(line.lstrip())
                if indent <= first_indent:
                    return i
        
        return len(lines)

    def _extract_docstring(self, lines: List[str]) -> str:
        """Extract docstring from lines before a definition."""
        docstring_lines = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                    docstring_lines.append(stripped[3:-3])
                    break
            elif in_docstring:
                docstring_lines.append(stripped)
        return '\n'.join(docstring_lines).strip()

    def _chunk_js_ts(self, file_path: Path, content: str) -> List[CodeChunk]:
        """Chunk JavaScript/TypeScript files."""
        chunks = []
        lines = content.split('\n')
        
        # Patterns
        func_pattern = re.compile(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)|^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(')
        class_pattern = re.compile(r'^(?:export\s+)?class\s+(\w+)')
        
        chunk_id_prefix = f"{file_path.stem}"
        
        for i, line in enumerate(lines):
            # Function
            func_match = func_pattern.search(line)
            if func_match:
                name = func_match.group(1) or func_match.group(2)
                start_line = i + 1
                end_line = self._find_js_block_end(lines, i)
                
                func_content = '\n'.join(lines[i:end_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{name}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="function",
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    source_code=func_content,
                    language="javascript" if file_path.suffix == ".js" else "typescript",
                ))
            
            # Class
            class_match = class_pattern.match(line)
            if class_match:
                name = class_match.group(1)
                start_line = i + 1
                end_line = self._find_js_block_end(lines, i)
                
                class_content = '\n'.join(lines[i:end_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{name}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="class",
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    source_code=class_content,
                    language="javascript" if file_path.suffix == ".js" else "typescript",
                ))
        
        if not chunks:
            chunks.append(CodeChunk(
                chunk_id=chunk_id_prefix,
                file_path=str(file_path.relative_to(self.project_path)),
                chunk_type="module",
                name=file_path.stem,
                start_line=1,
                end_line=len(lines),
                source_code=content[:5000],
                language="javascript" if file_path.suffix == ".js" else "typescript",
            ))
        
        return chunks

    def _find_js_block_end(self, lines: List[str], start: int) -> int:
        """Find where a JS/TS block ends."""
        brace_count = 0
        started = False
        
        for i in range(start, len(lines)):
            for char in lines[i]:
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
            
            if started and brace_count <= 0:
                return i + 1
        
        return len(lines)

    def _chunk_vue(self, file_path: Path, content: str) -> List[CodeChunk]:
        """Chunk Vue SFC files."""
        chunks = []
        
        # Split by script, template, style sections
        script_match = re.search(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
        template_match = re.search(r'<template[^>]*>(.*?)</template>', content, re.DOTALL)
        style_match = re.search(r'<style[^>]*>(.*?)</style>', content, re.DOTALL)
        
        if script_match:
            chunks.append(CodeChunk(
                chunk_id=f"{file_path.stem}.script",
                file_path=str(file_path.relative_to(self.project_path)),
                chunk_type="script",
                name=f"{file_path.stem} script",
                start_line=content[:script_match.start()].count('\n') + 1,
                end_line=content[:script_match.end()].count('\n') + 1,
                source_code=script_match.group(1).strip(),
                language="javascript",
            ))
        
        if template_match:
            chunks.append(CodeChunk(
                chunk_id=f"{file_path.stem}.template",
                file_path=str(file_path.relative_to(self.project_path)),
                chunk_type="template",
                name=f"{file_path.stem} template",
                start_line=content[:template_match.start()].count('\n') + 1,
                end_line=content[:template_match.end()].count('\n') + 1,
                source_code=template_match.group(1).strip(),
                language="html",
            ))
        
        return chunks

    def _chunk_go(self, file_path: Path, content: str) -> List[CodeChunk]:
        """Chunk Go files."""
        chunks = []
        lines = content.split('\n')
        
        func_pattern = re.compile(r'^func\s+(\w+)\s*\(')
        
        chunk_id_prefix = f"{file_path.stem}"
        
        for i, line in enumerate(lines):
            func_match = func_pattern.match(line.strip())
            if func_match:
                name = func_match.group(1)
                start_line = i + 1
                end_line = self._find_go_block_end(lines, i)
                
                func_content = '\n'.join(lines[i:end_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{name}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="function",
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    source_code=func_content,
                    language="go",
                ))
        
        if not chunks:
            chunks.append(CodeChunk(
                chunk_id=chunk_id_prefix,
                file_path=str(file_path.relative_to(self.project_path)),
                chunk_type="module",
                name=file_path.stem,
                start_line=1,
                end_line=len(lines),
                source_code=content[:5000],
                language="go",
            ))
        
        return chunks

    def _find_go_block_end(self, lines: List[str], start: int) -> int:
        """Find where a Go block ends."""
        brace_count = 0
        
        for i in range(start, len(lines)):
            for char in lines[i]:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count <= 0:
                        return i + 1
        
        return len(lines)

    def _chunk_rust(self, file_path: Path, content: str) -> List[CodeChunk]:
        """Chunk Rust files."""
        chunks = []
        lines = content.split('\n')
        
        func_pattern = re.compile(r'^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)')
        struct_pattern = re.compile(r'^struct\s+(\w+)')
        impl_pattern = re.compile(r'^impl\s+(?:<[^>]+>\s+)?(\w+)')
        
        chunk_id_prefix = f"{file_path.stem}"
        
        for i, line in enumerate(lines):
            func_match = func_pattern.match(line.strip())
            if func_match:
                name = func_match.group(1)
                start_line = i + 1
                end_line = self._find_rust_block_end(lines, i)
                
                func_content = '\n'.join(lines[i:end_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{name}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="function",
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    source_code=func_content,
                    language="rust",
                ))
            
            struct_match = struct_pattern.match(line.strip())
            if struct_match:
                name = struct_match.group(1)
                start_line = i + 1
                end_line = self._find_rust_block_end(lines, i)
                
                struct_content = '\n'.join(lines[i:end_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{name}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="struct",
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    source_code=struct_content,
                    language="rust",
                ))
        
        if not chunks:
            chunks.append(CodeChunk(
                chunk_id=chunk_id_prefix,
                file_path=str(file_path.relative_to(self.project_path)),
                chunk_type="module",
                name=file_path.stem,
                start_line=1,
                end_line=len(lines),
                source_code=content[:5000],
                language="rust",
            ))
        
        return chunks

    def _find_rust_block_end(self, lines: List[str], start: int) -> int:
        """Find where a Rust block ends."""
        brace_count = 0
        
        for i in range(start, len(lines)):
            for char in lines[i]:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count <= 0:
                        return i + 1
        
        return len(lines)

    def _chunk_java(self, file_path: Path, content: str) -> List[CodeChunk]:
        """Chunk Java files."""
        chunks = []
        lines = content.split('\n')
        
        class_pattern = re.compile(r'^(?:public\s+)?class\s+(\w+)')
        method_pattern = re.compile(r'^(?:\s+)(?:public|private|protected)?\s*(?:static\s+)?(?:[\w<>[\],\s]+\s+)+(\w+)\s*\(')
        
        chunk_id_prefix = f"{file_path.stem}"
        current_class = None
        
        for i, line in enumerate(lines):
            class_match = class_pattern.match(line.strip())
            if class_match:
                current_class = class_match.group(1)
                end_line = self._find_java_block_end(lines, i)
                
                class_content = '\n'.join(lines[i:end_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{current_class}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="class",
                    name=current_class,
                    start_line=i + 1,
                    end_line=end_line,
                    source_code=class_content,
                    language="java",
                ))
            
            method_match = method_pattern.match(line)
            if method_match and current_class:
                name = method_match.group(1)
                end_line = self._find_java_block_end(lines, i)
                
                method_content = '\n'.join(lines[i:end_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{current_class}.{name}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="method",
                    name=f"{current_class}.{name}",
                    start_line=i + 1,
                    end_line=end_line,
                    source_code=method_content,
                    language="java",
                ))
        
        if not chunks:
            chunks.append(CodeChunk(
                chunk_id=chunk_id_prefix,
                file_path=str(file_path.relative_to(self.project_path)),
                chunk_type="file",
                name=file_path.stem,
                start_line=1,
                end_line=len(lines),
                source_code=content[:5000],
                language="java",
            ))
        
        return chunks

    def _find_java_block_end(self, lines: List[str], start: int) -> int:
        """Find where a Java block ends."""
        brace_count = 0
        
        for i in range(start, len(lines)):
            for char in lines[i]:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count <= 0:
                        return i + 1
        
        return len(lines)

    def _chunk_ruby(self, file_path: Path, content: str) -> List[CodeChunk]:
        """Chunk Ruby files."""
        chunks = []
        lines = content.split('\n')
        
        def_pattern = re.compile(r'^def\s+(\w+|[\w:]+)')
        class_pattern = re.compile(r'^class\s+(\w+)')
        
        chunk_id_prefix = f"{file_path.stem}"
        
        for i, line in enumerate(lines):
            def_match = def_pattern.match(line.strip())
            if def_match:
                name = def_match.group(1)
                end_line = self._find_ruby_block_end(lines, i)
                
                def_content = '\n'.join(lines[i:end_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{name.replace(':', '_')}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="method",
                    name=name,
                    start_line=i + 1,
                    end_line=end_line,
                    source_code=def_content,
                    language="ruby",
                ))
            
            class_match = class_pattern.match(line.strip())
            if class_match:
                name = class_match.group(1)
                end_line = self._find_ruby_block_end(lines, i)
                
                class_content = '\n'.join(lines[i:end_line])
                
                chunks.append(CodeChunk(
                    chunk_id=f"{chunk_id_prefix}.{name}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="class",
                    name=name,
                    start_line=i + 1,
                    end_line=end_line,
                    source_code=class_content,
                    language="ruby",
                ))
        
        if not chunks:
            chunks.append(CodeChunk(
                chunk_id=chunk_id_prefix,
                file_path=str(file_path.relative_to(self.project_path)),
                chunk_type="file",
                name=file_path.stem,
                start_line=1,
                end_line=len(lines),
                source_code=content[:5000],
                language="ruby",
            ))
        
        return chunks

    def _find_ruby_block_end(self, lines: List[str], start: int) -> int:
        """Find where a Ruby block ends (end keyword)."""
        depth = 0
        for i in range(start, len(lines)):
            line = lines[i].strip()
            if line == 'end':
                if depth == 0:
                    return i + 1
                depth -= 1
            elif 'end' in line:
                depth += 1
        return len(lines)

    def _chunk_generic(self, file_path: Path, content: str) -> List[CodeChunk]:
        """Generic chunker for unsupported languages."""
        lines = content.split('\n')
        chunks = []
        
        # Try to split by obvious boundaries (empty lines, headers, etc.)
        if len(lines) > 100:
            # Split into chunks of ~100 lines
            for i in range(0, len(lines), 100):
                chunk_lines = lines[i:i + 100]
                chunks.append(CodeChunk(
                    chunk_id=f"{file_path.stem}.chunk{i // 100}",
                    file_path=str(file_path.relative_to(self.project_path)),
                    chunk_type="block",
                    name=f"{file_path.stem}[{i // 100}]",
                    start_line=i + 1,
                    end_line=min(i + 100, len(lines)),
                    source_code='\n'.join(chunk_lines),
                    language=file_path.suffix.lstrip('.'),
                ))
        else:
            chunks.append(CodeChunk(
                chunk_id=file_path.stem,
                file_path=str(file_path.relative_to(self.project_path)),
                chunk_type="file",
                name=file_path.stem,
                start_line=1,
                end_line=len(lines),
                source_code=content[:5000],
                language=file_path.suffix.lstrip('.'),
            ))
        
        return chunks


# ============================================================
# Codebase Index
# ============================================================

class CodebaseIndex:
    """
    Main indexer that combines file scanning and chunking.
    
    Usage:
        index = CodebaseIndex("/path/to/project")
        index.scan()
        
        # Get project info
        info = index.get_info()
        print(f"Indexed {info['chunk_count']} chunks from {info['file_count']} files")
    """

    def __init__(
        self,
        project_path: str,
        index_dir: Path = None,
        embedder_model: str = "all-MiniLM-L6-v2",
    ):
        self.project_path = Path(project_path).resolve()
        self.index_dir = index_dir or DEFAULT_INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        self.file_indexer = FileIndexer(project_path, index_dir)
        self.chunker = CodeChunker(project_path)
        
        self._chunks: Dict[str, CodeChunk] = {}
        self._embeddings: Dict[str, List[float]] = {}
        self._project_info: Dict[str, Any] = {}
        
        # Try to load existing index
        self._load_index()

    def _chunk_db_path(self) -> Path:
        """Get path to chunk database."""
        return self.index_dir / f"{self.file_indexer._project_hash()}_chunks.json"

    def _load_index(self):
        """Load existing index from disk."""
        chunk_db = self._chunk_db_path()
        if chunk_db.exists():
            try:
                data = json.loads(chunk_db.read_text())
                self._chunks = {c['chunk_id']: CodeChunk.from_dict(c) for c in data.get('chunks', [])}
                self._embeddings = data.get('embeddings', {})
                self._project_info = data.get('info', {})
            except (json.JSONDecodeError, OSError):
                pass

    def _save_index(self):
        """Save index to disk."""
        chunk_db = self._chunk_db_path()
        data = {
            'chunks': [c.to_dict() for c in self._chunks.values()],
            'embeddings': self._embeddings,
            'info': self._project_info,
        }
        chunk_db.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def scan(self, incremental: bool = True) -> Dict[str, Any]:
        """
        Scan and index the project.
        
        Args:
            incremental: If True, only re-index changed files
            
        Returns:
            Project index info
        """
        # Scan files
        file_data = self.file_indexer.scan_project(incremental=incremental)
        
        # Get existing chunks for incremental
        existing_file_chunks: Dict[str, Set[str]] = {}
        if incremental:
            for chunk_id, chunk in self._chunks.items():
                existing_file_chunks.setdefault(chunk.file_path, set()).add(chunk_id)
        
        # Chunk all files
        new_chunks: Dict[str, CodeChunk] = {}
        
        for file_path in self.file_indexer.iter_files():
            rel_path = str(file_path.relative_to(self.project_path))
            
            # For incremental, check if we need to re-chunk
            if incremental and rel_path in existing_file_chunks:
                # Check if file was modified
                file_info = file_data['files'].get(rel_path, {})
                if not file_info:
                    continue
                
                # Re-chunk to get new chunk IDs
                file_chunks = self.chunker.chunk_file(file_path)
                for chunk in file_chunks:
                    new_chunks[chunk.chunk_id] = chunk
            else:
                file_chunks = self.chunker.chunk_file(file_path)
                for chunk in file_chunks:
                    new_chunks[chunk.chunk_id] = chunk
        
        self._chunks = new_chunks
        
        # Build project info
        self._project_info = {
            'project_path': str(self.project_path),
            'project_name': self.project_path.name,
            'scan_time': time.time(),
            'file_count': file_data['file_count'],
            'chunk_count': len(self._chunks),
            'languages': self._get_languages(),
        }
        
        self._save_index()
        
        return self._project_info

    def _get_languages(self) -> Dict[str, int]:
        """Get language distribution."""
        langs: Dict[str, int] = {}
        for chunk in self._chunks.values():
            langs[chunk.language] = langs.get(chunk.language, 0) + 1
        return langs

    def get_info(self) -> Dict[str, Any]:
        """Get project info."""
        return self._project_info

    def get_chunks(self, file_path: str = None, chunk_type: str = None) -> List[CodeChunk]:
        """Get chunks, optionally filtered."""
        chunks = list(self._chunks.values())
        
        if file_path:
            chunks = [c for c in chunks if c.file_path == file_path]
        
        if chunk_type:
            chunks = [c for c in chunks if c.chunk_type == chunk_type]
        
        return chunks

    def get_chunk(self, chunk_id: str) -> Optional[CodeChunk]:
        """Get a specific chunk."""
        return self._chunks.get(chunk_id)

    def iterate_chunks(self) -> Iterator[CodeChunk]:
        """Iterate over all chunks."""
        return iter(self._chunks.values())

    def clear(self):
        """Clear the index."""
        self._chunks = {}
        self._embeddings = {}
        self._project_info = {}
        
        chunk_db = self._chunk_db_path()
        if chunk_db.exists():
            chunk_db.unlink()
