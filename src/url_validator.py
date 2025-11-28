"""
URL Validation for RAG Pipeline

This module provides URL validation and sanitization to prevent hallucinated URLs
from appearing in responses. It maintains a whitelist of known good URLs from the corpus.

Features:
- Build URL whitelist from corpus at startup
- Validate URLs in LLM responses
- Sanitize unknown URLs to fallback to homepage
- Log suspicious URL usage for monitoring
"""

import re
import json
from typing import Set, List, Optional, Dict, Any
from pathlib import Path

# Base URL for the knowledge base
BASE_URL = "https://veteransbenefitskb.com"
HOMEPAGE_URL = "https://veteransbenefitskb.com"

# Known valid page paths (populated from corpus)
_known_urls: Set[str] = set()
_url_to_topics: Dict[str, List[str]] = {}  # URL -> list of topics that use it

# Pages that should never be used as source URLs (navigation, utility pages)
BLOCKED_PATHS = {
    '', '#', 'cart', 'mission', 'about', 'contact', 'login', 'signup',
    'checkout', 'privacy', 'terms', 'faq'
}


def build_url_whitelist(corpus_path: str) -> Set[str]:
    """
    Build the URL whitelist from the corpus file.
    
    Args:
        corpus_path: Path to the restructured corpus JSON file
        
    Returns:
        Set of valid URLs found in the corpus
    """
    global _known_urls, _url_to_topics
    
    _known_urls = {HOMEPAGE_URL, BASE_URL}
    _url_to_topics = {HOMEPAGE_URL: ["homepage"], BASE_URL: ["homepage"]}
    
    try:
        corpus_file = Path(corpus_path)
        if not corpus_file.exists():
            print(f"[URL_VALIDATOR] Corpus not found at {corpus_path}")
            return _known_urls
        
        with open(corpus_file, 'r', encoding='utf-8') as f:
            corpus = json.load(f)
        
        for chunk in corpus:
            url = chunk.get("url", "")
            topic = chunk.get("topic", "Unknown")
            
            if url and url.strip():
                # Normalize URL
                normalized = normalize_url(url)
                if normalized and not is_blocked_url(normalized):
                    _known_urls.add(normalized)
                    
                    # Track topics for debugging
                    if normalized not in _url_to_topics:
                        _url_to_topics[normalized] = []
                    if topic not in _url_to_topics[normalized]:
                        _url_to_topics[normalized].append(topic)
        
        print(f"[URL_VALIDATOR] Built whitelist with {len(_known_urls)} URLs from corpus")
        return _known_urls
        
    except Exception as e:
        print(f"[URL_VALIDATOR] Error building whitelist: {e}")
        return _known_urls


def normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent comparison.
    
    Args:
        url: URL to normalize
        
    Returns:
        Normalized URL string
    """
    if not url:
        return ""
    
    url = url.strip()
    
    # Handle relative URLs
    if url.startswith('/'):
        url = BASE_URL + url
    
    # Ensure https
    if url.startswith('http://veteransbenefitskb'):
        url = url.replace('http://', 'https://')
    
    # Add www if missing (normalize both forms)
    if url.startswith('https://veteransbenefitskb.com'):
        pass  # Keep as-is
    elif url.startswith('https://www.veteransbenefitskb.com'):
        url = url.replace('www.', '')  # Normalize to non-www
    
    # Remove trailing slash
    url = url.rstrip('/')
    
    return url


def is_blocked_url(url: str) -> bool:
    """
    Check if a URL path is blocked (navigation/utility pages).
    
    Args:
        url: URL to check
        
    Returns:
        True if URL should be blocked
    """
    if not url:
        return True
    
    # Extract path from URL
    path = ""
    if 'veteransbenefitskb.com/' in url:
        path = url.split('veteransbenefitskb.com/')[-1]
    elif 'veteransbenefitskb.com' in url:
        path = ""
    
    # Remove hash fragment for path check
    path = path.split('#')[0].lower()
    
    return path in BLOCKED_PATHS


def is_valid_url(url: str) -> bool:
    """
    Check if a URL is in the whitelist.
    
    Args:
        url: URL to validate
        
    Returns:
        True if URL is known/valid
    """
    if not url:
        return False
    
    normalized = normalize_url(url)
    
    # Check exact match
    if normalized in _known_urls:
        return True
    
    # Check without hash fragment
    base_url = normalized.split('#')[0]
    if base_url in _known_urls:
        return True
    
    # Check if it's a valid veteransbenefitskb.com URL
    if 'veteransbenefitskb.com' in normalized:
        # Allow any veteransbenefitskb.com URL that's not blocked
        if not is_blocked_url(normalized):
            return True
    
    return False


def sanitize_response_urls(response: str) -> tuple[str, List[str]]:
    """
    Sanitize URLs in an LLM response, replacing unknown URLs with the homepage.
    
    Args:
        response: The LLM response text
        
    Returns:
        Tuple of (sanitized response, list of replaced URLs)
    """
    # Find all URLs in the response
    url_pattern = r'https?://(?:www\.)?veteransbenefitskb\.com[^\s\)\]\"\'<>]*'
    found_urls = re.findall(url_pattern, response)
    
    replaced_urls = []
    
    for url in found_urls:
        normalized = normalize_url(url)
        
        if not is_valid_url(normalized):
            print(f"[URL_VALIDATOR] Unknown URL found in response: {url}")
            replaced_urls.append(url)
            # Replace with homepage
            response = response.replace(url, HOMEPAGE_URL)
    
    if replaced_urls:
        print(f"[URL_VALIDATOR] Replaced {len(replaced_urls)} unknown URLs with homepage")
    
    return response, replaced_urls


def validate_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate and sanitize URLs in source citations.
    
    Args:
        sources: List of source dictionaries with 'source_url' or 'url' fields
        
    Returns:
        Sanitized sources list
    """
    validated = []
    
    for source in sources:
        url = source.get("source_url") or source.get("url", "")
        
        if url:
            normalized = normalize_url(url)
            if not is_valid_url(normalized):
                print(f"[URL_VALIDATOR] Invalid source URL: {url} (topic: {source.get('title', 'unknown')})")
                source["source_url"] = HOMEPAGE_URL
                source["url"] = HOMEPAGE_URL
                source["url_validated"] = False
            else:
                source["url_validated"] = True
        
        validated.append(source)
    
    return validated


def get_topics_for_url(url: str) -> List[str]:
    """
    Get the topics associated with a URL (for debugging).
    
    Args:
        url: URL to look up
        
    Returns:
        List of topic names that use this URL
    """
    normalized = normalize_url(url)
    return _url_to_topics.get(normalized, [])


def get_whitelist_stats() -> Dict[str, Any]:
    """
    Get statistics about the URL whitelist.
    
    Returns:
        Dictionary with whitelist statistics
    """
    return {
        "total_urls": len(_known_urls),
        "unique_base_urls": len(set(url.split('#')[0] for url in _known_urls)),
        "urls_with_fragments": len([u for u in _known_urls if '#' in u]),
        "sample_urls": list(_known_urls)[:10]
    }


# Initialize with empty whitelist - will be populated when corpus loads
def initialize_url_validator(corpus_path: str = "veteran-ai-spark/corpus/vbkb_restructured.json") -> None:
    """
    Initialize the URL validator with the corpus.
    
    Args:
        corpus_path: Path to the restructured corpus JSON file
    """
    build_url_whitelist(corpus_path)

