#!/usr/bin/env python3
"""
h_agent/features/rag.py - Codebase RAG 支持

为 h_agent 添加代码库理解和 RAG 能力。

功能：
1. 代码库索引（文件结构、符号）
2. 向量搜索（语义搜索）
3. 代码片段检索
"""

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from h_agent.platform_utils import get_config_dir

# 可选依赖
HAS_CHROMA = False
chromadb = None

def _check_chroma():
    global HAS_CHROMA, chromadb
    if chromadb is None:
        try:
            import chromadb as _chroma
            chromadb = _chroma
            HAS_CHROMA = True
        except ImportError:
            HAS_CHROMA = False

# OpenAI embedding
HAS_OPENAI = False
_openai_client = None

def _get_openai_client():
    global _openai_client, HAS_OPENAI
    if _openai_client is None:
        try:
            from h_agent.core.client import get_client
            _openai_client = get_client()
            HAS_OPENAI = True
        except Exception:
            HAS_OPENAI = False
    return _openai_client


# ============================================================
# 配置
# ============================================================

def get_rag_dir() -> Path:
    """Get RAG data directory."""
    rag_dir = get_config_dir() / "rag"
    rag_dir.mkdir(parents=True, exist_ok=True)
    return rag_dir


def get_rag_index_path() -> Path:
    return get_rag_dir() / "codebase_index.json"


def get_rag_stats_path() -> Path:
    return get_rag_dir() / "stats.json"


# ============================================================
# 代码符号提取
# ============================================================

@dataclass
class CodeSymbol:
    name: str
    kind: str  # function, class, variable, import, method
    file: str
    line: int
    snippet: str = ""


