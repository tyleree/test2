"""
OpenAI Embeddings Module with Caching

This module handles:
- Generating embeddings via OpenAI API (text-embedding-3-small)
- Caching embeddings to disk to avoid regeneration
- Batch processing to handle rate limits
- Cache validation against corpus changes

The embedding cache is stored as JSON for easy inspection and portability.
"""

import os
import json
import time
import hashlib
import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from openai import OpenAI

# Configuration
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 1  # Process one chunk at a time (BoardRemands-2 alone is ~13k tokens, exceeds limit when batched)
RATE_LIMIT_DELAY = 0.05  # Very short delay since we're processing 1407 individual chunks
MAX_RETRIES = 5  # Max retry attempts for rate limit errors
RETRY_BASE_DELAY = 3.0  # Base delay for exponential backoff (seconds)


def get_openai_client() -> OpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return OpenAI(api_key=api_key)


def compute_corpus_hash(documents: Dict[str, str]) -> str:
    """
    Compute a hash of the corpus content for cache validation.
    
    Args:
        documents: Dict mapping document IDs to text content
        
    Returns:
        SHA256 hash of the corpus
    """
    # Sort by ID for consistent hashing
    sorted_items = sorted(documents.items())
    content = json.dumps(sorted_items, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def load_embedding_cache(cache_path: str) -> Tuple[Optional[Dict[str, List[float]]], Optional[str]]:
    """
    Load embeddings from cache file.
    
    Returns:
        Tuple of (embeddings_dict, corpus_hash) or (None, None) if cache doesn't exist
    """
    path = Path(cache_path)
    if not path.exists():
        return None, None
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        embeddings = cache_data.get("embeddings", {})
        corpus_hash = cache_data.get("corpus_hash")
        model = cache_data.get("model", "unknown")
        
        print(f"[FILE] Loaded {len(embeddings)} cached embeddings (model: {model})")
        return embeddings, corpus_hash
    
    except Exception as e:
        print(f"[WARN] Failed to load embedding cache: {e}")
        return None, None


def save_embedding_cache(
    cache_path: str, 
    embeddings: Dict[str, List[float]], 
    corpus_hash: str,
    model: str
):
    """Save embeddings to cache file."""
    cache_data = {
        "corpus_hash": corpus_hash,
        "model": model,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(embeddings),
        "embeddings": embeddings
    }
    
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f)
    
    print(f"[SAVE] Saved {len(embeddings)} embeddings to cache")


def generate_embeddings_batch(
    client: OpenAI,
    texts: List[str],
    model: str = DEFAULT_EMBEDDING_MODEL,
    retry_count: int = 0
) -> List[List[float]]:
    """
    Generate embeddings for a batch of texts with retry logic for rate limits.
    
    Args:
        client: OpenAI client
        texts: List of text strings to embed
        model: Embedding model to use
        retry_count: Current retry attempt (for recursion)
        
    Returns:
        List of embedding vectors
    """
    try:
        response = client.embeddings.create(
            model=model,
            input=texts
        )
        
        # Sort by index to ensure order matches input
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]
    
    except Exception as e:
        error_str = str(e)
        
        # Check if it's a rate limit error (429)
        if "rate_limit" in error_str.lower() or "429" in error_str:
            if retry_count < MAX_RETRIES:
                # Extract wait time from error message if available
                wait_time = RETRY_BASE_DELAY * (2 ** retry_count)  # Exponential backoff
                
                # Try to parse suggested wait time from error message
                if "Please try again in" in error_str:
                    match = re.search(r'try again in ([\d.]+)s', error_str)
                    if match:
                        try:
                            suggested_wait = float(match.group(1))
                            wait_time = max(wait_time, suggested_wait + 1.0)  # Add 1s buffer
                        except (ValueError, AttributeError):
                            pass
                
                print(f"   [RETRY] Rate limit hit, waiting {wait_time:.1f}s before retry {retry_count + 1}/{MAX_RETRIES}")
                time.sleep(wait_time)
                
                # Retry with incremented count
                return generate_embeddings_batch(client, texts, model, retry_count + 1)
            else:
                print(f"   [ERROR] Max retries ({MAX_RETRIES}) exceeded for rate limit")
                raise
        else:
            # Not a rate limit error, raise immediately
            raise


