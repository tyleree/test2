"""
Simplified reranking module for testing without heavy dependencies.
"""

import logging
from typing import List, Dict, Any

from .config import config

logger = logging.getLogger(__name__)


class SimpleDocumentReranker:
    """Simple reranker for testing without CrossEncoder dependencies."""
    
    def __init__(self):
        pass
    
    def rerank_documents(
        self, 
        query: str, 
        documents: List[Dict[str, Any]], 
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Simple reranking based on existing scores.
        """
        if top_k is None:
            top_k = config.rerank_k
        
        if not documents:
            return []
        
        logger.info(f"Simple reranking of {len(documents)} documents, returning top {top_k}")
        
        # Sort by existing score and take top_k
        reranked_docs = []
        for doc in documents:
            doc_copy = doc.copy()
            doc_copy['rerank_score'] = doc_copy.get('score', 0)
            doc_copy['original_score'] = doc_copy.get('score', 0)
            reranked_docs.append(doc_copy)
        
        # Sort by rerank score (descending)
        reranked_docs.sort(key=lambda x: x['rerank_score'], reverse=True)
        
        return reranked_docs[:top_k]
    
    def get_relevance_score(self, query: str, text: str) -> float:
        """Simple relevance score based on keyword overlap."""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())
        
        if not query_words or not text_words:
            return 0.0
        
        overlap = len(query_words.intersection(text_words))
        return overlap / len(query_words.union(text_words))


# Global reranker instance
reranker = SimpleDocumentReranker()







