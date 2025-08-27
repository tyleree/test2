"""
Utility functions for the RAG pipeline.
"""

import re
import hashlib
import tiktoken
import numpy as np
from typing import List, Set, Dict, Any
from sklearn.metrics.pairwise import cosine_similarity


def normalize_query(q: str) -> str:
    """
    Normalize query for consistent caching.
    Lowercase, collapse whitespace, strip punctuation; keep meaning.
    """
    # Convert to lowercase
    normalized = q.lower()
    
    # Remove extra whitespace and normalize
    normalized = re.sub(r'\s+', ' ', normalized.strip())
    
    # Remove some punctuation but keep meaningful characters
    normalized = re.sub(r'[^\w\s\-\'\"?!.]', '', normalized)
    
    # Remove trailing punctuation that doesn't change meaning
    normalized = re.sub(r'[.!?]+$', '', normalized)
    
    return normalized


def hash_string(s: str) -> str:
    """Create a stable hash of a string."""
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def jaccard_overlap(set1: Set[str], set2: Set[str]) -> float:
    """Calculate Jaccard overlap coefficient between two sets."""
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


def stable_hash_list(items: List[str]) -> str:
    """Create a stable hash for a list of doc_ids."""
    # Sort for consistency
    sorted_items = sorted(items)
    combined = '|'.join(sorted_items)
    return hash_string(combined)


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in text using tiktoken."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        # Fallback: rough approximation
        return len(text.split()) * 1.3


def estimate_tokens_saved(original_tokens: int, cached_tokens: int) -> int:
    """Estimate tokens saved by using cache instead of full pipeline."""
    # Assume full pipeline would use ~2x tokens (retrieval + generation)
    full_pipeline_estimate = original_tokens * 2
    return max(0, full_pipeline_estimate - cached_tokens)


def cosine_distance(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    if vec1.ndim == 1:
        vec1 = vec1.reshape(1, -1)
    if vec2.ndim == 1:
        vec2 = vec2.reshape(1, -1)
    
    return cosine_similarity(vec1, vec2)[0][0]


def truncate_text(text: str, max_tokens: int, model: str = "gpt-4") -> str:
    """Truncate text to fit within token budget."""
    current_tokens = count_tokens(text, model)
    if current_tokens <= max_tokens:
        return text
    
    # Rough truncation based on token ratio
    ratio = max_tokens / current_tokens
    target_chars = int(len(text) * ratio * 0.9)  # 90% to be safe
    
    truncated = text[:target_chars]
    
    # Try to end at a sentence boundary
    last_period = truncated.rfind('.')
    last_newline = truncated.rfind('\n')
    
    if last_period > len(truncated) * 0.8:
        truncated = truncated[:last_period + 1]
    elif last_newline > len(truncated) * 0.8:
        truncated = truncated[:last_newline]
    
    return truncated


def extract_doc_ids_from_results(results: List[Dict[str, Any]]) -> List[str]:
    """Extract unique doc_ids from search results."""
    doc_ids = []
    seen = set()
    
    for result in results:
        doc_id = result.get('doc_id') or result.get('id', '')
        if doc_id and doc_id not in seen:
            doc_ids.append(doc_id)
            seen.add(doc_id)
    
    return doc_ids


def merge_and_deduplicate_quotes(quotes: List[Dict[str, Any]], max_tokens: int) -> List[Dict[str, Any]]:
    """Merge and deduplicate quotes while staying within token budget."""
    seen_texts = set()
    merged = []
    current_tokens = 0
    
    for quote in quotes:
        text = quote.get('quote', '').strip()
        if not text or text in seen_texts:
            continue
        
        quote_tokens = count_tokens(text)
        if current_tokens + quote_tokens > max_tokens:
            break
        
        merged.append(quote)
        seen_texts.add(text)
        current_tokens += quote_tokens
    
    return merged


def format_citations(sources: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Format sources into citation format."""
    citations = []
    for i, source in enumerate(sources, 1):
        citations.append({
            "n": i,
            "url": source.get("url", "")
        })
    return citations


def validate_and_clean_response(answer: str, max_length: int = 5000) -> str:
    """Validate and clean the generated answer."""
    if not answer or not answer.strip():
        return "I don't have enough information to answer that question."
    
    # Truncate if too long
    if len(answer) > max_length:
        answer = answer[:max_length].rsplit('.', 1)[0] + '.'
    
    # Ensure proper formatting
    answer = answer.strip()
    
    return answer










