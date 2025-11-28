"""
RAG Pipeline for Veterans Benefits AI

This module implements the complete RAG (Retrieval-Augmented Generation) pipeline
using OpenAI for both embeddings and chat completions, with an in-memory vector store.

Flow:
1. User Query -> Check Response Cache (exact + semantic)
2. Cache Miss -> Query Embedding (with embedding cache)
3. Embedding -> Vector Store Search (Top-K chunks)
4. Chunks -> Model Routing (simple vs complex)
5. Prompt -> OpenAI Chat Completion (streaming supported)
6. Response -> Cache + Return

Features:
- Response caching (exact + semantic) for <50ms cache hits
- Streaming responses for better UX
- Intelligent model routing for cost optimization
- File-backed embedding cache with compression

This replaces the Pinecone-based rag_system.py with a self-contained solution.
"""

import os
import json
import time
from typing import List, Dict, Any, Optional, Tuple, Generator, Iterator
from dataclasses import dataclass
from pathlib import Path
from openai import OpenAI

from src.vector_store import (
    InMemoryVectorStore, 
    get_vector_store, 
    initialize_vector_store,
    SearchResult
)
from src.embeddings import (
    get_or_create_embeddings,
    embed_query_cached,
    DEFAULT_EMBEDDING_MODEL
)
from src.prompts import (
    build_rag_prompt,
    extract_sources_from_chunks,
    build_query_expansion_prompt
)
from src.response_cache import (
    get_response_cache,
    get_cached_response,
    cache_response,
    ResponseCache
)
from src.url_validator import (
    initialize_url_validator,
    validate_sources,
    sanitize_response_urls,
    is_valid_url,
    get_whitelist_stats
)
from src.citation_verifier import (
    verify_citations,
    get_verification_summary,
    VerificationResult
)

# Configuration
DEFAULT_CHAT_MODEL = "gpt-4.1-mini"
PREMIUM_CHAT_MODEL = "gpt-4.1"  # More capable model for complex queries
DEFAULT_TOP_K = 7
DEFAULT_MIN_SCORE = 0.45  # Increased from 0.3 - reject low-relevance chunks
CORPUS_PATH = "veteran-ai-spark/corpus/vbkb_restructured.json"
EMBEDDINGS_CACHE_PATH = "data/embeddings_cache.json"

# Relevance thresholds for hallucination prevention
WEAK_RETRIEVAL_THRESHOLD = 0.55  # Log warning if best chunk is below this
VERY_WEAK_THRESHOLD = 0.45  # Consider adding "I'm not sure" prefix if below this

# Model routing thresholds
SIMPLE_QUERY_MAX_WORDS = 15  # Queries with fewer words are likely simple
COMPLEX_CONTEXT_THRESHOLD = 3000  # Context chars above this suggests complexity
COMPLEX_CHUNKS_THRESHOLD = 5  # More chunks retrieved suggests complex topic
HIGH_SCORE_THRESHOLD = 0.7  # High similarity = likely simple FAQ match

# Keywords that suggest complex queries needing the premium model
COMPLEX_QUERY_INDICATORS = [
    "compare", "comparison", "difference between", "versus", "vs",
    "explain in detail", "comprehensive", "thoroughly",
    "multiple conditions", "combined rating", "bilateral",
    "secondary condition", "aggravation", "nexus",
    "appeal", "higher level review", "board",
    "tdiu", "individual unemployability",
    "presumptive", "agent orange", "burn pit",
    "effective date", "back pay", "retro",
]

# Keywords that suggest simple FAQ-style queries (use cheap model)
SIMPLE_QUERY_INDICATORS = [
    "what is", "how do i", "where can i", "when can i",
    "how to file", "how to apply", "what forms",
    "phone number", "address", "contact",
    "how long", "how much", "what percent",
]


