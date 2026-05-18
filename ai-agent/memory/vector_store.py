"""Vector memory for semantic code search (RAG)"""
import os
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class CodeChunk:
    path: str
    content: str
    start_line: int
    end_line: int
    embedding: Optional[List[float]] = None
    score: float = 0.0


class ProjectIndex:
    """Simple semantic search over project files"""

    def __init__(self, project_path: str = ".", embedding_model: Optional[str] = None):
        self.project_path = Path(project_path).resolve()
        self.chunks: List[CodeChunk] = []
        self._embedder = None
        self._embedding_model = embedding_model

        # Lazy load embedder
        self._try_load_embedder()

    def _try_load_embedder(self):
        """Try to load sentence-transformers, fallback to simple keyword matching"""
        try:
            from sentence_transformers import SentenceTransformer
            model_name = self._embedding_model or "all-MiniLM-L6-v2"
            self._embedder = SentenceTransformer(model_name)
            print(f"[VectorStore] Loaded embedding model: {model_name}")
        except ImportError:
            print("[VectorStore] sentence-transformers not installed. Using keyword fallback.")
            self._embedder = None

    def index_files(self, pattern: str = "*.py", chunk_size: int = 50) -> int:
        """Index all matching files"""
        self.chunks = []
        files = list(self.project_path.rglob(pattern))

        for file_path in files:
            if not file_path.is_file():
                continue
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

                # Chunk by logical blocks (functions/classes) or fixed size
                chunks = self._chunk_file(lines, chunk_size)

                for start, end, content in chunks:
                    rel = str(file_path.relative_to(self.project_path))
                    self.chunks.append(CodeChunk(
                        path=rel,
                        content=content,
                        start_line=start,
                        end_line=end
                    ))
            except Exception as e:
                print(f"[VectorStore] Failed to index {file_path}: {e}")

        # Compute embeddings if available
        if self._embedder:
            texts = [c.content for c in self.chunks]
            embeddings = self._embedder.encode(texts, show_progress_bar=True)
            for chunk, emb in zip(self.chunks, embeddings):
                chunk.embedding = emb.tolist()

        print(f"[VectorStore] Indexed {len(self.chunks)} chunks from {len(files)} files")
        return len(self.chunks)

    def _chunk_file(self, lines: List[str], chunk_size: int) -> List[tuple]:
        """Split file into chunks"""
        chunks = []
        current_start = 0
        current_lines = []

        for i, line in enumerate(lines):
            current_lines.append(line)
            # Split on empty line or function/class definition
            if len(current_lines) >= chunk_size or (line.strip() == "" and len(current_lines) > 5):
                content = "".join(current_lines)
                chunks.append((current_start + 1, i + 1, content))
                current_start = i + 1
                current_lines = []

        if current_lines:
            content = "".join(current_lines)
            chunks.append((current_start + 1, len(lines), content))

        return chunks

    def search(self, query: str, top_k: int = 5) -> List[CodeChunk]:
        """Semantic or keyword search"""
        if not self.chunks:
            return []

        if self._embedder:
            return self._semantic_search(query, top_k)
        else:
            return self._keyword_search(query, top_k)

    def _semantic_search(self, query: str, top_k: int) -> List[CodeChunk]:
        """Search using cosine similarity"""
        import numpy as np

        query_emb = self._embedder.encode([query])[0]

        scored = []
        for chunk in self.chunks:
            if chunk.embedding:
                emb = np.array(chunk.embedding)
                q = np.array(query_emb)
                sim = np.dot(emb, q) / (np.linalg.norm(emb) * np.linalg.norm(q))
                chunk.score = float(sim)
                scored.append(chunk)

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def _keyword_search(self, query: str, top_k: int) -> List[CodeChunk]:
        """Fallback keyword search"""
        query_words = set(query.lower().split())
        scored = []

        for chunk in self.chunks:
            content_lower = chunk.content.lower()
            score = sum(1 for w in query_words if w in content_lower)
            if score > 0:
                chunk.score = score
                scored.append(chunk)

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def get_context_for_query(self, query: str, max_chars: int = 4000) -> str:
        """Get relevant code context as string for LLM prompt"""
        results = self.search(query, top_k=10)
        context_parts = []
        total = 0

        for r in results:
            header = f"\n--- {r.path}:{r.start_line}-{r.end_line} (score: {r.score:.3f}) ---\n"
            piece = header + r.content
            if total + len(piece) > max_chars:
                break
            context_parts.append(piece)
            total += len(piece)

        return "\n".join(context_parts)