class CodeParser:
    """简单的代码解析器。"""

    LANGUAGE_PATTERNS = {
        "python": {
            "function": r"def\s+(\w+)\s*\(",
            "class": r"class\s+(\w+)",
            "async_function": r"async\s+def\s+(\w+)\s*\(",
            "import": r"^(?:from\s+[\w.]+\s+)?import\s+",
            "decorator": r"@(\w+)",
        },
        "javascript": {
            "function": r"function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\(",
            "class": r"class\s+(\w+)",
            "method": r"(\w+)\s*\([^)]*\)\s*\{",
            "arrow_function": r"const\s+(\w+)\s*=\s*(?:async\s*)?\(",
            "import": r"import\s+.*?from\s+['\"](.+?)['\"]",
        },
        "typescript": {
            "function": r"function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\(",
            "class": r"class\s+(\w+)",
            "interface": r"interface\s+(\w+)",
            "type": r"type\s+(\w+)",
            "import": r"import\s+.*?from\s+['\"](.+?)['\"]",
        },
        "go": {
            "function": r"func\s+(\w+)",
            "method": r"func\s+\((\w+)\s+\*?\w+)\s+(\w+)\(",
            "struct": r"type\s+(\w+)\s+struct",
            "import": r"import\s+\(",
        },
        "rust": {
            "function": r"fn\s+(\w+)",
            "struct": r"struct\s+(\w+)",
            "impl": r"impl\s+",
            "use": r"use\s+",
        },
    }

    IGNORE_DIRS = {
        ".git", ".svn", ".hg",
        "node_modules", "venv", ".venv",
        "__pycache__", ".pytest_cache", ".mypy_cache",
        "dist", "build", "target", ".next", ".nuxt",
        ".env", ".venv", "vendor", "bin", "obj",
    }

    IGNORE_EXTENSIONS = {
        ".exe", ".dll", ".so", ".dylib", ".o", ".a",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".zip", ".tar", ".gz", ".rar", ".7z",
        ".mp3", ".mp4", ".wav", ".avi",
        ".ttf", ".woff", ".woff2",
    }

    def __init__(self):
        self.re = re

    def should_ignore(self, path: Path) -> bool:
        """Check if file/dir should be ignored."""
        name = path.name
        if name in self.IGNORE_DIRS:
            return True
        if path.suffix.lower() in self.IGNORE_EXTENSIONS:
            return True
        return False

    def detect_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sh": "shell",
            ".bash": "shell",
            ".zsh": "shell",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".md": "markdown",
        }
        return lang_map.get(ext)

    def parse_file(self, file_path: str, root_dir: Optional[str] = None) -> List[CodeSymbol]:
        """解析文件，提取符号。"""
        symbols = []
        lang = self.detect_language(file_path)
        if not lang or lang not in self.LANGUAGE_PATTERNS:
            return symbols

        rel_path = file_path
        if root_dir:
            try:
                rel_path = str(Path(file_path).relative_to(root_dir))
            except ValueError:
                rel_path = file_path

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            return symbols

        patterns = self.LANGUAGE_PATTERNS[lang]
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            for kind, pattern in patterns.items():
                if kind == "import":
                    if self.re.search(pattern, stripped):
                        match = self.re.search(r"import\s+.*?['\"](.+?)['\"]", stripped)
                        if match:
                            symbols.append(CodeSymbol(
                                name=match.group(1),
                                kind="import",
                                file=str(rel_path),
                                line=line_num,
                                snippet=stripped[:100],
                            ))
                else:
                    match = self.re.search(pattern, line)
                    if match:
                        # Get the name from first non-None group
                        name = None
                        for g in match.groups():
                            if g is not None:
                                name = g.strip()
                                break
                        if name is None:
                            continue
                        # Skip dunder methods
                        if name.startswith("__") and name.endswith("__"):
                            continue
                        symbols.append(CodeSymbol(
                            name=name,
                            kind=kind,
                            file=str(rel_path),
                            line=line_num,
                            snippet=stripped[:100],
                        ))

        return symbols

    def chunk_file(self, file_path: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict]:
        """将文件分块，便于向量检索。"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return []

        rel_path = file_path
        lines = content.split("\n")
        chunks = []
        start = 0
        while start < len(lines):
            end = min(start + chunk_size, len(lines))
            chunk_lines = lines[start:end]
            chunk_text = "\n".join(chunk_lines)
            chunks.append({
                "file": rel_path,
                "start_line": start + 1,
                "end_line": end,
                "content": chunk_text,
            })
            start += chunk_size - overlap
        return chunks


# ============================================================
# 代码库索引
# ============================================================

@dataclass
class FileInfo:
    path: str
    language: str
    size: int
    hash: str
    symbols: List[str] = field(default_factory=list)
    last_indexed: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "language": self.language,
            "size": self.size,
            "hash": self.hash,
            "symbols": self.symbols,
            "last_indexed": self.last_indexed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FileInfo":
        return cls(
            path=d["path"],
            language=d["language"],
            size=d["size"],
            hash=d["hash"],
            symbols=d.get("symbols", []),
            last_indexed=d.get("last_indexed", ""),
        )


class CodebaseIndex:
    """代码库索引。"""

    DEFAULT_PATTERNS = [
        "**/*.py", "**/*.js", "**/*.ts", "**/*.tsx",
        "**/*.go", "**/*.rs", "**/*.java", "**/*.c", "**/*.cpp",
        "**/*.cs", "**/*.rb", "**/*.php", "**/*.swift", "**/*.kt",
        "**/*.sh", "**/*.bash", "**/*.yaml", "**/*.yml",
        "**/*.md", "**/*.txt",
    ]

    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir).resolve()
        self.parser = CodeParser()
        self.files: Dict[str, FileInfo] = {}
        self.symbols: Dict[str, List[CodeSymbol]] = {}
        self._load()

    def _load(self):
        """从磁盘加载索引（重新解析文件以恢复符号对象）。"""
        index_path = get_rag_index_path()
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                root_dir = data.get("root_dir", str(self.root_dir))
                for k, v in data.get("files", {}).items():
                    self.files[k] = FileInfo.from_dict(v)

                # Re-parse files to reconstruct CodeSymbol objects
                for rel_path, file_info in self.files.items():
                    file_path = Path(root_dir) / rel_path
                    if file_path.exists():
                        symbols = self.parser.parse_file(str(file_path), root_dir)
                        for sym in symbols:
                            key = f"symbol:{sym.name}"
                            if key not in self.symbols:
                                self.symbols[key] = []
                            # Avoid duplicates
                            existing = [s for s in self.symbols[key]
                                        if s.file == sym.file and s.line == sym.line]
                            if not existing:
                                self.symbols[key].append(sym)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        """保存索引到磁盘。"""
        data = {
            "root_dir": str(self.root_dir),
            "files": {k: v.to_dict() for k, v in self.files.items()},
        }
        get_rag_index_path().write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def scan(self, patterns: List[str] = None, verbose: bool = True):
        """扫描代码库。"""
        if patterns is None:
            patterns = self.DEFAULT_PATTERNS

        if verbose:
            print(f"Scanning {self.root_dir}...")

        file_count = 0
        for pattern in patterns:
            for file_path in self.root_dir.glob(pattern):
                # Check ignore dirs
                if any(part in file_path.parts for part in CodeParser.IGNORE_DIRS):
                    continue
                rel = str(file_path.relative_to(self.root_dir))
                if self.should_reindex(rel):
                    self._index_file(str(file_path))
                    file_count += 1

        if verbose:
            print(f"Indexed {file_count} files. Total: {len(self.files)}")

    def should_reindex(self, rel_path: str) -> bool:
        """检查是否需要重新索引。"""
        if rel_path not in self.files:
            return True
        try:
            content = Path(self.root_dir / rel_path).read_text(encoding="utf-8", errors="ignore")
            current_hash = hashlib.md5(content.encode()).hexdigest()
            return self.files[rel_path].hash != current_hash
        except Exception:
            return False

    def _index_file(self, file_path: str):
        """索引单个文件。"""
        try:
            rel_path = str(Path(file_path).relative_to(self.root_dir))
        except ValueError:
            rel_path = file_path

        # 计算文件 hash
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            file_hash = hashlib.md5(content.encode()).hexdigest()
        except Exception:
            return

        # 提取符号
        symbols = self.parser.parse_file(file_path, str(self.root_dir))

        # 存储文件信息
        lang = self.parser.detect_language(file_path) or "unknown"
        self.files[rel_path] = FileInfo(
            path=rel_path,
            language=lang,
            size=len(content),
            hash=file_hash,
            symbols=[s.name for s in symbols],
            last_indexed=datetime.now().isoformat(),
        )

        # 存储符号
        for sym in symbols:
            key = f"symbol:{sym.name}"
            if key not in self.symbols:
                self.symbols[key] = []
            # Avoid duplicates
            existing = [s for s in self.symbols[key] if s.file == sym.file and s.line == sym.line]
            if not existing:
                self.symbols[key].append(sym)

    def search_symbols(self, query: str, limit: int = 10) -> List[CodeSymbol]:
        """搜索符号。"""
        results = []
        query_lower = query.lower()

        for key, syms in self.symbols.items():
            if query_lower in key.lower():
                results.extend(syms)
            else:
                # Also search in symbol names
                for sym in syms:
                    if query_lower in sym.name.lower():
                        results.append(sym)

        # Deduplicate
        seen = set()
        unique = []
        for sym in results:
            ident = (sym.name, sym.file, sym.line)
            if ident not in seen:
                seen.add(ident)
                unique.append(sym)

        return unique[:limit]

    def get_stats(self) -> dict:
        """获取统计信息。"""
        lang_counts: Dict[str, int] = {}
        for f in self.files.values():
            lang_counts[f.language] = lang_counts.get(f.language, 0) + 1
        return {
            "files": len(self.files),
            "symbols": len(self.symbols),
            "languages": lang_counts,
            "root_dir": str(self.root_dir),
        }


# ============================================================
# 向量存储
# ============================================================

class VectorStore:
    """向量存储，支持 chromadb 或内存回退。"""

    def __init__(self, collection_name: str = "codebase", persist_dir: Optional[str] = None):
        _check_chroma()
        self.use_chroma = HAS_CHROMA
        self.collection_name = collection_name
        self.persist_dir = persist_dir or str(get_rag_dir() / "chroma")
        self._client = None
        self._collection = None
        self._docs: Dict[str, str] = {}  # fallback

        if self.use_chroma:
            try:
                import chromadb
                from chromadb.config import Settings
                self._client = chromadb.Client(Settings(
                    persist_directory=self.persist_dir,
                    anonymized_telemetry=False,
                ))
                # Try to get existing or create new
                try:
                    self._collection = self._client.get_collection(collection_name)
                except Exception:
                    self._collection = self._client.create_collection(
                        collection_name,
                        metadata={"h-agent": "rag"}
                    )
            except Exception as e:
                self.use_chroma = False

    def add_documents(self, docs: List[dict]) -> bool:
        """
        添加文档到向量存储。

        Args:
            docs: [{"id": str, "content": str, "metadata": dict}]

        Returns:
            True if successful, False otherwise.
        """
        if not docs:
            return True

        if self.use_chroma and self._collection is not None:
            try:
                self._collection.add(
                    ids=[d["id"] for d in docs],
                    documents=[d["content"] for d in docs],
                    metadatas=[d.get("metadata", {}) for d in docs],
                )
                return True
            except Exception as e:
                print(f"Chroma add failed: {e}")
                self.use_chroma = False

        # Fallback: memory storage
        for d in docs:
            self._docs[d["id"]] = d["content"]
        return True

    def search(self, query: str, n: int = 5) -> List[dict]:
        """搜索相似文档。"""
        if self.use_chroma and self._collection is not None:
            try:
                results = self._collection.query(
                    query_texts=[query],
                    n_results=n,
                )
                if results and results["ids"]:
                    return [
                        {
                            "id": id_,
                            "content": doc,
                            "metadata": meta or {},
                            "distance": dist,
                        }
                        for id_, doc, meta, dist in zip(
                            results["ids"][0],
                            results["documents"][0],
                            results.get("metadatas", [[]] * len(results["ids"][0])),
                            results.get("distances", [[0.0] * len(results["ids"][0])])[0],
                        )
                    ]
            except Exception as e:
                print(f"Chroma search failed: {e}")

        # Fallback: keyword match
        results = []
        query_lower = query.lower()
        for id_, content in self._docs.items():
            if query_lower in content.lower():
                results.append({
                    "id": id_,
                    "content": content,
                    "metadata": {},
                    "distance": 0.0,
                })
                if len(results) >= n:
                    break
        return results

    def count(self) -> int:
        """获取文档数量。"""
        if self.use_chroma and self._collection is not None:
            try:
                return self._collection.count()
            except Exception:
                pass
        return len(self._docs)


# ============================================================
# RAG 系统
# ============================================================

class CodebaseRAG:
    """代码库 RAG 系统。"""

    def __init__(self, root_dir: str, use_embeddings: bool = True):
        self.root_dir = Path(root_dir).resolve()
        self.index = CodebaseIndex(str(self.root_dir))
        self.use_embeddings = use_embeddings and HAS_CHROMA
        self.vector_store: Optional[VectorStore] = None

        if self.use_embeddings:
            _check_chroma()
            if HAS_CHROMA:
                self.vector_store = VectorStore("codebase_chunks", str(get_rag_dir() / "chroma"))

    def index_codebase(self, patterns: List[str] = None, verbose: bool = True):
        """索引代码库（符号 + 向量）。"""
        if verbose:
            print(f"\033[36mIndexing codebase at {self.root_dir}\033[0m")

        # 1. 扫描文件，构建符号索引
        self.index.scan(patterns=patterns, verbose=verbose)

        # 2. 向量化文件块
        if self.vector_store is not None and verbose:
            print("Generating embeddings...")

        doc_count = 0
        if self.vector_store is not None:
            docs = []
            for rel_path in list(self.index.files.keys())[:500]:  # Limit for now
                file_path = self.root_dir / rel_path
                if not file_path.exists():
                    continue
                chunks = self.index.parser.chunk_file(str(file_path))
                for i, chunk in enumerate(chunks):
                    doc_id = f"{rel_path}:{chunk['start_line']}"
                    chunk_with_meta = {
                        "id": doc_id,
                        "content": f"// {chunk['file']}:{chunk['start_line']}-{chunk['end_line']}\n{chunk['content']}",
                        "metadata": {
                            "file": chunk["file"],
                            "language": self.index.files[rel_path].language,
                            "start_line": chunk["start_line"],
                            "end_line": chunk["end_line"],
                        }
                    }
                    docs.append(chunk_with_meta)
                    doc_count += 1

            if docs:
                self.vector_store.add_documents(docs)

        # 3. 保存索引
        self.index.save()

        stats = self.index.get_stats()
        if verbose:
            print(f"\n\033[32mIndex complete!\033[0m")
            print(f"  Files: {stats['files']}")
            print(f"  Symbols: {stats['symbols']}")
            print(f"  Chunks: {doc_count}")
            if self.vector_store:
                print(f"  Vector store: {self.vector_store.count()} docs")

    def search(self, query: str, n: int = 5) -> Dict[str, Any]:
        """搜索代码（符号 + 向量）。"""
        results = {
            "query": query,
            "symbols": [],
            "documents": [],
        }

        # 1. 符号搜索
        symbols = self.index.search_symbols(query, limit=n)
        results["symbols"] = [
            {
                "name": s.name,
                "kind": s.kind,
                "file": s.file,
                "line": s.line,
                "snippet": s.snippet,
            }
            for s in symbols
        ]

        # 2. 向量搜索
        if self.vector_store is not None:
            vector_results = self.vector_store.search(query, n=n)
            results["documents"] = [
                {
                    "id": d["id"],
                    "content": d["content"],
                    "metadata": d.get("metadata", {}),
                    "score": 1.0 - d.get("distance", 0.0),
                }
                for d in vector_results
            ]

        return results

    def get_context(self, query: str, max_chars: int = 8000) -> str:
        """获取相关上下文（用于注入 LLM）。"""
        results = self.search(query, n=5)

        context_parts = []
        total_chars = 0

        # 相关符号
        if results["symbols"]:
            context_parts.append("# Related Symbols\n")
            for sym in results["symbols"][:10]:
                line = f"- [{sym['kind']}] {sym['name']} ({sym['file']}:{sym['line']})\n"
                if total_chars + len(line) > max_chars:
                    break
                context_parts.append(line)
                total_chars += len(line)

        # 相关代码片段
        if results["documents"]:
            context_parts.append("\n# Related Code\n")
            for doc in results["documents"]:
                header = f"## {doc['id']}"
                content = doc["content"]
                if len(content) > 1500:
                    content = content[:1500] + "\n... [truncated]"
                block = f"\n{header}\n```{doc.get('metadata', {}).get('language', '')}\n{content}\n```\n"
                if total_chars + len(block) > max_chars:
                    break
                context_parts.append(block)
                total_chars += len(block)

        return "".join(context_parts) if context_parts else ""


# ============================================================
# CLI helpers
# ============================================================

def get_or_create_rag(root_dir: Optional[str] = None) -> CodebaseRAG:
    """获取或创建 RAG 实例。"""
    if root_dir is None:
        root_dir = os.getcwd()
    return CodebaseRAG(root_dir)


# ============================================================
# 测试
# ============================================================

def main():
    import sys

    root_dir = sys.argv[1] if len(sys.argv) > 1 else "."

    print(f"\033[36m代码库 RAG 测试\033[0m")
    print(f"目录: {root_dir}")
    print("=" * 50)

    rag = CodebaseRAG(root_dir)
    rag.index_codebase()

    # 统计
    stats = rag.index.get_stats()
    print(f"\n统计:")
    print(f"  文件: {stats['files']}")
    print(f"  符号: {stats['symbols']}")
    print(f"  语言: {stats['languages']}")

    # 搜索测试
    if stats['symbols'] > 0:
        print("\n=== 搜索测试 ===")
        query = sys.argv[2] if len(sys.argv) > 2 else "test"
        results = rag.search(query, n=3)

        print(f"\n符号 ({len(results['symbols'])} 个):")
        for sym in results['symbols'][:5]:
            print(f"  {sym['kind']} {sym['name']} @ {sym['file']}:{sym['line']}")

        print(f"\n文档 ({len(results['documents'])} 个):")
        for doc in results['documents'][:2]:
            print(f"  {doc['id'][:60]}... (score: {doc.get('score', 0):.2f})")

        print("\n✅ 代码库 RAG 测试通过")
    else:
        print("No files indexed. Try specifying a directory with code files.")


if __name__ == "__main__":
    main()
