"""
In-Memory Vector Store with Cosine Similarity Search

This module provides a simple, efficient vector store that:
- Loads documents from the restructured corpus JSON
- Stores embeddings in memory
- Performs cosine similarity search for retrieval
- Returns top-K chunks with full metadata

Designed to be swappable with external vector DBs (Pinecone, pgvector, etc.)
by implementing the same interface.
"""

import json
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Document:
    """A document chunk with its embedding and metadata."""
    id: str
    text: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "embedding": self.embedding,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Document":
        return cls(
            id=data.get("id", ""),
            text=data.get("text", ""),
            embedding=data.get("embedding"),
            metadata=data.get("metadata", {})
        )


@dataclass
class SearchResult:
    """A search result with similarity score."""
    document: Document
    score: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.document.id,
            "text": self.document.text,
            "score": self.score,
            "metadata": self.document.metadata
        }


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class InMemoryVectorStore:
    """
    In-memory vector store with cosine similarity search.
    
    This implementation is suitable for small to medium corpora (< 100K documents).
    For larger corpora, consider using Pinecone, pgvector, or Qdrant.
    
    Usage:
        store = InMemoryVectorStore()
        store.load_corpus("path/to/corpus.json")
        store.set_embeddings(embeddings_dict)  # {doc_id: [float, ...]}
        results = store.search(query_embedding, k=5)
    """
    
    def __init__(self):
        self.documents: Dict[str, Document] = {}
        self._embeddings_matrix: Optional[np.ndarray] = None
        self._doc_ids: List[str] = []
        self._is_indexed = False
    
    def load_corpus(self, corpus_path: str) -> int:
        """
        Load documents from the restructured corpus JSON file.
        
        Expected format (from vbkb_restructured.json):
        [
            {
                "source_id": "...",
                "entry_id": "7101-001",
                "topic": "High Blood Pressure",
                "type": "rating_table",
                "original_heading": "...",
                "url": "https://...",
                "diagnostic_code": "7101",
                "content": "..."
            },
            ...
        ]
        
        Returns the number of documents loaded.
        """
        path = Path(corpus_path)
        if not path.exists():
            raise FileNotFoundError(f"Corpus file not found: {corpus_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            corpus_data = json.load(f)
        
        self.documents.clear()
        
        for item in corpus_data:
            doc_id = item.get("entry_id", "")
            if not doc_id:
                continue
            
            # Extract text content
            text = item.get("content", "")
            if not text:
                continue
            
            # Build metadata from all fields except content
            metadata = {
                "source_id": item.get("source_id", ""),
                "topic": item.get("topic", ""),
                "subtopic": item.get("subtopic"),
                "type": item.get("type", ""),
                "original_heading": item.get("original_heading", ""),
                "url": item.get("url", ""),
                "source_url": item.get("url", ""),  # Alias for compatibility
                "diagnostic_code": item.get("diagnostic_code"),
                "parent_topic": item.get("parent_topic"),
                "last_updated": item.get("last_updated"),
            }
            # Remove None values
            metadata = {k: v for k, v in metadata.items() if v is not None}
            
            doc = Document(
                id=doc_id,
                text=text,
                metadata=metadata
            )
            self.documents[doc_id] = doc
        
        self._is_indexed = False
        print(f"\ud83d\udcda Loaded {len(self.documents)} documents from corpus")
        return len(self.documents)
    
    def set_embeddings(self, embeddings: Dict[str, List[float]]) -> int:
        """
        Set embeddings for documents.
        
        Args:
            embeddings: Dict mapping document IDs to embedding vectors
            
        Returns:
            Number of embeddings set
        """
        count = 0
        for doc_id, embedding in embeddings.items():
            if doc_id in self.documents:
                self.documents[doc_id].embedding = embedding
                count += 1
        
        self._build_index()
        print(f"\ud83d\udd22 Set embeddings for {count} documents")
        return count
    
    def _build_index(self):
        """Build the numpy matrix for fast similarity search."""
        docs_with_embeddings = [
            (doc_id, doc) 
            for doc_id, doc in self.documents.items() 
            if doc.embedding is not None
        ]
        
        if not docs_with_embeddings:
            self._embeddings_matrix = None
            self._doc_ids = []
            self._is_indexed = False
            return
        
        self._doc_ids = [doc_id for doc_id, _ in docs_with_embeddings]
        embeddings_list = [doc.embedding for _, doc in docs_with_embeddings]
        self._embeddings_matrix = np.array(embeddings_list, dtype=np.float32)
        
        # Normalize for faster cosine similarity (just dot product after normalization)
        norms = np.linalg.norm(self._embeddings_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Avoid division by zero
        self._embeddings_matrix = self._embeddings_matrix / norms
        
        self._is_indexed = True
        print(f"\ud83d\udcca Built index with {len(self._doc_ids)} vectors")
    
    def search(
        self, 
        query_embedding: List[float], 
        k: int = 5,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """
        Search for the most similar documents.
        
        Args:
            query_embedding: The query embedding vector
            k: Number of results to return
            min_score: Minimum similarity score threshold
            
        Returns:
            List of SearchResult objects sorted by similarity (highest first)
        """
        if not self._is_indexed or self._embeddings_matrix is None:
            print("\u26a0\ufe0f Vector store not indexed. Call set_embeddings() first.")
            return []
        
        # Normalize query vector
        query = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        query = query / query_norm
        
        # Compute similarities (dot product with normalized vectors = cosine similarity)
        similarities = np.dot(self._embeddings_matrix, query)
        
        # Get top-k indices
        if k >= len(similarities):
            top_indices = np.argsort(similarities)[::-1]
        else:
            # Use argpartition for efficiency with large arrays
            top_indices = np.argpartition(similarities, -k)[-k:]
            top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score < min_score:
                continue
            
            doc_id = self._doc_ids[idx]
            doc = self.documents[doc_id]
            results.append(SearchResult(document=doc, score=score))
        
        return results
    
    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a document by ID."""
        return self.documents.get(doc_id)
    
    def get_all_ids(self) -> List[str]:
        """Get all document IDs."""
        return list(self.documents.keys())
    
    def __len__(self) -> int:
        return len(self.documents)
    
    @property
    def is_ready(self) -> bool:
        """Check if the store is ready for search."""
        return self._is_indexed and len(self._doc_ids) > 0


# Singleton instance for the application
_vector_store: Optional[InMemoryVectorStore] = None


def get_vector_store() -> InMemoryVectorStore:
    """Get or create the global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = InMemoryVectorStore()
    return _vector_store


def initialize_vector_store(corpus_path: str, embeddings: Dict[str, List[float]]) -> InMemoryVectorStore:
    """Initialize the global vector store with corpus and embeddings."""
    store = get_vector_store()
    store.load_corpus(corpus_path)
    store.set_embeddings(embeddings)
    return store