@dataclass
class RAGResponse:
    """Response from the RAG pipeline."""
    answer: str
    sources: List[Dict[str, Any]]
    query_time_ms: float
    chunks_retrieved: int
    model_used: str
    routing_reason: Optional[str] = None
    cache_hit: Optional[str] = None  # "exact", "semantic", or None
    error: Optional[str] = None
    weak_retrieval: bool = False  # True if best chunk score was below threshold
    citation_verification: Optional[Dict[str, Any]] = None  # Citation verification results
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "answer": self.answer,
            "sources": self.sources,
            "metadata": {
                "query_time_ms": self.query_time_ms,
                "chunks_retrieved": self.chunks_retrieved,
                "model_used": self.model_used,
                "model_tier": "premium" if "4.1" in self.model_used and "mini" not in self.model_used else "standard"
            }
        }
        if self.routing_reason:
            result["metadata"]["routing_reason"] = self.routing_reason
        if self.cache_hit:
            result["metadata"]["cache_hit"] = self.cache_hit
        if self.weak_retrieval:
            result["metadata"]["weak_retrieval"] = True
        if self.citation_verification:
            result["metadata"]["citation_verification"] = self.citation_verification
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class StreamChunk:
    """A chunk of streaming response."""
    content: str
    is_final: bool = False
    sources: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class RAGPipeline:
    """
    Complete RAG pipeline using OpenAI embeddings and chat completions.
    
    Usage:
        pipeline = RAGPipeline()
        pipeline.initialize()  # Load corpus and embeddings
        response = pipeline.ask("What is the rating for PTSD?")
    """
    
    def __init__(
        self,
        corpus_path: str = CORPUS_PATH,
        embeddings_cache_path: str = EMBEDDINGS_CACHE_PATH,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        chat_model: str = DEFAULT_CHAT_MODEL,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
        enable_response_cache: bool = True
    ):
        self.corpus_path = corpus_path
        self.embeddings_cache_path = embeddings_cache_path
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.top_k = top_k
        self.min_score = min_score
        self.enable_response_cache = enable_response_cache
        
        self.vector_store: Optional[InMemoryVectorStore] = None
        self.openai_client: Optional[OpenAI] = None
        self.response_cache: Optional[ResponseCache] = None
        self._is_initialized = False
    
    def initialize(self, force_regenerate_embeddings: bool = False) -> bool:
        """
        Initialize the RAG pipeline by loading corpus and embeddings.
        
        Args:
            force_regenerate_embeddings: If True, regenerate embeddings even if cached
            
        Returns:
            True if initialization was successful
        """
        print("[START] Initializing RAG Pipeline...")
        start_time = time.time()
        
        try:
            # Initialize OpenAI client
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self.openai_client = OpenAI(api_key=api_key)
            print("[OK] OpenAI client initialized")
            
            # Load corpus
            corpus_path = Path(self.corpus_path)
            if not corpus_path.exists():
                raise FileNotFoundError(f"Corpus file not found: {self.corpus_path}")
            
            with open(corpus_path, 'r', encoding='utf-8') as f:
                corpus_data = json.load(f)
            print(f"[LOAD] Loaded {len(corpus_data)} chunks from corpus")
            
            # Build documents dict for embeddings
            documents = {}
            for item in corpus_data:
                doc_id = item.get("entry_id", "")
                content = item.get("content", "")
                if doc_id and content:
                    # Include topic in the text for better semantic matching
                    topic = item.get("topic", "")
                    if topic:
                        content = f"{topic}\n\n{content}"
                    documents[doc_id] = content
            
            print(f"[NOTE] Prepared {len(documents)} documents for embedding")
            
            # Get or create embeddings
            embeddings = get_or_create_embeddings(
                documents,
                self.embeddings_cache_path,
                self.embedding_model,
                force_regenerate=force_regenerate_embeddings
            )
            
            # Initialize vector store
            self.vector_store = get_vector_store()
            self.vector_store.load_corpus(self.corpus_path)
            self.vector_store.set_embeddings(embeddings)
            
            # Initialize response cache
            if self.enable_response_cache:
                self.response_cache = get_response_cache()
                print(f"[OK] Response cache initialized")
            
            # Initialize URL validator with corpus URLs
            initialize_url_validator(self.corpus_path)
            whitelist_stats = get_whitelist_stats()
            print(f"[OK] URL validator initialized with {whitelist_stats['total_urls']} known URLs")
            
            self._is_initialized = True
            
            elapsed = time.time() - start_time
            print(f"[OK] RAG Pipeline initialized in {elapsed:.2f}s")
            print(f"   - Documents: {len(self.vector_store)}")
            print(f"   - Embedding model: {self.embedding_model}")
            print(f"   - Chat model: {self.chat_model}")
            print(f"   - Response caching: {'enabled' if self.enable_response_cache else 'disabled'}")
            print(f"   - URL validation: enabled ({whitelist_stats['unique_base_urls']} base URLs)")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] RAG Pipeline initialization failed: {e}")
            self._is_initialized = False
            raise
    
    @property
    def is_ready(self) -> bool:
        """Check if the pipeline is ready for queries."""
        return (
            self._is_initialized and 
            self.vector_store is not None and 
            self.vector_store.is_ready and
            self.openai_client is not None
        )
    
    def _classify_query_complexity(
        self,
        query: str,
        chunks: List[Dict[str, Any]]
    ) -> Tuple[str, str]:
        """
        Classify query complexity and select appropriate model.
        
        This implements smart model routing:
        - Simple FAQ-style queries -> cheap model (gpt-4.1-mini)
        - Complex queries needing precision -> premium model (gpt-4.1)
        
        Args:
            query: User's question
            chunks: Retrieved context chunks
            
        Returns:
            Tuple of (selected_model, routing_reason)
        """
        query_lower = query.lower().strip()
        word_count = len(query.split())
        
        # Calculate context size
        total_context_chars = sum(len(c.get("text", "")) for c in chunks)
        num_chunks = len(chunks)
        avg_score = sum(c.get("score", 0) for c in chunks) / max(num_chunks, 1)
        
        # Check for complex query indicators
        has_complex_indicators = any(
            indicator in query_lower 
            for indicator in COMPLEX_QUERY_INDICATORS
        )
        
        # Check for simple query indicators
        has_simple_indicators = any(
            indicator in query_lower 
            for indicator in SIMPLE_QUERY_INDICATORS
        )
        
        # Decision logic for model routing
        
        # 1. Explicit complex indicators -> use premium model
        if has_complex_indicators:
            return PREMIUM_CHAT_MODEL, "complex_query_detected"
        
        # 2. Very high similarity score + simple indicators -> cheap model is fine
        if avg_score > HIGH_SCORE_THRESHOLD and has_simple_indicators:
            return DEFAULT_CHAT_MODEL, "high_confidence_simple_match"
        
        # 3. Short query + few chunks + high scores -> simple FAQ, use cheap model
        if (word_count <= SIMPLE_QUERY_MAX_WORDS and 
            num_chunks <= COMPLEX_CHUNKS_THRESHOLD and 
            avg_score > 0.5):
            return DEFAULT_CHAT_MODEL, "simple_faq_query"
        
        # 4. Large context retrieved -> might need better reasoning
        if total_context_chars > COMPLEX_CONTEXT_THRESHOLD:
            return PREMIUM_CHAT_MODEL, "large_context_needs_synthesis"
        
        # 5. Many chunks retrieved -> complex topic
        if num_chunks > COMPLEX_CHUNKS_THRESHOLD:
            return PREMIUM_CHAT_MODEL, "multi_source_complexity"
        
        # 6. Long query with multiple parts -> likely complex
        if word_count > 25 or query.count("?") > 1 or " and " in query_lower:
            return PREMIUM_CHAT_MODEL, "multi_part_query"
        
        # 7. Low confidence scores -> need better reasoning
        if avg_score < 0.4:
            return PREMIUM_CHAT_MODEL, "low_confidence_needs_reasoning"
        
        # Default: use cheap model for cost efficiency
        return DEFAULT_CHAT_MODEL, "default_simple"
    
    def _retrieve_context(self, query: str) -> Tuple[List[Dict[str, Any]], float, bool]:
        """
        Retrieve relevant context chunks for a query with hallucination prevention.
        
        Args:
            query: User's question
            
        Returns:
            Tuple of (chunks list, retrieval time in ms, weak_retrieval flag)
        """
        start_time = time.time()
        
        # Generate query embedding
        query_embedding = embed_query_cached(query, self.embedding_model)
        
        # Search vector store
        results: List[SearchResult] = self.vector_store.search(
            query_embedding,
            k=self.top_k,
            min_score=self.min_score
        )
        
        # Convert to chunk dicts
        chunks = []
        for result in results:
            chunks.append({
                "id": result.document.id,
                "text": result.document.text,
                "metadata": result.document.metadata,
                "score": result.score
            })
        
        # Check for weak retrieval (hallucination risk)
        weak_retrieval = False
        if chunks:
            best_score = chunks[0]["score"]
            if best_score < WEAK_RETRIEVAL_THRESHOLD:
                print(f"[WARN] Weak retrieval for query: '{query[:80]}...' (best_score={best_score:.3f})")
                weak_retrieval = True
                if best_score < VERY_WEAK_THRESHOLD:
                    print(f"[WARN] Very weak retrieval - high hallucination risk!")
        else:
            print(f"[WARN] No chunks found for query: '{query[:80]}...'")
            weak_retrieval = True
        
        elapsed_ms = (time.time() - start_time) * 1000
        return chunks, elapsed_ms, weak_retrieval
    
    def _generate_response(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None
    ) -> Tuple[str, float, str]:
        """
        Generate a response using OpenAI chat completion.
        
        Args:
            question: User's question
            context_chunks: Retrieved context chunks
            conversation_history: Optional conversation history
            model: Specific model to use (overrides default)
            
        Returns:
            Tuple of (answer text, generation time in ms, model used)
        """
        start_time = time.time()
        
        # Use specified model or fall back to instance default
        selected_model = model or self.chat_model
        
        # Build prompt
        messages = build_rag_prompt(
            question,
            context_chunks,
            conversation_history
        )
        
        # Call OpenAI
        response = self.openai_client.chat.completions.create(
            model=selected_model,
            messages=messages,
            temperature=0.3,  # Lower temperature for more factual responses
            max_tokens=1500
        )
        
        answer = response.choices[0].message.content
        elapsed_ms = (time.time() - start_time) * 1000
        
        return answer, elapsed_ms, selected_model
    
    def _generate_response_streaming(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None
    ) -> Generator[str, None, str]:
        """
        Generate a streaming response using OpenAI chat completion.
        
        Args:
            question: User's question
            context_chunks: Retrieved context chunks
            conversation_history: Optional conversation history
            model: Specific model to use (overrides default)
            
        Yields:
            Token strings as they arrive
            
        Returns:
            Complete response text
        """
        # Use specified model or fall back to instance default
        selected_model = model or self.chat_model
        
        # Build prompt
        messages = build_rag_prompt(
            question,
            context_chunks,
            conversation_history
        )
        
        # Call OpenAI with streaming
        stream = self.openai_client.chat.completions.create(
            model=selected_model,
            messages=messages,
            temperature=0.3,
            max_tokens=1500,
            stream=True
        )
        
        # Collect full response while streaming
        full_response = []
        for chunk in stream:
            if chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response.append(token)
                yield token
        
        return "".join(full_response)
    
    def ask_streaming(
        self,
        question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        force_model: Optional[str] = None
    ) -> Generator[StreamChunk, None, None]:
        """
        Ask a question and stream the response.
        
        Uses intelligent model routing and response caching.
        If cache hit, yields complete response immediately.
        Otherwise, streams tokens as they arrive from the LLM.
        
        Args:
            question: User's question
            conversation_history: Optional list of previous messages
            force_model: Optional model override (bypasses routing)
            
        Yields:
            StreamChunk objects with content and metadata
        """
        if not self.is_ready:
            yield StreamChunk(
                content="",
                is_final=True,
                error="RAG pipeline not initialized. Please try again later."
            )
            return
        
        total_start = time.time()
        
        try:
            # Generate query embedding for cache lookup and retrieval
            query_embedding = embed_query_cached(question, self.embedding_model)
            
            # Check response cache first
            if self.response_cache and self.enable_response_cache:
                cached = self.response_cache.get(question, query_embedding)
                if cached:
                    response_text, sources, model_used, cache_type = cached
                    # Return cached response immediately
                    yield StreamChunk(
                        content=response_text,
                        is_final=True,
                        sources=sources,
                        metadata={
                            "query_time_ms": (time.time() - total_start) * 1000,
                            "cache_hit": cache_type,
                            "model_used": model_used
                        }
                    )
                    return
            
            # Cache miss - proceed with retrieval
            chunks, retrieval_time, weak_retrieval = self._retrieve_context(question)
            
            if not chunks:
                yield StreamChunk(
                    content="I couldn't find any relevant information in my knowledge base to answer your question. Please try rephrasing your question or ask about a specific VA benefit or condition.",
                    is_final=True,
                    sources=[],
                    metadata={"query_time_ms": (time.time() - total_start) * 1000, "weak_retrieval": True}
                )
                return
            
            # Model routing
            if force_model:
                selected_model = force_model
                routing_reason = "forced_override"
            else:
                selected_model, routing_reason = self._classify_query_complexity(question, chunks)
            
            print(f"[ROUTER] Model: {selected_model} (reason: {routing_reason})")
            
            # Extract and validate sources
            sources = extract_sources_from_chunks(chunks)
            sources = validate_sources(sources)  # URL validation
            
            # Stream the response
            response_tokens = []
            for token in self._generate_response_streaming(
                question, chunks, conversation_history, model=selected_model
            ):
                response_tokens.append(token)
                yield StreamChunk(content=token, is_final=False)
            
            full_response = "".join(response_tokens)
            total_time = (time.time() - total_start) * 1000
            
            # Cache the response
            if self.response_cache and self.enable_response_cache:
                self.response_cache.set(
                    question,
                    full_response,
                    sources,
                    selected_model,
                    query_embedding
                )
            
            # Send final chunk with metadata
            yield StreamChunk(
                content="",
                is_final=True,
                sources=sources,
                metadata={
                    "query_time_ms": total_time,
                    "chunks_retrieved": len(chunks),
                    "model_used": selected_model,
                    "routing_reason": routing_reason
                }
            )
            
        except Exception as e:
            print(f"[ERROR] RAG Pipeline streaming error: {e}")
            yield StreamChunk(
                content="",
                is_final=True,
                error=str(e)
            )
    
    def ask(
        self,
        question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        force_model: Optional[str] = None
    ) -> RAGResponse:
        """
        Ask a question and get an answer with sources.
        
        Uses intelligent model routing to select the appropriate model:
        - Simple FAQ-style queries -> cheap model (gpt-4.1-mini)
        - Complex queries needing precision -> premium model (gpt-4.1)
        
        Args:
            question: User's question
            conversation_history: Optional list of previous messages
            force_model: Optional model override (bypasses routing)
            
        Returns:
            RAGResponse with answer, sources, and metadata
        """
        if not self.is_ready:
            return RAGResponse(
                answer="",
                sources=[],
                query_time_ms=0,
                chunks_retrieved=0,
                model_used=self.chat_model,
                error="RAG pipeline not initialized. Please try again later."
            )
        
        total_start = time.time()
        
        try:
            # Step 0: Generate query embedding for cache lookup
            query_embedding = embed_query_cached(question, self.embedding_model)
            
            # Step 1: Check response cache
            if self.response_cache and self.enable_response_cache:
                cached = self.response_cache.get(question, query_embedding)
                if cached:
                    response_text, sources, model_used, cache_type = cached
                    return RAGResponse(
                        answer=response_text,
                        sources=sources,
                        query_time_ms=(time.time() - total_start) * 1000,
                        chunks_retrieved=0,  # From cache, no retrieval
                        model_used=model_used,
                        cache_hit=cache_type
                    )
            
            # Step 2: Retrieve context (cache miss)
            chunks, retrieval_time, weak_retrieval = self._retrieve_context(question)
            
            if not chunks:
                return RAGResponse(
                    answer="I couldn't find any relevant information in my knowledge base to answer your question. Please try rephrasing your question or ask about a specific VA benefit or condition.",
                    sources=[],
                    query_time_ms=(time.time() - total_start) * 1000,
                    chunks_retrieved=0,
                    model_used=self.chat_model,
                    routing_reason="no_context"
                )
            
            # Flag weak retrievals for monitoring
            if weak_retrieval:
                print(f"[HALLUCINATION_RISK] Proceeding with weak retrieval - best score below {WEAK_RETRIEVAL_THRESHOLD}")
            
            # Step 3: Model routing - select appropriate model based on query complexity
            if force_model:
                selected_model = force_model
                routing_reason = "forced_override"
            else:
                selected_model, routing_reason = self._classify_query_complexity(question, chunks)
            
            print(f"[ROUTER] Model: {selected_model} (reason: {routing_reason})")
            
            # Step 4: Generate response with selected model
            answer, generation_time, model_used = self._generate_response(
                question,
                chunks,
                conversation_history,
                model=selected_model
            )
            
            # Step 5: Extract and validate sources
            sources = extract_sources_from_chunks(chunks)
            sources = validate_sources(sources)  # URL validation
            
            # Step 6: Verify citations (hallucination detection)
            verification_result = verify_citations(answer, chunks)
            verification_summary = get_verification_summary(verification_result)
            
            if verification_result.suspicious_citations > 0:
                print(f"[CITATION_CHECK] {verification_result.suspicious_citations} suspicious citations detected")
                for issue in verification_result.overall_issues:
                    print(f"  - {issue}")
            
            total_time = (time.time() - total_start) * 1000
            
            # Step 7: Cache the response
            if self.response_cache and self.enable_response_cache:
                self.response_cache.set(
                    question,
                    answer,
                    sources,
                    model_used,
                    query_embedding
                )
            
            return RAGResponse(
                answer=answer,
                sources=sources,
                query_time_ms=total_time,
                chunks_retrieved=len(chunks),
                model_used=model_used,
                routing_reason=routing_reason,
                weak_retrieval=weak_retrieval,
                citation_verification=verification_summary
            )
            
        except Exception as e:
            print(f"[ERROR] RAG Pipeline error: {e}")
            return RAGResponse(
                answer="I'm sorry, I encountered an error while processing your question. Please try again.",
                sources=[],
                query_time_ms=(time.time() - total_start) * 1000,
                chunks_retrieved=0,
                model_used=self.chat_model,
                error=str(e)
            )
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific chunk by its ID.
        
        Args:
            chunk_id: The document/chunk ID
            
        Returns:
            Chunk dict with text and metadata, or None if not found
        """
        if not self.vector_store:
            return None
        
        doc = self.vector_store.get_document(chunk_id)
        if not doc:
            return None
        
        return {
            "id": doc.id,
            "text": doc.text,
            "metadata": doc.metadata
        }
    
    def get_cache_metrics(self) -> Dict[str, Any]:
        """Get response cache metrics."""
        if self.response_cache:
            return self.response_cache.get_metrics()
        return {"caching": "disabled"}
    
    def clear_cache(self) -> None:
        """Clear the response cache."""
        if self.response_cache:
            self.response_cache.clear()
            print("[CACHE] Response cache cleared")


# Global pipeline instance
_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline() -> RAGPipeline:
    """Get or create the global RAG pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline


