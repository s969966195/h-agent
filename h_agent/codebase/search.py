#!/usr/bin/env python3
"""
h_agent/codebase/search.py - Semantic Code Search

Provides semantic search over indexed code chunks using embeddings.
"""

import math
from pathlib import Path
from typing import Dict, List, Any, Optional, Iterator
from dataclasses import dataclass

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from h_agent.codebase.indexer import CodebaseIndex, CodeChunk, DEFAULT_INDEX_DIR


# ============================================================
# Embedder (Lightweight, no external dependencies)
# ============================================================

class CodeEmbedder:
    """
    Simple embedder using TF-IDF and keyword matching.
    
    For full embedding support, install sentence-transformers:
        pip install sentence-transformers
    
    Or use OpenAI embeddings via the API.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._keywords_cache: Dict[str, List[str]] = {}
        self._doc_freq: Dict[str, float] = {}
        self._total_docs = 0

    def embed_text(self, text: str) -> List[float]:
        """
        Generate a simple embedding using TF-IDF-like approach.
        
        For production, use sentence-transformers or OpenAI embeddings.
        """
        # Tokenize
        words = self._tokenize(text)
        if not words:
            return [0.0] * 384
        
        # Simple hash-based embedding
        embedding = [0.0] * 384
        
        for i, word in enumerate(words[:100]):  # Limit vocab
            # Simple hash
            h = hash(word)
            for j in range(16):  # Spread across 16 dimensions
                idx = (h + j * 137) % 384
                embedding[idx] += math.sin(h / (j + 1))
        
        # Normalize
        norm = math.sqrt(sum(x * x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        return embedding

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        import re
        # Split on non-word characters, lowercase
        words = re.findall(r'\w+', text.lower())
        # Filter short words
        return [w for w in words if len(w) > 2]


class SentenceTransformerEmbedder:
    """
    Full embedder using sentence-transformers.
    
    Usage:
        embedder = SentenceTransformerEmbedder("all-MiniLM-L6-v2")
        embedding = embedder.embed_text("user authentication")
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
            self.dimension = self.model.get_sentence_embedding_dimension()
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding using sentence-transformers."""
        embedding = self.model.encode(text)
        return embedding.tolist()


# ============================================================
# Search Result
# ============================================================

@dataclass
class SearchResult:
    """A search result with similarity score."""
    chunk: CodeChunk
    similarity: float
    file_path: str
    chunk_type: str
    name: str
    start_line: int
    end_line: int
    source_code: str
    docstring: str = ""

    def to_dict(self) -> dict:
        return {
            'similarity': self.similarity,
            'file_path': self.file_path,
            'chunk_type': self.chunk_type,
            'name': self.name,
            'start_line': self.start_line,
            'end_line': self.end_line,
            'source_code': self.source_code,
            'docstring': self.docstring,
        }


# ============================================================
# Code Search
# ============================================================

class CodeSearch:
    """
    Semantic code search engine.
    
    Usage:
        search = CodeSearch()
        
        # Search across all indexed projects
        results = search.search("user authentication logic")
        
        # Search with filters
        results = search.search(
            "database queries",
            project_name="myproject",
            chunk_types=["function", "class"],
            top_k=10,
        )
        
        # Get project stats
        stats = search.get_project_stats()
    """

    def __init__(
        self,
        index_dir: Path = None,
        embedder_model: str = "all-MiniLM-L6-v2",
        use_advanced_embeddings: bool = True,
    ):
        self.index_dir = index_dir or DEFAULT_INDEX_DIR
        self._embedder: Optional[CodeEmbedder] = None
        self.embedder_model = embedder_model
        self.use_advanced_embeddings = use_advanced_embeddings
        
        # Cache for loaded indexes
        self._indexes: Dict[str, CodebaseIndex] = {}

    def _get_embedder(self) -> CodeEmbedder:
        """Get or create embedder instance."""
        if self._embedder is None:
            if self.use_advanced_embeddings:
                try:
                    self._embedder = SentenceTransformerEmbedder(self.embedder_model)
                except ImportError:
                    self._embedder = CodeEmbedder(self.embedder_model)
            else:
                self._embedder = CodeEmbedder(self.embedder_model)
        return self._embedder

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not HAS_NUMPY:
            # Pure Python implementation
            dot = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = math.sqrt(sum(a * a for a in vec1))
            norm2 = math.sqrt(sum(b * b for b in vec2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot / (norm1 * norm2)
        else:
            import numpy as np
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

    def _load_index(self, project_path: str) -> Optional[CodebaseIndex]:
        """Load or create index for a project."""
        if project_path in self._indexes:
            return self._indexes[project_path]
        
        try:
            index = CodebaseIndex(project_path, self.index_dir)
            self._indexes[project_path] = index
            return index
        except FileNotFoundError:
            return None

    def search(
        self,
        query: str,
        project_path: str = None,
        chunk_types: List[str] = None,
        languages: List[str] = None,
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> List[SearchResult]:
        """
        Search for relevant code chunks.
        
        Args:
            query: Natural language query (e.g., "user login logic")
            project_path: If provided, limit search to specific project
            chunk_types: Filter by chunk types (function, class, method, etc.)
            languages: Filter by programming languages
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold (0.0 to 1.0)
        
        Returns:
            List of SearchResult sorted by similarity score (descending)
        """
        embedder = self._get_embedder()
        query_embedding = embedder.embed_text(query)
        
        # Determine which indexes to search
        if project_path:
            indexes = [self._load_index(project_path)]
        else:
            # Search all indexes in index_dir
            indexes = []
            for idx_file in self.index_dir.glob("*_chunks.json"):
                # Extract project path from index
                try:
                    data = json.loads(idx_file.read_text())
                    path = data.get('info', {}).get('project_path')
                    if path:
                        index = self._load_index(path)
                        if index:
                            indexes.append(index)
                except (json.JSONDecodeError, OSError):
                    continue
        
        results: List[SearchResult] = []
        
        for index in indexes:
            if not index:
                continue
            
            for chunk in index.iterate_chunks():
                # Apply filters
                if chunk_types and chunk.chunk_type not in chunk_types:
                    continue
                if languages and chunk.language not in languages:
                    continue
                
                # Compute similarity
                # For simple embedder, use keyword matching as fallback
                chunk_embedding = self._compute_chunk_embedding(chunk, embedder)
                similarity = self._cosine_similarity(query_embedding, chunk_embedding)
                
                if similarity >= min_similarity:
                    results.append(SearchResult(
                        chunk=chunk,
                        similarity=similarity,
                        file_path=chunk.file_path,
                        chunk_type=chunk.chunk_type,
                        name=chunk.name,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        source_code=chunk.source_code,
                        docstring=chunk.docstring,
                    ))
        
        # Sort by similarity (descending)
        results.sort(key=lambda r: r.similarity, reverse=True)
        
        return results[:top_k]

    def _compute_chunk_embedding(self, chunk: CodeChunk, embedder: CodeEmbedder) -> List[float]:
        """Compute embedding for a code chunk (combines signature + docstring + code)."""
        text_parts = []
        
        # Include name and signature
        if chunk.name:
            text_parts.append(chunk.name)
        if chunk.signature:
            text_parts.append(chunk.signature)
        if chunk.docstring:
            text_parts.append(chunk.docstring)
        
        # Include first few lines of code (for context)
        code_lines = chunk.source_code.split('\n')[:20]
        text_parts.append(' '.join(code_lines))
        
        combined_text = ' '.join(text_parts)
        return embedder.embed_text(combined_text)

    def find_similar_chunks(
        self,
        chunk_id: str,
        project_path: str,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """
        Find chunks similar to a given chunk.
        
        Args:
            chunk_id: ID of the reference chunk
            project_path: Path to the project containing the chunk
            top_k: Number of results to return
        
        Returns:
            List of similar SearchResult
        """
        index = self._load_index(project_path)
        if not index:
            return []
        
        chunk = index.get_chunk(chunk_id)
        if not chunk:
            return []
        
        embedder = self._get_embedder()
        query_embedding = self._compute_chunk_embedding(chunk, embedder)
        
        results: List[SearchResult] = []
        
        for other_chunk in index.iterate_chunks():
            if other_chunk.chunk_id == chunk_id:
                continue
            
            other_embedding = self._compute_chunk_embedding(other_chunk, embedder)
            similarity = self._cosine_similarity(query_embedding, other_embedding)
            
            results.append(SearchResult(
                chunk=other_chunk,
                similarity=similarity,
                file_path=other_chunk.file_path,
                chunk_type=other_chunk.chunk_type,
                name=other_chunk.name,
                start_line=other_chunk.start_line,
                end_line=other_chunk.end_line,
                source_code=other_chunk.source_code,
                docstring=other_chunk.docstring,
            ))
        
        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:top_k]

    def get_project_stats(self) -> List[Dict[str, Any]]:
        """Get statistics for all indexed projects."""
        stats = []
        
        for idx_file in self.index_dir.glob("*_chunks.json"):
            try:
                data = json.loads(idx_file.read_text())
                info = data.get('info', {})
                stats.append({
                    'project_name': info.get('project_name', 'unknown'),
                    'project_path': info.get('project_path', 'unknown'),
                    'file_count': info.get('file_count', 0),
                    'chunk_count': info.get('chunk_count', 0),
                    'languages': info.get('languages', {}),
                    'last_scan': info.get('scan_time', 0),
                })
            except (json.JSONDecodeError, OSError):
                continue
        
        return stats

    def index_project(
        self,
        project_path: str,
        incremental: bool = True,
    ) -> Dict[str, Any]:
        """
        Index a project for searching.
        
        Args:
            project_path: Path to the project
            incremental: If True, only re-index changed files
        
        Returns:
            Index info
        """
        index = CodebaseIndex(project_path, self.index_dir)
        self._indexes[project_path] = index
        return index.scan(incremental=incremental)

    def search_by_file(
        self,
        file_path: str,
        project_path: str = None,
    ) -> List[SearchResult]:
        """
        Get all chunks from a specific file.
        
        Args:
            file_path: Relative path to the file
            project_path: Path to the project
        
        Returns:
            List of SearchResult for chunks in the file
        """
        if project_path:
            indexes = [self._load_index(project_path)]
        else:
            indexes = list(self._indexes.values())
        
        results: List[SearchResult] = []
        
        for index in indexes:
            if not index:
                continue
            
            chunks = index.get_chunks(file_path=file_path)
            for chunk in chunks:
                results.append(SearchResult(
                    chunk=chunk,
                    similarity=1.0,  # Exact match
                    file_path=chunk.file_path,
                    chunk_type=chunk.chunk_type,
                    name=chunk.name,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    source_code=chunk.source_code,
                    docstring=chunk.docstring,
                ))
        
        return results


# Need to import json at module level
import json
