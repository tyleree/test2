"""
Utility functions for the RAG application.
"""

import hashlib
import uuid
import re
import tiktoken
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def get_token_count(text: str, model: str = "gpt-4o") -> int:
    """Get token count for text using tiktoken."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Token counting failed: {e}, using character approximation")
        return len(text) // 4  # Rough approximation

def normalize_query(query: str) -> str:
    """Normalize query for consistent caching."""
    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', query.strip())
    # Convert to lowercase
    normalized = normalized.lower()
    # Remove common punctuation that doesn't affect meaning
    normalized = re.sub(r'[.!?]+$', '', normalized)
    return normalized

def generate_doc_id(source_url: str, title: str = "") -> str:
    """Generate stable document ID from source URL and title."""
    content = f"{source_url}#{title}".encode('utf-8')
    return hashlib.sha256(content).hexdigest()[:16]

def generate_chunk_id() -> str:
    """Generate unique chunk ID."""
    return str(uuid.uuid4())

def calculate_jaccard_similarity(set1: set, set2: set) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0

def extract_doc_ids_from_text(text: str) -> set:
    """Extract potential document identifiers from text for similarity comparison."""
    # Extract URLs, proper nouns, and key terms
    urls = set(re.findall(r'https?://[^\s]+', text))
    
    # Extract capitalized words (potential proper nouns)
    proper_nouns = set(re.findall(r'\b[A-Z][a-zA-Z]+\b', text))
    
    # Extract numbers (ratings, percentages, etc.)
    numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', text))
    
    return urls.union(proper_nouns).union(numbers)

def chunk_text_markdown_aware(text: str, chunk_size: int = 700, overlap: int = 90) -> List[Dict[str, Any]]:
    """
    Split text into chunks with markdown awareness.
    Returns list of chunks with metadata.
    """
    chunks = []
    
    # Split by major sections (headers)
    sections = re.split(r'\n(?=#{1,3}\s)', text)
    
    current_chunk = ""
    current_title = ""
    current_section = ""
    
    for section in sections:
        lines = section.split('\n')
        
        # Extract title and section from headers
        if lines[0].startswith('#'):
            header_line = lines[0]
            if header_line.startswith('# '):
                current_title = header_line[2:].strip()
                current_section = ""
            elif header_line.startswith('## ') or header_line.startswith('### '):
                current_section = header_line.lstrip('# ').strip()
        
        section_text = section
        
        # If section is small enough, add to current chunk
        if get_token_count(current_chunk + section_text) <= chunk_size:
            current_chunk += "\n" + section_text if current_chunk else section_text
        else:
            # Save current chunk if it exists
            if current_chunk.strip():
                chunks.append({
                    'text': current_chunk.strip(),
                    'title': current_title,
                    'section': current_section,
                    'token_count': get_token_count(current_chunk)
                })
            
            # Start new chunk with overlap
            if overlap > 0 and chunks:
                # Take last few sentences for overlap
                sentences = current_chunk.split('. ')
                overlap_text = '. '.join(sentences[-2:]) if len(sentences) > 1 else ""
                current_chunk = overlap_text + "\n" + section_text if overlap_text else section_text
            else:
                current_chunk = section_text
    
    # Add final chunk
    if current_chunk.strip():
        chunks.append({
            'text': current_chunk.strip(),
            'title': current_title,
            'section': current_section,
            'token_count': get_token_count(current_chunk)
        })
    
    return chunks

def sanitize_html(html: str) -> str:
    """Sanitize HTML to allow only safe tags."""
    from bs4 import BeautifulSoup
    
    allowed_tags = ['p', 'ul', 'ol', 'li', 'strong', 'em', 'a', 'br', 'h3']
    allowed_attrs = {'a': ['href']}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove all tags not in allowed list
    for tag in soup.find_all():
        if tag.name not in allowed_tags:
            tag.unwrap()
        else:
            # Remove attributes not in allowed list
            allowed_tag_attrs = allowed_attrs.get(tag.name, [])
            attrs_to_remove = [attr for attr in tag.attrs if attr not in allowed_tag_attrs]
            for attr in attrs_to_remove:
                del tag[attr]
    
    return str(soup)

def format_timestamp() -> str:
    """Get formatted timestamp for logging."""
    return datetime.utcnow().isoformat() + "Z"

def is_query_complex(query: str, word_threshold: int = 18) -> bool:
    """Determine if query is complex enough to warrant rewriting."""
    words = query.split()
    
    # Check word count
    if len(words) > word_threshold:
        return True
    
    # Check for complex patterns
    complex_patterns = [
        r'\b(how|why|what|when|where)\b.*\b(and|or|but)\b',  # Multiple questions
        r'\b(compare|versus|vs\.?|difference)\b',  # Comparisons
        r'\b(if|unless|provided|assuming)\b',  # Conditionals
        r'[;,].*[;,]',  # Multiple clauses
    ]
    
    for pattern in complex_patterns:
        if re.search(pattern, query.lower()):
            return True
    
    return False

def merge_scores(vector_score: float, bm25_score: float, vector_weight: float = 0.65) -> float:
    """Merge vector and BM25 scores with weighting."""
    bm25_weight = 1.0 - vector_weight
    return (vector_score * vector_weight) + (bm25_score * bm25_weight)