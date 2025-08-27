"""
Document reranking using CrossEncoder for improved relevance scoring.
"""

import logging
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder

from .settings import settings

logger = logging.getLogger(__name__)


class DocumentReranker:
    """Rerank retrieved documents using CrossEncoder for better relevance."""
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = None
        self.model_name = model_name
        self._load_model()
    
    def _load_model(self):
        """Load CrossEncoder model lazily."""
        if self.model is None:
            try:
                self.model = CrossEncoder(self.model_name)
                logger.info(f"Loaded CrossEncoder model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to load CrossEncoder model: {e}")
                self.model = None
    
    def rerank_documents(
        self, 
        query: str, 
        documents: List[Dict[str, Any]], 
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using CrossEncoder.
        
        Args:
            query: The search query
            documents: List of documents with text content
            top_k: Number of top documents to return (defaults to settings.rerank_k)
        
        Returns:
            Reranked list of documents with updated scores
        """
        if top_k is None:
            top_k = settings.rerank_k
        
        if not documents:
            return []
        
        # Fallback if model failed to load
        if self.model is None:
            logger.warning("CrossEncoder model not available, using original scores")
            return sorted(documents, key=lambda x: x.get('score', 0), reverse=True)[:top_k]
        
        try:
            # Prepare query-document pairs
            pairs = []
            for doc in documents:
                text = doc.get('text', '').strip()
                if text:
                    pairs.append([query, text])
                else:
                    # Handle empty text
                    pairs.append([query, doc.get('title', 'No content')])
            
            if not pairs:
                return []
            
            # Get relevance scores
            scores = self.model.predict(pairs)
            
            # Update documents with new scores
            reranked_docs = []
            for doc, score in zip(documents, scores):
                doc_copy = doc.copy()
                doc_copy['rerank_score'] = float(score)
                doc_copy['original_score'] = doc_copy.get('score', 0)
                doc_copy['score'] = float(score)  # Update main score
                reranked_docs.append(doc_copy)
            
            # Sort by rerank score (descending)
            reranked_docs.sort(key=lambda x: x['rerank_score'], reverse=True)
            
            logger.info(f"Reranked {len(documents)} documents, returning top {top_k}")
            
            return reranked_docs[:top_k]
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Fallback to original ranking
            return sorted(documents, key=lambda x: x.get('score', 0), reverse=True)[:top_k]
    
    def batch_rerank(
        self, 
        queries_docs: List[tuple], 
        top_k: int = None
    ) -> List[List[Dict[str, Any]]]:
        """
        Batch rerank multiple query-document sets.
        
        Args:
            queries_docs: List of (query, documents) tuples
            top_k: Number of top documents per query
        
        Returns:
            List of reranked document lists
        """
        results = []
        for query, docs in queries_docs:
            reranked = self.rerank_documents(query, docs, top_k)
            results.append(reranked)
        
        return results
    
    def get_relevance_score(self, query: str, text: str) -> float:
        """
        Get relevance score for a single query-text pair.
        
        Args:
            query: The search query
            text: The document text
        
        Returns:
            Relevance score (higher is more relevant)
        """
        if self.model is None:
            return 0.0
        
        try:
            score = self.model.predict([[query, text]])[0]
            return float(score)
        except Exception as e:
            logger.error(f"Failed to get relevance score: {e}")
            return 0.0
    
    def filter_by_threshold(
        self, 
        documents: List[Dict[str, Any]], 
        threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Filter documents by minimum relevance threshold.
        
        Args:
            documents: List of documents with rerank_score
            threshold: Minimum score threshold
        
        Returns:
            Filtered list of documents
        """
        filtered = []
        for doc in documents:
            score = doc.get('rerank_score', doc.get('score', 0))
            if score >= threshold:
                filtered.append(doc)
        
        logger.info(f"Filtered {len(documents)} documents to {len(filtered)} above threshold {threshold}")
        
        return filtered


# Global reranker instance
reranker = DocumentReranker()









