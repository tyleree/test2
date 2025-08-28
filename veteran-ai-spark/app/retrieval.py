"""
Hybrid retrieval system combining Pinecone vector search with BM25.
Includes query rewriting and score fusion.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import json

import openai
from pinecone import Pinecone
from rank_bm25 import BM25Okapi
import numpy as np

from .config import config
from .utils import (
    is_query_complex,
    merge_scores,
    get_token_count,
    normalize_query
)

logger = logging.getLogger(__name__)

@dataclass
class RetrievalCandidate:
    """Represents a retrieval candidate with scores and metadata."""
    chunk_id: str
    doc_id: str
    text: str
    title: str
    section: str
    source_url: str
    vector_score: float
    bm25_score: float = 0.0
    combined_score: float = 0.0
    token_count: int = 0

class HybridRetriever:
    """Hybrid retrieval system combining vector and BM25 search."""
    
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=config.openai_api_key)
        self.pc = Pinecone(api_key=config.pinecone_api_key)
        self.index = self.pc.Index(config.pinecone_index)
        
        # BM25 corpus - will be populated from Pinecone
        self.bm25_corpus: List[str] = []
        self.bm25_metadata: List[Dict[str, Any]] = []
        self.bm25_model: Optional[BM25Okapi] = None
        self.corpus_loaded = False
        
    def rewrite_query(self, query: str) -> str:
        """Rewrite complex queries for better retrieval."""
        if not is_query_complex(query):
            return query
            
        logger.info("Query is complex, attempting rewrite")
        
        try:
            response = self.openai_client.chat.completions.create(
                model=config.model_small,
                messages=[
                    {
                        "role": "system",
                        "content": """Rewrite the user's query to be clearer and more focused for document retrieval. 
                        Break down complex questions into key search terms while preserving the core intent.
                        Keep it concise and specific. Return only the rewritten query."""
                    },
                    {
                        "role": "user",
                        "content": f"Rewrite this query: {query}"
                    }
                ],
                temperature=0,
                max_tokens=100
            )
            
            rewritten = response.choices[0].message.content.strip()
            logger.info(f"Query rewritten: '{query}' -> '{rewritten}'")
            return rewritten
            
        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}, using original query")
            return query
    
    def generate_query_embedding(self, query: str) -> List[float]:
        """Generate embedding for query."""
        try:
            response = self.openai_client.embeddings.create(
                model=config.embed_model,
                input=query
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            raise
    
    def load_bm25_corpus(self, namespace: str = None) -> None:
        """Load corpus from Pinecone for BM25 search."""
        if self.corpus_loaded:
            return
            
        if not namespace:
            namespace = config.pinecone_namespace
            
        logger.info("Loading BM25 corpus from Pinecone")
        
        try:
            # Get all vectors from Pinecone (this might need pagination for large corpora)
            # For now, we'll fetch a reasonable sample
            stats = self.index.describe_index_stats()
            total_vectors = stats.get('total_vector_count', 0)
            
            if total_vectors > 10000:
                logger.warning(f"Large corpus ({total_vectors} vectors). Consider using a subset for BM25.")
            
            # Fetch vectors in batches
            self.bm25_corpus = []
            self.bm25_metadata = []
            
            # Use query to get sample of vectors
            dummy_query = [0.0] * 1536  # Dimension for text-embedding-3-small
            results = self.index.query(
                vector=dummy_query,
                top_k=min(5000, total_vectors),  # Limit corpus size
                include_metadata=True,
                namespace=namespace
            )
            
            for match in results['matches']:
                if 'text' in match['metadata']:
                    self.bm25_corpus.append(match['metadata']['text'])
                    self.bm25_metadata.append(match['metadata'])
            
            # Create BM25 model
            if self.bm25_corpus:
                tokenized_corpus = [doc.lower().split() for doc in self.bm25_corpus]
                self.bm25_model = BM25Okapi(tokenized_corpus)
                self.corpus_loaded = True
                logger.info(f"BM25 corpus loaded with {len(self.bm25_corpus)} documents")
            else:
                logger.warning("No documents found for BM25 corpus")
                
        except Exception as e:
            logger.error(f"Failed to load BM25 corpus: {e}")
            # Continue without BM25
            self.bm25_model = None
    
    def vector_search(self, query: str, top_k: int = None, namespace: str = None) -> List[RetrievalCandidate]:
        """Perform vector search using Pinecone."""
        if not top_k:
            top_k = config.retrieval_top_k
        if not namespace:
            namespace = config.pinecone_namespace
            
        # Generate query embedding
        query_embedding = self.generate_query_embedding(query)
        
        # Search Pinecone
        try:
            results = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                namespace=namespace
            )
            
            candidates = []
            for match in results['matches']:
                metadata = match['metadata']
                
                # Ensure required fields exist
                if not all(key in metadata for key in ['text', 'source_url', 'doc_id']):
                    logger.warning(f"Skipping result with incomplete metadata: {match['id']}")
                    continue
                
                candidate = RetrievalCandidate(
                    chunk_id=match['id'],
                    doc_id=metadata.get('doc_id', ''),
                    text=metadata['text'],
                    title=metadata.get('title', ''),
                    section=metadata.get('section', ''),
                    source_url=metadata['source_url'],
                    vector_score=match['score'],
                    token_count=metadata.get('token_count', get_token_count(metadata['text']))
                )
                candidates.append(candidate)
            
            logger.info(f"Vector search returned {len(candidates)} candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise
    
    def bm25_search(self, query: str, top_k: int = None) -> List[Tuple[int, float]]:
        """Perform BM25 search on loaded corpus."""
        if not self.bm25_model or not self.bm25_corpus:
            logger.warning("BM25 model not available")
            return []
        
        if not top_k:
            top_k = config.retrieval_top_k
        
        # Tokenize query
        tokenized_query = query.lower().split()
        
        # Get BM25 scores
        scores = self.bm25_model.get_scores(tokenized_query)
        
        # Get top K indices and scores
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = [(idx, scores[idx]) for idx in top_indices if scores[idx] > 0]
        
        logger.info(f"BM25 search returned {len(results)} candidates")
        return results
    
    def merge_search_results(
        self, 
        vector_candidates: List[RetrievalCandidate],
        bm25_results: List[Tuple[int, float]],
        vector_weight: float = 0.65
    ) -> List[RetrievalCandidate]:
        """Merge vector and BM25 search results."""
        
        # Create lookup for vector candidates
        vector_lookup = {candidate.chunk_id: candidate for candidate in vector_candidates}
        
        # Add BM25 candidates
        all_candidates = {}
        
        # Add vector candidates
        for candidate in vector_candidates:
            all_candidates[candidate.chunk_id] = candidate
        
        # Add BM25 candidates
        for corpus_idx, bm25_score in bm25_results:
            if corpus_idx < len(self.bm25_metadata):
                metadata = self.bm25_metadata[corpus_idx]
                chunk_id = metadata.get('chunk_id', f"bm25_{corpus_idx}")
                
                if chunk_id in all_candidates:
                    # Update existing candidate with BM25 score
                    all_candidates[chunk_id].bm25_score = bm25_score
                else:
                    # Create new candidate from BM25
                    candidate = RetrievalCandidate(
                        chunk_id=chunk_id,
                        doc_id=metadata.get('doc_id', ''),
                        text=metadata.get('text', ''),
                        title=metadata.get('title', ''),
                        section=metadata.get('section', ''),
                        source_url=metadata.get('source_url', ''),
                        vector_score=0.0,
                        bm25_score=bm25_score,
                        token_count=metadata.get('token_count', 0)
                    )
                    all_candidates[chunk_id] = candidate
        
        # Calculate combined scores
        candidates = list(all_candidates.values())
        
        # Normalize scores to 0-1 range
        if candidates:
            vector_scores = [c.vector_score for c in candidates]
            bm25_scores = [c.bm25_score for c in candidates]
            
            max_vector = max(vector_scores) if max(vector_scores) > 0 else 1.0
            max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1.0
            
            for candidate in candidates:
                norm_vector = candidate.vector_score / max_vector
                norm_bm25 = candidate.bm25_score / max_bm25
                candidate.combined_score = merge_scores(norm_vector, norm_bm25, vector_weight)
        
        # Sort by combined score and deduplicate
        candidates.sort(key=lambda x: x.combined_score, reverse=True)
        
        # Deduplicate by doc_id + chunk_id
        seen = set()
        unique_candidates = []
        for candidate in candidates:
            key = f"{candidate.doc_id}:{candidate.chunk_id}"
            if key not in seen:
                seen.add(key)
                unique_candidates.append(candidate)
        
        # Return top 60 for reranking
        return unique_candidates[:60]
    
    def retrieve(self, query: str, namespace: str = None) -> List[RetrievalCandidate]:
        """Main retrieval function combining vector and BM25 search."""
        logger.info(f"Starting hybrid retrieval for query: '{query[:100]}...'")
        
        # Optionally rewrite query
        processed_query = self.rewrite_query(query)
        
        # Load BM25 corpus if needed
        if not self.corpus_loaded:
            self.load_bm25_corpus(namespace)
        
        # Vector search
        vector_candidates = self.vector_search(processed_query, namespace=namespace)
        
        # BM25 search
        bm25_results = self.bm25_search(processed_query)
        
        # Merge results
        merged_candidates = self.merge_search_results(vector_candidates, bm25_results)
        
        logger.info(f"Hybrid retrieval returned {len(merged_candidates)} candidates")
        return merged_candidates
    
    def get_debug_info(self) -> Dict[str, Any]:
        """Get debug information about the retriever state."""
        return {
            'corpus_loaded': self.corpus_loaded,
            'bm25_corpus_size': len(self.bm25_corpus),
            'pinecone_index': config.pinecone_index,
            'namespace': config.pinecone_namespace,
            'retrieval_top_k': config.retrieval_top_k
        }