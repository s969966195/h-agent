#!/usr/bin/env python3
"""
h_agent/codebase/context.py - Context Generation for Development Tasks

Generates comprehensive context for development tasks by combining
project structure, relevant code, and cross-project patterns.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field, asdict

from h_agent.codebase.indexer import CodebaseIndex, CodeChunk, DEFAULT_INDEX_DIR
from h_agent.codebase.search import CodeSearch, SearchResult


# ============================================================
# Context Types
# ============================================================

@dataclass
class FileContext:
    """Context about a file in the project."""
    path: str
    language: str
    chunk_count: int = 0
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PatternGroup:
    """A group of similar code patterns across files."""
    pattern_id: str
    pattern_type: str  # "class", "function", "api", etc.
    similarity_score: float
    chunk_ids: List[str]
    file_paths: List[str]
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DevelopmentContext:
    """Complete context for a development task."""
    task_description: str
    project_name: str
    project_path: str
    file_count: int
    chunk_count: int
    relevant_files: List[FileContext]
    relevant_code: List[SearchResult]
    patterns: List[PatternGroup]
    generated_at: str = ""
    
    # Statistics
    languages_used: Dict[str, int] = field(default_factory=dict)
    total_lines: int = 0
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d['relevant_code'] = [r.to_dict() for r in d['relevant_code']]
        return d

    def to_markdown(self) -> str:
        """Format context as Markdown for easy reading."""
        lines = [
            f"# Development Context: {self.task_description}",
            "",
            f"**Project:** {self.project_name}",
            f"**Path:** {self.project_path}",
            "",
            "## Project Overview",
            f"- Files: {self.file_count}",
            f"- Code chunks: {self.chunk_count}",
            f"- Total lines: {self.total_lines:,}",
            "",
            "### Languages",
        ]
        
        for lang, count in sorted(self.languages_used.items(), key=lambda x: -x[1]):
            lines.append(f"- {lang}: {count} chunks")
        
        if self.relevant_files:
            lines.extend([
                "",
                "## Relevant Files",
            ])
            for fc in self.relevant_files[:10]:
                lines.append(f"- `{fc.path}` ({fc.language}) - {fc.description}")
        
        if self.relevant_code:
            lines.extend([
                "",
                "## Relevant Code",
            ])
            for i, result in enumerate(self.relevant_code, 1):
                lines.extend([
                    f"",
                    f"### {i}. {result.name} ({result.chunk_type})",
                    f"**File:** `{result.file_path}` (lines {result.start_line}-{result.end_line})",
                    f"**Similarity:** {result.similarity:.2%}",
                    "",
                    "```" + (result.chunk.language or ""),
                    result.source_code[:500] + ("..." if len(result.source_code) > 500 else ""),
                    "```",
                ])
        
        if self.patterns:
            lines.extend([
                "",
                "## Cross-Project Patterns",
            ])
            for pattern in self.patterns:
                lines.extend([
                    f"",
                    f"### {pattern.pattern_type}: {pattern.pattern_id}",
                    f"**Similarity:** {pattern.similarity_score:.2%}",
                    f"**Files:** {', '.join(pattern.file_paths[:5])}",
                    f"",
                    pattern.description,
                ])
        
        lines.extend([
            "",
            "---",
            f"*Generated at {self.generated_at}*",
        ])
        
        return '\n'.join(lines)


# ============================================================
# Context Generator
# ============================================================

class ContextGenerator:
    """
    Generates development context for tasks.
    
    Usage:
        generator = ContextGenerator()
        
        # Generate context for a task
        ctx = generator.generate_context(
            project_path="/path/to/project",
            task="add user profile editing",
            top_k=5,
        )
        
        # Format as markdown for LLM
        print(ctx.to_markdown())
        
        # Get as dict for API
        print(ctx.to_dict())
    """

    def __init__(
        self,
        index_dir: Path = None,
        embedder_model: str = "all-MiniLM-L6-v2",
    ):
        self.index_dir = index_dir or DEFAULT_INDEX_DIR
        self.search = CodeSearch(index_dir, embedder_model)

    def generate_context(
        self,
        project_path: str,
        task: str,
        top_k: int = 5,
        min_similarity: float = 0.3,
        include_patterns: bool = True,
        patterns_only_same_project: bool = False,
        chunk_limit: int = 500,
    ) -> DevelopmentContext:
        """
        Generate comprehensive context for a development task.
        
        Args:
            project_path: Path to the project
            task: Natural language description of the task
            top_k: Number of relevant code chunks to include
            min_similarity: Minimum similarity for code search
            include_patterns: Whether to detect cross-project patterns
            patterns_only_same_project: If True, only find patterns within project
            chunk_limit: Maximum lines of code per chunk to include
        
        Returns:
            DevelopmentContext with all relevant information
        """
        import time
        
        # Ensure project is indexed
        index_info = self.search.index_project(project_path, incremental=True)
        
        # Load index
        index = self.search._load_index(project_path)
        if not index:
            raise ValueError(f"Could not load index for {project_path}")
        
        # Search for relevant code
        relevant_code = self.search.search(
            query=task,
            project_path=project_path,
            top_k=top_k,
            min_similarity=min_similarity,
        )
        
        # Collect relevant files
        relevant_files_map: Dict[str, FileContext] = {}
        languages_used: Dict[str, int] = {}
        total_lines = 0
        
        for result in relevant_code:
            path = result.file_path
            if path not in relevant_files_map:
                # Get file info from index
                chunks = index.get_chunks(file_path=path)
                
                # Detect language from extension
                ext = Path(path).suffix.lstrip('.')
                lang_map = {
                    'py': 'python', 'js': 'javascript', 'ts': 'typescript',
                    'jsx': 'javascript', 'tsx': 'typescript', 'vue': 'vue',
                    'go': 'go', 'rs': 'rust', 'java': 'java', 'rb': 'ruby',
                }
                lang = lang_map.get(ext, ext)
                
                relevant_files_map[path] = FileContext(
                    path=path,
                    language=lang,
                    chunk_count=len(chunks),
                    description=self._describe_file(chunks),
                )
                
                languages_used[lang] = languages_used.get(lang, 0) + 1
            
            total_lines += (result.end_line - result.start_line)
        
        relevant_files = list(relevant_files_map.values())
        
        # Find patterns
        patterns: List[PatternGroup] = []
        if include_patterns:
            patterns = self._find_patterns(
                relevant_code,
                project_path if not patterns_only_same_project else None,
            )
        
        return DevelopmentContext(
            task_description=task,
            project_name=index_info.get('project_name', Path(project_path).name),
            project_path=project_path,
            file_count=index_info.get('file_count', 0),
            chunk_count=index_info.get('chunk_count', 0),
            relevant_files=relevant_files,
            relevant_code=relevant_code,
            patterns=patterns,
            generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            languages_used=languages_used,
            total_lines=total_lines,
        )

    def _describe_file(self, chunks: List[CodeChunk]) -> str:
        """Generate a description for a file based on its chunks."""
        if not chunks:
            return "Empty file"
        
        chunk_types: Dict[str, int] = {}
        names: List[str] = []
        
        for chunk in chunks[:10]:  # Look at first 10 chunks
            chunk_types[chunk.chunk_type] = chunk_types.get(chunk.chunk_type, 0) + 1
            if chunk.name and chunk.chunk_type in ('class', 'function', 'method'):
                names.append(chunk.name)
        
        # Build description
        parts = []
        
        if 'class' in chunk_types:
            parts.append(f"{chunk_types['class']} class(es)")
        if 'function' in chunk_types:
            parts.append(f"{chunk_types['function']} function(s)")
        if 'method' in chunk_types:
            parts.append(f"{chunk_types['method']} method(s)")
        
        if names:
            key_names = names[:3]
            if len(names) > 3:
                key_names.append("...")
            parts.append(f"including {', '.join(key_names)}")
        
        return ', '.join(parts) if parts else "Code file"

    def _find_patterns(
        self,
        relevant_code: List[SearchResult],
        search_across_projects: Optional[str] = None,
    ) -> List[PatternGroup]:
        """Find similar code patterns across the codebase."""
        patterns: List[PatternGroup] = []
        
        # Group chunks by type
        by_type: Dict[str, List[SearchResult]] = {}
        for result in relevant_code:
            by_type.setdefault(result.chunk_type, []).append(result)
        
        # For each type, look for patterns
        for chunk_type, results in by_type.items():
            if len(results) < 2:
                continue
            
            # Group by name similarity
            by_name: Dict[str, List[SearchResult]] = {}
            for result in results:
                # Simplistic grouping by first word of name
                base_name = result.name.split('.')[-1].split('_')[0].lower()
                by_name.setdefault(base_name, []).append(result)
            
            for name, name_results in by_name.items():
                if len(name_results) >= 2:
                    # Calculate average similarity
                    avg_sim = sum(r.similarity for r in name_results) / len(name_results)
                    
                    patterns.append(PatternGroup(
                        pattern_id=name,
                        pattern_type=chunk_type,
                        similarity_score=avg_sim,
                        chunk_ids=[r.chunk.chunk_id for r in name_results],
                        file_paths=[r.file_path for r in name_results],
                        description=f"Found {len(name_results)} similar {chunk_type}(s) named '{name}'",
                    ))
        
        return patterns

    def quick_context(
        self,
        project_path: str,
        task: str,
    ) -> str:
        """
        Generate a quick context string for a task.
        
        Convenience method that returns formatted markdown directly.
        
        Args:
            project_path: Path to the project
            task: Natural language description of the task
        
        Returns:
            Markdown-formatted context string
        """
        ctx = self.generate_context(project_path, task)
        return ctx.to_markdown()


# ============================================================
# CLI Helpers
# ============================================================

def format_context_for_llm(
    context: DevelopmentContext,
    format: str = "markdown",
) -> str:
    """
    Format context for consumption by an LLM.
    
    Args:
        context: The DevelopmentContext to format
        format: Output format ("markdown", "json", "text")
    
    Returns:
        Formatted string
    """
    if format == "markdown":
        return context.to_markdown()
    elif format == "json":
        return json.dumps(context.to_dict(), indent=2, ensure_ascii=False)
    elif format == "text":
        # Simple text format
        lines = [
            f"Task: {context.task_description}",
            f"Project: {context.project_name}",
            "",
            "Relevant Files:",
        ]
        for fc in context.relevant_files:
            lines.append(f"  - {fc.path}")
        
        lines.extend([
            "",
            "Relevant Code:",
        ])
        for i, result in enumerate(context.relevant_code, 1):
            lines.extend([
                f"  [{i}] {result.name} in {result.file_path}:{result.start_line}",
                f"      {result.source_code[:200]}...",
            ])
        
        return '\n'.join(lines)
    else:
        raise ValueError(f"Unknown format: {format}")