def generate_all_embeddings(
    documents: Dict[str, str],
    model: str = DEFAULT_EMBEDDING_MODEL,
    show_progress: bool = True
) -> Dict[str, List[float]]:
    """
    Generate embeddings for all documents.
    
    Args:
        documents: Dict mapping document IDs to text content
        model: Embedding model to use
        show_progress: Whether to print progress updates
        
    Returns:
        Dict mapping document IDs to embedding vectors
    """
    client = get_openai_client()
    
    doc_ids = list(documents.keys())
    texts = [documents[doc_id] for doc_id in doc_ids]
    
    total = len(texts)
    embeddings_dict: Dict[str, List[float]] = {}
    
    print(f"[START] Generating embeddings for {total} documents using {model}...")
    
    for i in range(0, total, BATCH_SIZE):
        batch_ids = doc_ids[i:i + BATCH_SIZE]
        batch_texts = texts[i:i + BATCH_SIZE]
        
        batch_start = i
        batch_end = min(i + BATCH_SIZE, total)
        
        try:
            # Generate embeddings with automatic retry on rate limits
            batch_embeddings = generate_embeddings_batch(client, batch_texts, model)
            
            for doc_id, embedding in zip(batch_ids, batch_embeddings):
                embeddings_dict[doc_id] = embedding
            
            if show_progress:
                progress = batch_end
                print(f"   [{progress:4d}/{total}] Batch {batch_start}-{batch_end} complete ({100 * progress // total}%)")
            
            # Rate limit delay between batches to avoid hitting limits
            if batch_end < total:
                time.sleep(RATE_LIMIT_DELAY)
                
        except Exception as e:
            print(f"[ERROR] Failed to generate embeddings for batch {batch_start}-{batch_end} after retries: {e}")
            raise
    
    print(f"[OK] Generated {len(embeddings_dict)} embeddings")
    return embeddings_dict


def embed_query(query: str, model: str = DEFAULT_EMBEDDING_MODEL) -> List[float]:
    """
    Generate embedding for a single query.
    
    Args:
        query: The query text
        model: Embedding model to use
        
    Returns:
        Embedding vector
    """
    client = get_openai_client()
    
    response = client.embeddings.create(
        model=model,
        input=[query]
    )
    
    return response.data[0].embedding


def get_or_create_embeddings(
    documents: Dict[str, str],
    cache_path: str,
    model: str = DEFAULT_EMBEDDING_MODEL,
    force_regenerate: bool = False
) -> Dict[str, List[float]]:
    """
    Get embeddings from cache or generate them if needed.
    
    This is the main entry point for getting embeddings. It:
    1. Computes a hash of the corpus
    2. Checks if valid cached embeddings exist
    3. If not, generates new embeddings and caches them
    
    Args:
        documents: Dict mapping document IDs to text content
        cache_path: Path to the embedding cache file
        model: Embedding model to use
        force_regenerate: If True, regenerate even if cache exists
        
    Returns:
        Dict mapping document IDs to embedding vectors
    """
    corpus_hash = compute_corpus_hash(documents)
    print(f"[INFO] Corpus hash: {corpus_hash}")
    
    if not force_regenerate:
        cached_embeddings, cached_hash = load_embedding_cache(cache_path)
        
        if cached_embeddings and cached_hash == corpus_hash:
            # Verify all documents have embeddings
            missing = set(documents.keys()) - set(cached_embeddings.keys())
            if not missing:
                print("[OK] Using cached embeddings (corpus unchanged)")
                return cached_embeddings
            else:
                print(f"[WARN] Cache missing {len(missing)} documents, regenerating...")
        elif cached_embeddings:
            print("[WARN] Corpus changed since cache was created, regenerating...")
        else:
            print("[NOTE] No embedding cache found, generating...")
    else:
        print("[REFRESH] Force regenerating embeddings...")
    
    # Generate new embeddings
    embeddings = generate_all_embeddings(documents, model)
    
    # Save to cache
    save_embedding_cache(cache_path, embeddings, corpus_hash, model)
    
    return embeddings


# Query embedding cache (in-memory, for repeated queries)
_query_cache: Dict[str, List[float]] = {}
_query_cache_max_size = 1000


def embed_query_cached(query: str, model: str = DEFAULT_EMBEDDING_MODEL) -> List[float]:
    """
    Generate embedding for a query with in-memory caching.
    
    Args:
        query: The query text
        model: Embedding model to use
        
    Returns:
        Embedding vector
    """
    # Normalize query for cache key
    cache_key = f"{model}:{query.strip().lower()}"
    
    if cache_key in _query_cache:
        return _query_cache[cache_key]
    
    embedding = embed_query(query, model)
    
    # Add to cache (with simple size limit)
    if len(_query_cache) >= _query_cache_max_size:
        # Remove oldest entry (first key)
        oldest_key = next(iter(_query_cache))
        del _query_cache[oldest_key]
    
    _query_cache[cache_key] = embedding
    return embedding
