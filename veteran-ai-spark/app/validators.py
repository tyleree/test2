"""
Cache validation module to ensure cached results are still relevant.
"""

import logging
from typing import List, Dict, Any, Optional
from enum import Enum

from .settings import settings
from .utils import jaccard_overlap, hash_string
from .schemas import CacheEntry
from .cache import cache
from .retrieval import retriever

logger = logging.getLogger(__name__)


class UseCache(Enum):
    """Cache validation results."""
    OK = "ok"
    FALLBACK = "fallback"


class CacheValidator:
    """Validate cached results before serving to ensure they're still relevant."""
    
    def __init__(self):
        pass
    
    def validate_semantic_cache_hit(
        self, 
        cached_entry: CacheEntry, 
        normalized_query: str
    ) -> UseCache:
        """
        Validate a semantic cache hit before reusing.
        
        Runs cheap validation checks:
        1. Document overlap validation
        2. Source availability validation  
        3. Document version validation
        
        Args:
            cached_entry: The cached entry to validate
            normalized_query: The normalized query
        
        Returns:
            UseCache.OK if valid, UseCache.FALLBACK if invalid
        """
        try:
            # Parse cached data
            import json
            cached_top_doc_ids = json.loads(cached_entry.top_doc_ids_json)
            compressed_pack = json.loads(cached_entry.compressed_pack_json)
            
            # 1. Document overlap validation
            if not self._validate_doc_overlap(normalized_query, cached_top_doc_ids):
                logger.info("Cache validation failed: insufficient document overlap")
                return UseCache.FALLBACK
            
            # 2. Source availability validation
            if not self._validate_source_availability(normalized_query, compressed_pack):
                logger.info("Cache validation failed: sources no longer available")
                return UseCache.FALLBACK
            
            # 3. Document version validation
            if not self._validate_doc_versions(cached_entry.doc_version_hash):
                logger.info("Cache validation failed: document versions changed")
                return UseCache.FALLBACK
            
            logger.info("Cache validation passed: reusing cached result")
            return UseCache.OK
            
        except Exception as e:
            logger.error(f"Cache validation error: {e}")
            return UseCache.FALLBACK
    
    def _validate_doc_overlap(self, query: str, cached_top_doc_ids: List[str]) -> bool:
        """
        Validate that fresh retrieval still has sufficient overlap with cached doc_ids.
        
        Args:
            query: The normalized query
            cached_top_doc_ids: Document IDs from cached result
        
        Returns:
            True if overlap meets threshold, False otherwise
        """
        try:
            # Get fresh top document IDs
            fresh_doc_ids = retriever.get_fresh_top_docs(query, k=settings.retrieve_k)
            
            if not fresh_doc_ids:
                return False
            
            # Calculate Jaccard overlap
            cached_set = set(cached_top_doc_ids)
            fresh_set = set(fresh_doc_ids)
            
            overlap = jaccard_overlap(cached_set, fresh_set)
            
            logger.debug(f"Document overlap: {overlap:.3f} (threshold: {settings.doc_overlap_min})")
            
            return overlap >= settings.doc_overlap_min
            
        except Exception as e:
            logger.error(f"Document overlap validation failed: {e}")
            return False
    
    def _validate_source_availability(self, query: str, compressed_pack: Dict) -> bool:
        """
        Validate that cached sources are still available in fresh results.
        
        Args:
            query: The normalized query
            compressed_pack: Compressed pack from cache
        
        Returns:
            True if sources are still available, False otherwise
        """
        try:
            sources = compressed_pack.get('sources', [])
            if not sources:
                return True  # No sources to validate
            
            # Get fresh results
            fresh_results = retriever.retrieve_top_chunks(query, k=settings.retrieve_k)
            fresh_doc_ids = set(result.get('doc_id', '') for result in fresh_results)
            
            # Check if cached sources are still in fresh results
            cached_doc_ids = set(source.get('doc_id', '') for source in sources)
            
            # Require high overlap between cached and fresh sources
            if not cached_doc_ids or not fresh_doc_ids:
                return len(sources) == 0
            
            overlap = jaccard_overlap(cached_doc_ids, fresh_doc_ids)
            threshold = 0.8  # Higher threshold for source availability
            
            logger.debug(f"Source availability overlap: {overlap:.3f} (threshold: {threshold})")
            
            return overlap >= threshold
            
        except Exception as e:
            logger.error(f"Source availability validation failed: {e}")
            return False
    
    def _validate_doc_versions(self, cached_doc_version_hash: str) -> bool:
        """
        Validate that document versions haven't changed significantly.
        
        Args:
            cached_doc_version_hash: Document version hash from cache
        
        Returns:
            True if versions are compatible, False otherwise
        """
        try:
            # Generate current version hash
            current_version_hash = self._generate_current_version_hash()
            
            # Compare with cached version
            is_valid = cached_doc_version_hash == current_version_hash
            
            if not is_valid:
                logger.debug(f"Version mismatch: cached={cached_doc_version_hash[:8]}..., current={current_version_hash[:8]}...")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Document version validation failed: {e}")
            return True  # Default to valid if validation fails
    
    def _generate_current_version_hash(self) -> str:
        """
        Generate current document version hash.
        
        Combines DOC_VERSION_SALT with any document metadata hashes.
        This allows forced invalidation by changing DOC_VERSION_SALT.
        
        Returns:
            Current version hash
        """
        # Start with global version salt
        version_components = [settings.doc_version_salt]
        
        # TODO: Add individual document version hashes if available
        # This would require tracking document update timestamps
        # For now, we rely on the global salt for invalidation
        
        combined = '|'.join(version_components)
        return hash_string(combined)
    
    def force_invalidate_cache(self, reason: str = "Manual invalidation"):
        """
        Force invalidate cache by updating version salt.
        
        Args:
            reason: Reason for invalidation (for logging)
        """
        logger.info(f"Force invalidating cache: {reason}")
        
        # In a production system, you might update DOC_VERSION_SALT
        # For now, we'll clear the cache entirely
        cache.clear_cache()
    
    def validate_cache_entry_freshness(self, cached_entry: CacheEntry, max_age_hours: int = 24) -> bool:
        """
        Validate that cache entry is not too old.
        
        Args:
            cached_entry: Cache entry to validate
            max_age_hours: Maximum age in hours
        
        Returns:
            True if entry is fresh enough, False if too old
        """
        try:
            from datetime import datetime, timedelta
            
            if not cached_entry.created_at:
                return False
            
            created_at = datetime.fromisoformat(cached_entry.created_at.replace('Z', '+00:00'))
            max_age = timedelta(hours=max_age_hours)
            
            is_fresh = datetime.utcnow() - created_at.replace(tzinfo=None) < max_age
            
            if not is_fresh:
                logger.debug(f"Cache entry too old: {created_at}")
            
            return is_fresh
            
        except Exception as e:
            logger.error(f"Freshness validation failed: {e}")
            return True  # Default to fresh if validation fails
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """
        Get cache validation statistics.
        
        Returns:
            Dictionary with validation metrics
        """
        # This would be implemented with proper metrics tracking
        # For now, return placeholder stats
        return {
            "total_validations": 0,
            "passed_validations": 0,
            "failed_overlap": 0,
            "failed_sources": 0,
            "failed_versions": 0,
            "validation_rate": 0.0
        }


# Global validator instance
validator = CacheValidator()

