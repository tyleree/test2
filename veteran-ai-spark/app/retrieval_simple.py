"""
Simplified retrieval module for testing without heavy dependencies.
"""

import logging
from typing import List, Dict, Any, Optional
import openai

from .config import config
from .utils import extract_doc_ids_from_results, count_tokens

logger = logging.getLogger(__name__)


class SimpleDocumentRetriever:
    """Simplified document retrieval for testing."""
    
    def __init__(self):
        self.openai_client = None
    
    def _embed_query(self, query: str) -> List[float]:
        """Generate embedding for query using OpenAI."""
        try:
            if self.openai_client is None:
                self.openai_client = openai.OpenAI(api_key=config.openai_api_key)
            
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=query
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            # Return dummy embedding for testing
            return [0.1] * 1536
    
    def retrieve_top_chunks(
        self, 
        query: str, 
        k: int = None, 
        use_query_expansion: bool = True,
        use_bm25_hybrid: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Simplified retrieval - returns mock documents for testing.
        """
        if k is None:
            k = config.retrieve_k
        
        logger.info(f"Mock retrieval for query: {query[:100]}...")
        
        # Return mock documents for testing
        mock_docs = []
        for i in range(min(k, 5)):  # Return up to 5 mock documents
            mock_docs.append({
                'doc_id': f'mock_doc_{i}',
                'chunk_id': f'mock_doc_{i}_chunk_1',
                'text': f'This is mock content for document {i} about {query}. It contains relevant information that would help answer the user\'s question.',
                'url': f'https://example.com/mock_doc_{i}',
                'title': f'Mock Document {i}',
                'score': 0.9 - (i * 0.1)
            })
        
        logger.info(f"Retrieved {len(mock_docs)} mock documents")
        return mock_docs
    
    def get_fresh_top_docs(self, query: str, k: int = None) -> List[str]:
        """Get fresh top document IDs for cache validation."""
        if k is None:
            k = config.retrieve_k
        
        results = self.retrieve_top_chunks(query, k=k, use_query_expansion=False)
        return extract_doc_ids_from_results(results)


# Global retriever instance
retriever = SimpleDocumentRetriever()
