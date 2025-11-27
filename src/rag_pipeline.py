"""
RAG Pipeline for Veterans Benefits AI

This module implements the complete RAG (Retrieval-Augmented Generation) pipeline
using OpenAI for both embeddings and chat completions, with an in-memory vector store.

Flow:
1. User Query -> Query Preprocessing
2. Query -> OpenAI Embedding
3. Embedding -> Vector Store Search (Top-K chunks)
4. Chunks -> Prompt Building (with citations)
5. Prompt -> OpenAI Chat Completion
6. Response -> Answer + Sources

This replaces the Pinecone-based rag_system.py with a self-contained solution.
"""

import os
import json
import time
from typing import List, Dict, Any, Optional, Tuple
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

# Configuration
DEFAULT_CHAT_MODEL = "gpt-4.1-mini"
DEFAULT_TOP_K = 7
DEFAULT_MIN_SCORE = 0.3
CORPUS_PATH = "veteran-ai-spark/corpus/vbkb_restructured.json"
EMBEDDINGS_CACHE_PATH = "data/embeddings_cache.json"


@dataclass
class RAGResponse:
    """Response from the RAG pipeline."""
    answer: str
    sources: List[Dict[str, Any]]
    query_time_ms: float
    chunks_retrieved: int
    model_used: str
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "answer": self.answer,
            "sources": self.sources,
            "metadata": {
                "query_time_ms": self.query_time_ms,
                "chunks_retrieved": self.chunks_retrieved,
                "model_used": self.model_used
            }
        }
        if self.error:
            result["error"] = self.error
        return result


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
        min_score: float = DEFAULT_MIN_SCORE
    ):
        self.corpus_path = corpus_path
        self.embeddings_cache_path = embeddings_cache_path
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.top_k = top_k
        self.min_score = min_score
        
        self.vector_store: Optional[InMemoryVectorStore] = None
        self.openai_client: Optional[OpenAI] = None
        self._is_initialized = False
    
    def initialize(self, force_regenerate_embeddings: bool = False) -> bool:
        """
        Initialize the RAG pipeline by loading corpus and embeddings.
        
        Args:
            force_regenerate_embeddings: If True, regenerate embeddings even if cached
            
        Returns:
            True if initialization was successful
        """
        print("\ud83d\ude80 Initializing RAG Pipeline...")
        start_time = time.time()
        
        try:
            # Initialize OpenAI client
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self.openai_client = OpenAI(api_key=api_key)
            print("\u2705 OpenAI client initialized")
            
            # Load corpus
            corpus_path = Path(self.corpus_path)
            if not corpus_path.exists():
                raise FileNotFoundError(f"Corpus file not found: {self.corpus_path}")
            
            with open(corpus_path, 'r', encoding='utf-8') as f:
                corpus_data = json.load(f)
            print(f"\ud83d\udcda Loaded {len(corpus_data)} chunks from corpus")
            
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
            
            print(f"\ud83d\udcdd Prepared {len(documents)} documents for embedding")
            
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
            
            self._is_initialized = True
            
            elapsed = time.time() - start_time
            print(f"\u2705 RAG Pipeline initialized in {elapsed:.2f}s")
            print(f"   - Documents: {len(self.vector_store)}")
            print(f"   - Embedding model: {self.embedding_model}")
            print(f"   - Chat model: {self.chat_model}")
            
            return True
            
        except Exception as e:
            print(f"\u274c RAG Pipeline initialization failed: {e}")
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
    
    def _retrieve_context(self, query: str) -> Tuple[List[Dict[str, Any]], float]:
        """
        Retrieve relevant context chunks for a query.
        
        Args:
            query: User's question
            
        Returns:
            Tuple of (chunks list, retrieval time in ms)
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
        
        elapsed_ms = (time.time() - start_time) * 1000
        return chunks, elapsed_ms
    
    def _generate_response(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, float]:
        """
        Generate a response using OpenAI chat completion.
        
        Args:
            question: User's question
            context_chunks: Retrieved context chunks
            conversation_history: Optional conversation history
            
        Returns:
            Tuple of (answer text, generation time in ms)
        """
        start_time = time.time()
        
        # Build prompt
        messages = build_rag_prompt(
            question,
            context_chunks,
            conversation_history
        )
        
        # Call OpenAI
        response = self.openai_client.chat.completions.create(
            model=self.chat_model,
            messages=messages,
            temperature=0.3,  # Lower temperature for more factual responses
            max_tokens=1500
        )
        
        answer = response.choices[0].message.content
        elapsed_ms = (time.time() - start_time) * 1000
        
        return answer, elapsed_ms
    
    def ask(
        self,
        question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> RAGResponse:
        """
        Ask a question and get an answer with sources.
        
        Args:
            question: User's question
            conversation_history: Optional list of previous messages
            
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
            # Step 1: Retrieve context
            chunks, retrieval_time = self._retrieve_context(question)
            
            if not chunks:
                return RAGResponse(
                    answer="I couldn't find any relevant information in my knowledge base to answer your question. Please try rephrasing your question or ask about a specific VA benefit or condition.",
                    sources=[],
                    query_time_ms=(time.time() - total_start) * 1000,
                    chunks_retrieved=0,
                    model_used=self.chat_model
                )
            
            # Step 2: Generate response
            answer, generation_time = self._generate_response(
                question,
                chunks,
                conversation_history
            )
            
            # Step 3: Extract sources
            sources = extract_sources_from_chunks(chunks)
            
            total_time = (time.time() - total_start) * 1000
            
            return RAGResponse(
                answer=answer,
                sources=sources,
                query_time_ms=total_time,
                chunks_retrieved=len(chunks),
                model_used=self.chat_model
            )
            
        except Exception as e:
            print(f"\u274c RAG Pipeline error: {e}")
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
