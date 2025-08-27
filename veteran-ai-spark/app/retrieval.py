"""
Document retrieval module with Pinecone vector search and optional BM25.
"""

import logging
from typing import List, Dict, Any, Optional
from pinecone import Pinecone
import openai
from rank_bm25 import BM25Okapi

from .settings import settings
from .utils import extract_doc_ids_from_results, count_tokens

logger = logging.getLogger(__name__)


class DocumentRetriever:
    """Document retrieval using Pinecone vector search with optional BM25 hybrid."""
    
    def __init__(self):
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index = self.pc.Index(settings.pinecone_index)
        self.openai_client = openai.OpenAI(api_key=settings.openai_api_key)
        self.bm25_corpus = None  # Optional BM25 corpus
        self.bm25_index = None
        self.doc_texts = {}  # doc_id -> text mapping for BM25
    
    def _embed_query(self, query: str) -> List[float]:
        """Generate embedding for query using OpenAI."""
        # Use configurable embedding model to match Pinecone index dimensions
        embed_params = {
            "model": settings.embedding_model,
            "input": query
        }
        
        # For text-embedding-3-large, we can specify dimensions to match Pinecone
        if settings.embedding_model == "text-embedding-3-large":
            embed_params["dimensions"] = 1024  # Match typical Pinecone index
        
        response = self.openai_client.embeddings.create(**embed_params)
        return response.data[0].embedding
    
    def _rewrite_query(self, query: str) -> List[str]:
        """
        Optional query rewrite using small model to expand into subqueries.
        Keeps costs low by using small model.
        """
        try:
            response = self.openai_client.chat.completions.create(
                model=settings.model_small,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a query expansion assistant. Given a user question, generate up to 3 related subqueries that would help find comprehensive information. Return only the queries, one per line, no numbering or explanation."
                    },
                    {
                        "role": "user",
                        "content": f"Expand this query into subqueries: {query}"
                    }
                ],
                max_tokens=150,
                temperature=0.3
            )
            
            subqueries = [line.strip() for line in response.choices[0].message.content.strip().split('\n') if line.strip()]
            
            # Always include original query
            if query not in subqueries:
                subqueries.insert(0, query)
            
            return subqueries[:3]  # Limit to 3 subqueries
            
        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}")
            return [query]  # Fallback to original query
    
    def _vector_search(self, query: str, k: int = 50) -> List[Dict[str, Any]]:
        """Perform vector search using Pinecone."""
        try:
            # Generate embedding
            embedding = self._embed_query(query)
            
            # Search Pinecone
            results = self.index.query(
                vector=embedding,
                top_k=k,
                include_metadata=True
            )
            
            # Convert to standard format
            documents = []
            for match in results['matches']:
                metadata = match.get('metadata', {})
                documents.append({
                    'doc_id': metadata.get('doc_id', match['id']),
                    'chunk_id': match['id'],
                    'text': metadata.get('text', ''),
                    'url': metadata.get('url', ''),
                    'title': metadata.get('title', ''),
                    'score': match['score']
                })
            
            return documents
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def _bm25_search(self, query: str, k: int = 50) -> List[Dict[str, Any]]:
        """
        Perform BM25 search if corpus is available locally.
        This is optional and provides zero-token hybrid search.
        """
        if not self.bm25_index:
            return []
        
        try:
            # Tokenize query
            query_tokens = query.lower().split()
            
            # Get BM25 scores
            scores = self.bm25_index.get_scores(query_tokens)
            
            # Get top-k results
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
            
            documents = []
            for idx in top_indices:
                if scores[idx] > 0:  # Only include positive scores
                    doc_id = list(self.doc_texts.keys())[idx]
                    documents.append({
                        'doc_id': doc_id,
                        'chunk_id': f"{doc_id}-bm25",
                        'text': self.doc_texts[doc_id],
                        'url': '',  # Would need to be populated from metadata
                        'title': doc_id,
                        'score': scores[idx]
                    })
            
            return documents
            
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []
    
    def retrieve_top_chunks(
        self, 
        query: str, 
        k: int = None, 
        use_query_expansion: bool = True,
        use_bm25_hybrid: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve top relevant chunks using vector search and optional BM25.
        
        Args:
            query: The search query
            k: Number of results to return (defaults to settings.retrieve_k)
            use_query_expansion: Whether to expand query into subqueries
            use_bm25_hybrid: Whether to include BM25 results
        
        Returns:
            List of document chunks with metadata and scores
        """
        if k is None:
            k = settings.retrieve_k
        
        all_results = []
        seen_doc_ids = set()
        
        # Generate subqueries if enabled
        queries = self._rewrite_query(query) if use_query_expansion else [query]
        
        # Perform vector search for each query
        for q in queries:
            results = self._vector_search(q, k=k)
            
            # Add unique results
            for result in results:
                doc_id = result['doc_id']
                if doc_id not in seen_doc_ids:
                    all_results.append(result)
                    seen_doc_ids.add(doc_id)
        
        # Optional BM25 hybrid search
        if use_bm25_hybrid:
            bm25_results = self._bm25_search(query, k=k//2)
            
            for result in bm25_results:
                doc_id = result['doc_id']
                if doc_id not in seen_doc_ids:
                    all_results.append(result)
                    seen_doc_ids.add(doc_id)
        
        # Sort by score (descending) and limit results
        all_results.sort(key=lambda x: x['score'], reverse=True)
        
        logger.info(f"Retrieved {len(all_results)} unique chunks for query: {query[:100]}")
        
        return all_results[:k]
    
    def load_bm25_corpus(self, doc_texts: Dict[str, str]):
        """
        Load BM25 corpus for hybrid search.
        
        Args:
            doc_texts: Dictionary mapping doc_id to text content
        """
        try:
            self.doc_texts = doc_texts
            
            # Tokenize all documents
            tokenized_corpus = [text.lower().split() for text in doc_texts.values()]
            
            # Build BM25 index
            self.bm25_index = BM25Okapi(tokenized_corpus)
            
            logger.info(f"Loaded BM25 corpus with {len(doc_texts)} documents")
            
        except Exception as e:
            logger.error(f"Failed to load BM25 corpus: {e}")
            self.bm25_index = None
    
    def get_fresh_top_docs(self, query: str, k: int = None) -> List[str]:
        """
        Get fresh top document IDs for cache validation.
        Used by validators to check if cached results are still relevant.
        """
        if k is None:
            k = settings.retrieve_k
        
        results = self.retrieve_top_chunks(query, k=k, use_query_expansion=False)
        return extract_doc_ids_from_results(results)


# Global retriever instance
retriever = DocumentRetriever()