def initialize_rag_pipeline(force_regenerate: bool = False) -> RAGPipeline:
    """Initialize the global RAG pipeline."""
    pipeline = get_rag_pipeline()
    if not pipeline.is_ready or force_regenerate:
        pipeline.initialize(force_regenerate_embeddings=force_regenerate)
    return pipeline


def ask_question(
    question: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Convenience function to ask a question using the global pipeline.
    
    Args:
        question: User's question
        history: Optional conversation history
        
    Returns:
        Dict with 'answer', 'sources', and optional 'error'
    """
    pipeline = get_rag_pipeline()
    if not pipeline.is_ready:
        return {
            "answer": "",
            "sources": [],
            "error": "RAG system not initialized"
        }
    
    response = pipeline.ask(question, history)
    return response.to_dict()


def ask_question_streaming(
    question: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Generator[StreamChunk, None, None]:
    """
    Convenience function to stream a response using the global pipeline.
    
    Args:
        question: User's question
        history: Optional conversation history
        
    Yields:
        StreamChunk objects with content and metadata
    """
    pipeline = get_rag_pipeline()
    if not pipeline.is_ready:
        yield StreamChunk(
            content="",
            is_final=True,
            error="RAG system not initialized"
        )
        return
    
    yield from pipeline.ask_streaming(question, history)


def get_cache_metrics() -> Dict[str, Any]:
    """Get response cache metrics from the global pipeline."""
    pipeline = get_rag_pipeline()
    return pipeline.get_cache_metrics()
