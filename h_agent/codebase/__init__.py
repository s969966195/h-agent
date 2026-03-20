"""
h_agent/codebase - Codebase Indexing and Semantic Search

Provides intelligent code search and context generation for development tasks.
Inspired by codebase-rag project.

Usage:
    from h_agent.codebase import CodebaseIndex, CodeSearch
    
    # Index a project
    index = CodebaseIndex("/path/to/project")
    index.scan()
    
    # Search for code
    search = CodeSearch()
    results = search.search("user authentication logic")
    
    # Get context for a task
    ctx = search.get_context("project_name", "add user profile")
"""

from h_agent.codebase.indexer import CodebaseIndex, FileIndexer
from h_agent.codebase.search import CodeSearch
from h_agent.codebase.context import ContextGenerator

__all__ = [
    "CodebaseIndex",
    "FileIndexer", 
    "CodeSearch",
    "ContextGenerator",
]
