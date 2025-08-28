"""
Cross-encoder reranking system with deduplication.
Uses sentence-transformers CrossEncoder for relevance scoring.
"""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sentence_transformers import CrossEncoder

from .config import config
from .retrieval import RetrievalCandidate

logger = logging.getLogger(__name__)

@dataclass
class RerankedCandidate:
    """Represents a reranked candidate with relevance score."""
    chunk_id: str
    doc_id: str
    text: str
    title: str
    section: str
    source_url: str
    vector_score: float
    bm25_score: float
    combined_score: float
    rerank_score: float
    token_count: int
    rank: int

class CrossEncoderReranker:
    """Cross-encoder based reranking system."""
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self.model = None
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        
    def load_model(self) -> None:
        """Lazy load the cross-encoder model."""
        if self.model is None:
            logger.info(f"Loading cross-encoder model: {self.model_name}")
            try:
                self.model = CrossEncoder(self.model_name)
                logger.info("Cross-encoder model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load cross-encoder model: {e}")
                raise
    
    def score_candidates(self, query: str, candidates: List[RetrievalCandidate]) -> List[float]:
        """Score candidates using cross-encoder."""
        if not candidates:
            return []
        
        self.load_model()
        
        # Prepare query-document pairs
        pairs = []
        for candidate in candidates:
            # Use title + section + text for richer context
            doc_text = candidate.text
            if candidate.title:
                doc_text = f"{candidate.title}. {doc_text}"
            if candidate.section:
                doc_text = f"{candidate.section}. {doc_text}"
            
            pairs.append([query, doc_text])
        
        try:
            # Get relevance scores
            scores = self.model.predict(pairs)
            
            # Convert to list if numpy array
            if hasattr(scores, 'tolist'):
                scores = scores.tolist()
            
            logger.info(f"Scored {len(candidates)} candidates with cross-encoder")
            return scores
            
        except Exception as e:
            logger.error(f"Cross-encoder scoring failed: {e}")
            # Fallback to combined scores
            return [candidate.combined_score for candidate in candidates]
    
    def deduplicate_by_similarity(
        self, 
        candidates: List[RetrievalCandidate], 
        threshold: float = 0.85
    ) -> List[RetrievalCandidate]:
        """Remove near-duplicate candidates using TF-IDF cosine similarity."""
        if len(candidates) <= 1:
            return candidates
        
        logger.info(f"Deduplicating {len(candidates)} candidates")
        
        # Extract texts for TF-IDF
        texts = [candidate.text for candidate in candidates]
        
        try:
            # Compute TF-IDF matrix
            tfidf_matrix = self.tfidf_vectorizer.fit_transform(texts)
            
            # Compute cosine similarity
            similarity_matrix = cosine_similarity(tfidf_matrix)
            
            # Find duplicates
            to_remove = set()
            for i in range(len(candidates)):
                if i in to_remove:
                    continue
                    
                for j in range(i + 1, len(candidates)):
                    if j in to_remove:
                        continue
                    
                    similarity = similarity_matrix[i, j]
                    if similarity > threshold:
                        # Keep the one with higher combined score
                        if candidates[i].combined_score >= candidates[j].combined_score:
                            to_remove.add(j)
                        else:
                            to_remove.add(i)
                            break
            
            # Filter out duplicates
            unique_candidates = [
                candidate for i, candidate in enumerate(candidates) 
                if i not in to_remove
            ]
            
            logger.info(f"Removed {len(to_remove)} duplicates, {len(unique_candidates)} remaining")
            return unique_candidates
            
        except Exception as e:
            logger.warning(f"Deduplication failed: {e}, returning original candidates")
            return candidates
    
    def rerank(
        self, 
        query: str, 
        candidates: List[RetrievalCandidate], 
        top_k: int = None
    ) -> List[RerankedCandidate]:
        """Main reranking function."""
        if not top_k:
            top_k = config.rerank_top_k
        
        logger.info(f"Reranking {len(candidates)} candidates, returning top {top_k}")
        
        if not candidates:
            return []
        
        # Deduplicate first to reduce computation
        unique_candidates = self.deduplicate_by_similarity(candidates)
        
        # Score with cross-encoder
        rerank_scores = self.score_candidates(query, unique_candidates)
        
        # Create reranked candidates
        reranked = []
        for candidate, rerank_score in zip(unique_candidates, rerank_scores):
            reranked_candidate = RerankedCandidate(
                chunk_id=candidate.chunk_id,
                doc_id=candidate.doc_id,
                text=candidate.text,
                title=candidate.title,
                section=candidate.section,
                source_url=candidate.source_url,
                vector_score=candidate.vector_score,
                bm25_score=candidate.bm25_score,
                combined_score=candidate.combined_score,
                rerank_score=float(rerank_score),
                token_count=candidate.token_count,
                rank=0  # Will be set below
            )
            reranked.append(reranked_candidate)
        
        # Sort by rerank score
        reranked.sort(key=lambda x: x.rerank_score, reverse=True)
        
        # Assign ranks and return top K
        top_candidates = reranked[:top_k]
        for i, candidate in enumerate(top_candidates):
            candidate.rank = i + 1
        
        logger.info(f"Reranking complete, returning top {len(top_candidates)} candidates")
        return top_candidates
    
    def get_debug_info(self, candidates: List[RerankedCandidate]) -> Dict[str, Any]:
        """Get debug information about reranking results."""
        if not candidates:
            return {'candidates': 0}
        
        return {
            'candidates': len(candidates),
            'model_name': self.model_name,
            'score_stats': {
                'rerank_min': min(c.rerank_score for c in candidates),
                'rerank_max': max(c.rerank_score for c in candidates),
                'rerank_mean': sum(c.rerank_score for c in candidates) / len(candidates)
            },
            'top_candidates': [
                {
                    'rank': c.rank,
                    'chunk_id': c.chunk_id,
                    'title': c.title,
                    'section': c.section,
                    'rerank_score': round(c.rerank_score, 4),
                    'combined_score': round(c.combined_score, 4),
                    'text_preview': c.text[:100] + "..." if len(c.text) > 100 else c.text
                }
                for c in candidates[:5]  # Top 5 for debug
            ]


# Global reranker instance
reranker = CrossEncoderReranker()
        }