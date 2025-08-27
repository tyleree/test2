"""
Main RAG pipeline orchestration with multi-layer semantic caching.

Cost Math (target budgets):
- Small model: ~300-600 tokens in/out total (rewrite + compress)  
- Big model: ~1.8-2.3k input, ~300-700 output
- Cache saves: ~2x full pipeline cost when semantic hit
"""

import logging
import time
import json
from typing import Dict, Any

from .settings import settings
from .schemas import AnswerPayload, TokenUsage, CompressedPack
from .utils import normalize_query, hash_string, count_tokens, estimate_tokens_saved
from .cache_simple import cache
from .retrieval_simple import retriever
from .rerank_simple import reranker
from .compress import compressor
from .answer import answer_generator
from .validators import validator, UseCache
from .metrics import metrics

logger = logging.getLogger(__name__)


class RAGPipeline:
    """Main RAG pipeline with multi-layer semantic caching."""
    
    def __init__(self):
        self.metrics = metrics
    
    async def answer_question(self, question: str, detail_level: str = None) -> AnswerPayload:
        """
        Main pipeline entry point.
        
        Args:
            question: User question
            detail_level: Optional detail level ('more' for expanded context)
        
        Returns:
            AnswerPayload with answer, citations, cache info, and metrics
        """
        start_time = time.time()
        
        # Normalize query for consistent caching
        q_norm = normalize_query(question)
        q_hash = hash_string(q_norm)
        
        logger.info(f"Processing question: {question[:100]}...")
        
        try:
            # Step 1: Check exact cache hit
            exact_hit = cache.get_exact(q_hash)
            if exact_hit:
                logger.info("Exact cache hit found")
                cache.touch(exact_hit.id)
                
                result = self._build_response_from_cache(
                    exact_hit, "exact", start_time
                )
                self.metrics.record_cache_hit("exact")
                return result
            
            # Step 2: Check semantic cache
            semantic_result = await self._check_semantic_cache(q_norm, q_hash)
            if semantic_result:
                logger.info("Semantic cache hit found and validated")
                result = self._build_response_from_cache(
                    semantic_result, "semantic", start_time
                )
                self.metrics.record_cache_hit("semantic")
                return result
            
            # Step 3: Full pipeline execution
            logger.info("Cache miss - executing full pipeline")
            result = await self._execute_full_pipeline(
                question, q_norm, q_hash, detail_level, start_time
            )
            
            self.metrics.record_cache_miss()
            return result
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            return self._build_error_response(str(e), start_time)
    
    async def _check_semantic_cache(self, q_norm: str, q_hash: str) -> Any:
        """Check semantic cache with validation."""
        try:
            # Generate embedding for semantic search
            embedding = cache.embed_query_for_cache(q_norm)
            
            # Search for semantic hits
            semantic_hits = cache.get_semantic_hits(embedding, top_n=10)
            
            # Iterate through hits by descending similarity
            for cache_id, similarity in semantic_hits:
                if similarity >= settings.sim_threshold:
                    # Get cache entry
                    cached_entry = cache.get_cache_entry_by_id(cache_id)
                    if not cached_entry:
                        continue
                    
                    # Validate cache entry
                    validation_result = validator.validate_semantic_cache_hit(
                        cached_entry, q_norm
                    )
                    
                    if validation_result == UseCache.OK:
                        # Touch cache entry and return
                        cache.touch(cache_id)
                        logger.info(f"Semantic cache hit validated: similarity={similarity:.3f}")
                        return cached_entry
                    else:
                        logger.info(f"Semantic cache hit failed validation: similarity={similarity:.3f}")
            
            return None
            
        except Exception as e:
            logger.error(f"Semantic cache check failed: {e}")
            return None
    
    async def _execute_full_pipeline(
        self, 
        question: str, 
        q_norm: str, 
        q_hash: str, 
        detail_level: str,
        start_time: float
    ) -> AnswerPayload:
        """Execute the full RAG pipeline."""
        
        # Adjust compression budget for detail level
        compress_budget = settings.compress_budget_tokens
        if detail_level == "more":
            compress_budget = int(compress_budget * 1.5)  # 50% more context
        
        # Step 1: Retrieve relevant documents
        logger.info("Step 1: Retrieving documents")
        retrieved_docs = retriever.retrieve_top_chunks(
            question, 
            k=settings.retrieve_k,
            use_query_expansion=True
        )
        
        if not retrieved_docs:
            return self._build_no_results_response(start_time)
        
        # Step 2: Rerank documents
        logger.info(f"Step 2: Reranking {len(retrieved_docs)} documents")
        reranked_docs = reranker.rerank_documents(
            question, 
            retrieved_docs, 
            top_k=settings.rerank_k
        )
        
        # Step 3: Compress context
        logger.info(f"Step 3: Compressing {len(reranked_docs)} documents")
        compressed_pack = compressor.compress_context(
            question, 
            reranked_docs, 
            max_tokens=compress_budget
        )
        
        # Step 4: Generate answer
        logger.info("Step 4: Generating answer")
        answer, citations, token_usage_info = answer_generator.generate_answer(
            question, 
            compressed_pack,
            max_tokens=700 if detail_level != "more" else 1000
        )
        
        # Step 5: Create token usage object
        token_usage = TokenUsage(
            model_big=settings.model_big,
            model_small=settings.model_small,
            tokens_big=token_usage_info.get('total_tokens', 0),
            tokens_small=0,  # TODO: Track small model usage from compression
            total_tokens=token_usage_info.get('total_tokens', 0)
        )
        
        # Step 6: Cache the result
        doc_version_hash = validator._generate_current_version_hash()
        embedding = cache.embed_query_for_cache(q_norm)
        
        cache.record_answer(
            normalized_query=q_norm,
            q_hash=q_hash,
            embedding=embedding,
            answer=answer,
            citations=[c.dict() for c in citations],
            compressed_pack=compressed_pack.dict(),
            top_doc_ids=compressed_pack.top_doc_ids,
            token_usage=token_usage,
            doc_version_hash=doc_version_hash
        )
        
        # Step 7: Build response
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Record metrics
        self.metrics.record_request(
            cache_mode="miss",
            latency_ms=latency_ms,
            tokens_big=token_usage.tokens_big,
            tokens_small=token_usage.tokens_small
        )
        
        return AnswerPayload(
            answer=answer,
            citations=citations,
            cache_mode="miss",
            token_usage=token_usage,
            latency_ms=latency_ms
        )
    
    def _build_response_from_cache(
        self, 
        cached_entry: Any, 
        cache_mode: str, 
        start_time: float
    ) -> AnswerPayload:
        """Build response from cached entry."""
        try:
            import json
            
            # Parse cached data
            citations_data = json.loads(cached_entry.citations_json)
            token_cost_data = json.loads(cached_entry.token_cost_json)
            
            # Recreate citations
            from .schemas import Citation
            citations = [Citation(**c) for c in citations_data]
            
            # Recreate token usage
            token_usage = TokenUsage(**token_cost_data)
            
            # Estimate tokens saved
            original_tokens = token_usage.total_tokens
            token_usage.saved_tokens_estimate = estimate_tokens_saved(original_tokens, 50)  # Minimal cache lookup cost
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Record metrics
            self.metrics.record_request(
                cache_mode=cache_mode,
                latency_ms=latency_ms,
                tokens_big=0,  # No tokens used for cache hit
                tokens_small=0,
                saved_tokens=token_usage.saved_tokens_estimate
            )
            
            return AnswerPayload(
                answer=cached_entry.answer,
                citations=citations,
                cache_mode=cache_mode,
                token_usage=token_usage,
                latency_ms=latency_ms
            )
            
        except Exception as e:
            logger.error(f"Error building cache response: {e}")
            return self._build_error_response("Cache response error", start_time)
    
    def _build_no_results_response(self, start_time: float) -> AnswerPayload:
        """Build response when no relevant documents found."""
        latency_ms = int((time.time() - start_time) * 1000)
        
        token_usage = TokenUsage(
            model_big=settings.model_big,
            model_small=settings.model_small,
            tokens_big=0,
            tokens_small=0,
            total_tokens=0
        )
        
        return AnswerPayload(
            answer="I don't have enough information in the indexed sources to answer that question.",
            citations=[],
            cache_mode="miss",
            token_usage=token_usage,
            latency_ms=latency_ms
        )
    
    def _build_error_response(self, error_msg: str, start_time: float) -> AnswerPayload:
        """Build error response."""
        latency_ms = int((time.time() - start_time) * 1000)
        
        token_usage = TokenUsage(
            model_big=settings.model_big,
            model_small=settings.model_small,
            tokens_big=0,
            tokens_small=0,
            total_tokens=0
        )
        
        return AnswerPayload(
            answer=f"I apologize, but I encountered an error while processing your question: {error_msg}",
            citations=[],
            cache_mode="miss",
            token_usage=token_usage,
            latency_ms=latency_ms
        )
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        cache_stats = cache.get_stats()
        validation_stats = validator.get_validation_stats()
        
        return {
            "cache": cache_stats,
            "validation": validation_stats,
            "settings": {
                "sim_threshold": settings.sim_threshold,
                "doc_overlap_min": settings.doc_overlap_min,
                "max_sources": settings.max_sources,
                "retrieve_k": settings.retrieve_k,
                "rerank_k": settings.rerank_k,
                "compress_budget_tokens": settings.compress_budget_tokens
            }
        }


# Global pipeline instance
pipeline = RAGPipeline()

