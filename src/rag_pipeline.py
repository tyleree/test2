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
    compute_corpus_hash,
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
    VerificationResult,
    sanitize_response,
    verify_numbers_in_response
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
    cache_hit: Optional[str] = None  # "exact", "semantic", "database", "topic", or None
    semantic_similarity: Optional[float] = None  # Similarity score for cache hits (0-1)
    retrieval_score: Optional[float] = None  # Best retrieval score for cache misses (0-1)
    error: Optional[str] = None
    weak_retrieval: bool = False  # True if best chunk score was below threshold
    citation_verification: Optional[Dict[str, Any]] = None  # Citation verification results
    token_usage: Optional[Dict[str, int]] = None  # Token usage from OpenAI API
    
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
        if self.semantic_similarity is not None:
            result["metadata"]["semantic_similarity"] = self.semantic_similarity
        if self.retrieval_score is not None:
            result["metadata"]["retrieval_score"] = self.retrieval_score
        if self.weak_retrieval:
            result["metadata"]["weak_retrieval"] = True
        if self.citation_verification:
            result["metadata"]["citation_verification"] = self.citation_verification
        if self.token_usage:
            result["metadata"]["token_usage"] = self.token_usage
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
                    # Include topic and diagnostic_code for better semantic matching
                    # This helps queries like "What is diagnostic code for X" match better
                    topic = item.get("topic", "")
                    diagnostic_code = item.get("diagnostic_code", "")
                    
                    # Build prefix with diagnostic code if available
                    if diagnostic_code and topic:
                        content = f"Diagnostic Code {diagnostic_code} - {topic}\n\n{content}"
                    elif topic:
                        content = f"{topic}\n\n{content}"
                    
                    documents[doc_id] = content
            
            print(f"[NOTE] Prepared {len(documents)} documents for embedding")
            
            # Compute corpus hash for cache invalidation
            corpus_hash = compute_corpus_hash(documents)
            print(f"[INFO] Corpus hash: {corpus_hash}")
            
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
            
            # Initialize response cache with corpus hash for automatic invalidation
            # When corpus changes, stale cached answers will be cleared
            if self.enable_response_cache:
                self.response_cache = get_response_cache(corpus_hash=corpus_hash)
                print(f"[OK] Response cache initialized (corpus-aware)")
            
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
    
    # Common DC codes mapped to condition names for better query expansion
    DC_CODE_LOOKUP = {
        # Cardiovascular (7XXX)
        "7101": "hypertension high blood pressure",
        "7005": "arteriosclerotic heart disease coronary artery disease",
        "7007": "hypertensive heart disease",
        "7010": "supraventricular arrhythmia",
        "7011": "ventricular arrhythmia",
        "7110": "aortic aneurysm",
        "7114": "peripheral vascular disease",
        # Mental Health (9XXX)
        "9411": "PTSD post-traumatic stress disorder",
        "9434": "major depressive disorder depression",
        "9400": "generalized anxiety disorder",
        "9201": "schizophrenia",
        "9432": "bipolar disorder",
        # Musculoskeletal (5XXX)
        "5242": "degenerative arthritis spine",
        "5237": "lumbosacral strain back pain",
        "5260": "limitation of flexion knee",
        "5261": "limitation of extension knee",
        "5003": "degenerative arthritis",
        "5010": "traumatic arthritis",
        # Respiratory (6XXX)
        "6602": "asthma bronchial asthma",
        "6604": "COPD chronic obstructive pulmonary disease",
        "6600": "chronic bronchitis",
        "6847": "sleep apnea obstructive sleep apnea",
        # Neurological (8XXX)
        "8100": "migraine headaches",
        "8520": "sciatic nerve paralysis",
        "8045": "traumatic brain injury TBI",
        # Digestive (7XXX)
        "7305": "duodenal ulcer",
        "7307": "chronic gastritis",
        "7206": "GERD gastroesophageal reflux disease",
        # Endocrine (7XXX)
        "7913": "diabetes mellitus",
        # Genitourinary (7XXX)
        "7522": "erectile dysfunction",
        "7527": "prostate conditions",
        # Skin (7XXX)
        "7806": "dermatitis eczema",
        "7816": "psoriasis",
        # Hearing/Ear (6XXX)
        "6100": "hearing loss",
        "6260": "tinnitus",
    }
    
    def _preprocess_query(self, query: str) -> str:
        """
        Preprocess query to expand abbreviations and normalize terminology
        for better semantic matching.
        
        Args:
            query: Original user query
            
        Returns:
            Preprocessed query with expanded abbreviations
        """
        import re
        
        processed = query
        
        # Handle "DC XXXX" queries - expand with condition name if known
        dc_match = re.search(r'\b(?:dc|diagnostic\s*code)\s*(\d{4})\b', processed, re.IGNORECASE)
        if dc_match:
            code = dc_match.group(1)
            condition = self.DC_CODE_LOOKUP.get(code, "")
            
            # Replace the DC reference with full expansion
            if condition:
                replacement = f"Diagnostic Code {code} ({condition})"
            else:
                replacement = f"Diagnostic Code {code}"
            
            processed = re.sub(r'\bDC\s*' + code + r'\b', replacement, processed, flags=re.IGNORECASE)
            processed = re.sub(r'\bdiagnostic\s*code\s*' + code + r'\b', replacement, processed, flags=re.IGNORECASE)
            
            # If it's a simple "What is DC XXXX?" query, expand further
            if re.match(r'^(what is |what\'s )?(dc\s*\d{4}|diagnostic\s*code\s*\d{4})\s*\??$', query, re.IGNORECASE):
                if condition:
                    processed = f"What is Diagnostic Code {code}? {condition}. What are the rating criteria?"
                else:
                    processed = f"What is Diagnostic Code {code}? What condition does it cover?"
        
        # Handle "Chapter XX" education benefit queries
        chapter_patterns = {
            r'\bchapter\s*31\b': 'Chapter 31 VR&E (Veterans Readiness and Employment, Voc Rehab)',
            r'\bchapter\s*33\b': 'Chapter 33 Post-9/11 GI Bill',
            r'\bchapter\s*30\b': 'Chapter 30 Montgomery GI Bill',
            r'\bchapter\s*35\b': 'Chapter 35 DEA (Dependents Educational Assistance)',
            r'\bchapter\s*32\b': 'Chapter 32 VEAP (Veterans Educational Assistance Program)',
        }
        
        for pattern, expanded in chapter_patterns.items():
            if re.search(pattern, processed, re.IGNORECASE):
                processed = re.sub(pattern, expanded, processed, flags=re.IGNORECASE)
        
        # Expand "GI Bill" queries to distinguish from VR&E
        if re.search(r'\bgi\s*bill\b', processed, re.IGNORECASE):
            # Don't add if already has chapter info
            if not re.search(r'chapter\s*3[0-3]|montgomery|post.?9.?11', processed, re.IGNORECASE):
                processed = re.sub(r'\bgi\s*bill\b', 'GI Bill (education benefits Chapter 30 33 Montgomery Post-9/11)', processed, flags=re.IGNORECASE)
        
        # Expand "Post-9/11" references
        post911_pattern = r'\bpost[\s-]*9[\s/-]*11\b'
        if re.search(post911_pattern, processed, re.IGNORECASE):
            if 'GI Bill' not in processed and 'Chapter 33' not in processed:
                processed = re.sub(post911_pattern, 'Post-9/11 GI Bill (Chapter 33 education benefits)', processed, flags=re.IGNORECASE)
        
        # Expand common abbreviations
        abbreviations = {
            r'\bPTSD\b': 'PTSD (Post-Traumatic Stress Disorder)',
            r'\bTDIU\b': 'TDIU (Total Disability Individual Unemployability)',
            r'\bVR&E\b': 'VR&E (Veterans Readiness and Employment)',
            r'\bVRE\b': 'VRE (Veterans Readiness and Employment, Voc Rehab)',
            r'\bBDD\b': 'BDD (Benefits Delivery at Discharge)',
            r'\bC&P\b': 'C&P (Compensation and Pension)',
            r'\bMGIB\b': 'MGIB (Montgomery GI Bill)',
            r'\bvoc\s*rehab\b': 'Voc Rehab (Veterans Readiness and Employment, VR&E, Chapter 31)',
        }
        
        for abbrev, expanded in abbreviations.items():
            # Only expand if not already expanded
            if expanded not in processed:
                processed = re.sub(abbrev, expanded, processed, flags=re.IGNORECASE)
        
        # If query changed, log it
        if processed != query:
            print(f"[PREPROCESS] Query expanded: '{query}' -> '{processed}'")
        
        return processed
    
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
    
    def _log_low_confidence_report(
        self,
        question: str,
        best_score: float,
        chunks: List[Dict[str, Any]],
        verification_result,
        sanitization_report: Dict[str, Any],
        model_used: str
    ) -> None:
        """
        Generate a detailed report when confidence is low.
        
        This helps diagnose WHY the retrieval score was low and what
        might be done to improve coverage for this topic.
        """
        import json
        from datetime import datetime, timezone
        
        # Build comprehensive report
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "LOW_CONFIDENCE_REPORT",
            "question": question,
            "confidence_score": best_score,
            "threshold_used": 0.50,
            "analysis": {}
        }
        
        # Analyze why score was low
        analysis = report["analysis"]
        
        # 1. Query characteristics
        query_words = question.lower().split()
        analysis["query_analysis"] = {
            "word_count": len(query_words),
            "question_type": self._detect_question_type(question),
            "contains_specific_terms": any(term in question.lower() for term in [
                "dc", "diagnostic code", "percentage", "%", "rating",
                "form", "va form", "cfr", "38 cfr"
            ])
        }
        
        # 2. Chunk analysis - why didn't we find better matches?
        chunk_analysis = []
        for i, chunk in enumerate(chunks[:5]):  # Top 5 chunks
            chunk_info = {
                "rank": i + 1,
                "score": chunk.get("score", 0),
                "topic": chunk.get("metadata", {}).get("topic", "Unknown"),
                "type": chunk.get("metadata", {}).get("type", "Unknown"),
                "text_preview": chunk.get("text", "")[:150] + "..."
            }
            chunk_analysis.append(chunk_info)
        
        analysis["retrieved_chunks"] = {
            "total_retrieved": len(chunks),
            "best_score": best_score,
            "worst_score": chunks[-1]["score"] if chunks else 0,
            "score_spread": best_score - (chunks[-1]["score"] if chunks else 0),
            "chunks": chunk_analysis
        }
        
        # 3. Coverage gap detection
        # What topics were retrieved vs what was asked?
        retrieved_topics = list(set(
            c.get("metadata", {}).get("topic", "Unknown") 
            for c in chunks
        ))
        analysis["topic_coverage"] = {
            "retrieved_topics": retrieved_topics[:10],
            "topic_count": len(retrieved_topics),
            "possible_gap": best_score < 0.45  # Very likely a coverage gap
        }
        
        # 4. Citation verification issues
        if verification_result:
            analysis["citation_issues"] = {
                "total_citations": verification_result.total_citations,
                "suspicious": verification_result.suspicious_citations,
                "verification_score": verification_result.verification_score,
                "issues": verification_result.overall_issues[:5]
            }
        
        # 5. Number verification issues
        if sanitization_report and "number_verification" in sanitization_report:
            num_report = sanitization_report["number_verification"]
            analysis["number_issues"] = {
                "is_clean": num_report.get("is_clean", True),
                "hallucinated_percentages": num_report.get("hallucinated_percentages", []),
                "hallucinated_dc_codes": num_report.get("hallucinated_dc_codes", []),
                "issues": num_report.get("issues", [])
            }
        
        # 6. Recommendations
        recommendations = []
        if best_score < 0.45:
            recommendations.append("CRITICAL: Very low score suggests topic may not be covered in knowledge base")
        if best_score < 0.50:
            recommendations.append("Consider adding more content about this topic to the corpus")
        if len(retrieved_topics) == 1:
            recommendations.append("Only one topic matched - may need broader coverage")
        if analysis["query_analysis"]["contains_specific_terms"]:
            recommendations.append("Question asks for specific data - verify corpus has exact values")
        
        analysis["recommendations"] = recommendations
        
        # Log the report
        print("\n" + "="*80)
        print("[LOW_CONFIDENCE_REPORT] Detailed Analysis")
        print("="*80)
        print(f"Question: {question}")
        print(f"Confidence Score: {best_score:.1%} (threshold: 50%)")
        print(f"Model Used: {model_used}")
        print("-"*80)
        print(f"Query Type: {analysis['query_analysis']['question_type']}")
        print(f"Word Count: {analysis['query_analysis']['word_count']}")
        print(f"Asks for Specific Data: {analysis['query_analysis']['contains_specific_terms']}")
        print("-"*80)
        print(f"Retrieved {len(chunks)} chunks from {len(retrieved_topics)} topics:")
        for chunk_info in chunk_analysis[:3]:
            print(f"  #{chunk_info['rank']}: {chunk_info['topic']} (score: {chunk_info['score']:.3f})")
        print("-"*80)
        print("Recommendations:")
        for rec in recommendations:
            print(f"  • {rec}")
        print("="*80 + "\n")
        
        # Also log as JSON for structured parsing
        print(f"[LOW_CONFIDENCE_JSON] {json.dumps(report, default=str)}")
    
    def _detect_question_type(self, question: str) -> str:
        """Detect the type of question being asked."""
        q_lower = question.lower()
        
        if any(w in q_lower for w in ["what is", "define", "explain"]):
            return "definitional"
        elif any(w in q_lower for w in ["how do", "how to", "how can"]):
            return "procedural"
        elif any(w in q_lower for w in ["percentage", "%", "rating", "score"]):
            return "rating_criteria"
        elif any(w in q_lower for w in ["compare", "difference", "vs", "versus"]):
            return "comparison"
        elif any(w in q_lower for w in ["can i", "am i eligible", "qualify"]):
            return "eligibility"
        elif any(w in q_lower for w in ["when", "how long", "timeline"]):
            return "temporal"
        else:
            return "general"
    
    def _generate_response(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None
    ) -> Tuple[str, float, str, Dict[str, int]]:
        """
        Generate a response using OpenAI chat completion.
        
        Args:
            question: User's question
            context_chunks: Retrieved context chunks
            conversation_history: Optional conversation history
            model: Specific model to use (overrides default)
            
        Returns:
            Tuple of (answer text, generation time in ms, model used, token usage dict)
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
        
        # Capture token usage from OpenAI response
        token_usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }
        
        return answer, elapsed_ms, selected_model, token_usage
    
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
                    response_text, sources, model_used, cache_type, similarity = cached
                    # Return cached response immediately
                    yield StreamChunk(
                        content=response_text,
                        is_final=True,
                        sources=sources,
                        metadata={
                            "query_time_ms": (time.time() - total_start) * 1000,
                            "cache_hit": cache_type,
                            "model_used": model_used,
                            "semantic_similarity": similarity
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
        
        # Query preprocessing - expand common abbreviations for better retrieval
        question = self._preprocess_query(question)
        
        try:
            # Step 0: Generate query embedding for cache lookup
            query_embedding = embed_query_cached(question, self.embedding_model)
            
            # Step 1: Check response cache
            if self.response_cache and self.enable_response_cache:
                cached = self.response_cache.get(question, query_embedding)
                if cached:
                    response_text, sources, model_used, cache_type, similarity = cached
                    return RAGResponse(
                        answer=response_text,
                        sources=sources,
                        query_time_ms=(time.time() - total_start) * 1000,
                        chunks_retrieved=0,  # From cache, no retrieval
                        model_used=model_used,
                        cache_hit=cache_type,
                        semantic_similarity=similarity  # Include similarity score
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
            
            # HALLUCINATION PREVENTION: Refuse to answer if retrieval is too weak
            # This prevents the LLM from hallucinating when context is poor
            best_score = chunks[0]["score"] if chunks else 0
            if best_score < VERY_WEAK_THRESHOLD:
                print(f"[HALLUCINATION_BLOCKED] Refusing to answer - best retrieval score {best_score:.3f} < {VERY_WEAK_THRESHOLD}")
                return RAGResponse(
                    answer="I don't have reliable information about that specific topic in my knowledge base. "
                           "My sources may not cover this area well enough to give you an accurate answer.\n\n"
                           "**Suggestions:**\n"
                           "- Try rephrasing your question with different terms\n"
                           "- Check the official VA website at [va.gov](https://www.va.gov)\n"
                           "- Contact a Veterans Service Organization (VSO) for personalized guidance",
                    sources=[],
                    query_time_ms=(time.time() - total_start) * 1000,
                    chunks_retrieved=len(chunks),
                    model_used=self.chat_model,
                    routing_reason="retrieval_too_weak",
                    retrieval_score=best_score,
                    weak_retrieval=True
                )
            
            # Flag weak (but not critically weak) retrievals for monitoring
            if weak_retrieval:
                print(f"[HALLUCINATION_RISK] Proceeding with weak retrieval - best score {best_score:.3f} below {WEAK_RETRIEVAL_THRESHOLD}")
            
            # Step 3: Model routing - select appropriate model based on query complexity
            if force_model:
                selected_model = force_model
                routing_reason = "forced_override"
            else:
                selected_model, routing_reason = self._classify_query_complexity(question, chunks)
            
            print(f"[ROUTER] Model: {selected_model} (reason: {routing_reason})")
            
            # Step 4: Generate response with selected model
            answer, generation_time, model_used, token_usage = self._generate_response(
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
            
            # Step 6b: Sanitize response - remove hallucinated citations and verify numbers
            # This is a zero-token post-processing step
            answer, sanitization_report = sanitize_response(
                answer, 
                chunks, 
                remove_hallucinated_numbers=weak_retrieval  # Add warning if retrieval was weak
            )
            
            if sanitization_report["citations_cleaned"]:
                print(f"[SANITIZATION] Cleaned hallucinated citations from response")
            
            number_issues = sanitization_report["number_verification"]["issues"]
            if number_issues:
                print(f"[NUMBER_CHECK] Potential hallucinated numbers detected:")
                for issue in number_issues:
                    print(f"  - {issue}")
            
            # Step 6c: Add confidence warning prefix for weak retrievals
            # This adds transparency when our sources don't fully cover the topic
            LOW_CONFIDENCE_THRESHOLD = 0.50
            if weak_retrieval and best_score < LOW_CONFIDENCE_THRESHOLD:
                confidence_warning = (
                    "⚠️ **Note:** My sources may not fully cover this topic. "
                    f"Our internal confidence score is **{best_score:.1%}** for this response - "
                    "please verify the answer with your own due diligence. "
                    "A report has been generated and someone will review this.\n\n"
                )
                answer = confidence_warning + answer
                
                # Generate detailed low-confidence report
                self._log_low_confidence_report(
                    question=question,
                    best_score=best_score,
                    chunks=chunks,
                    verification_result=verification_result,
                    sanitization_report=sanitization_report,
                    model_used=model_used
                )
            
            total_time = (time.time() - total_start) * 1000
            
            # Step 7: Cache the SANITIZED response (don't cache hallucinations)
            if self.response_cache and self.enable_response_cache:
                self.response_cache.set(
                    question,
                    answer,  # Cache the cleaned answer
                    sources,
                    model_used,
                    query_embedding
                )
            
            # Calculate best retrieval score for analytics
            best_retrieval_score = chunks[0]["score"] if chunks else None
            
            return RAGResponse(
                answer=answer,
                sources=sources,
                query_time_ms=total_time,
                chunks_retrieved=len(chunks),
                model_used=model_used,
                routing_reason=routing_reason,
                retrieval_score=best_retrieval_score,  # Best chunk relevance score
                weak_retrieval=weak_retrieval,
                citation_verification=verification_summary,
                token_usage=token_usage
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
        # Check if caching should be disabled (for debugging/diagnostics)
        disable_cache = os.getenv("DISABLE_RESPONSE_CACHE", "").lower() in ("true", "1", "yes")
        if disable_cache:
            print("[CONFIG] ⚠️ Response caching DISABLED via DISABLE_RESPONSE_CACHE env var")
        _pipeline = RAGPipeline(enable_response_cache=not disable_cache)
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
