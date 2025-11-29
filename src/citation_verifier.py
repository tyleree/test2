"""
Citation Verification for RAG Pipeline

This module verifies that citations in LLM responses actually correspond
to information in the cited source chunks. Helps detect hallucinated citations.

Features:
- Extract citation references from response text
- Match citations to source chunks
- Verify cited claims appear in the referenced chunks
- Generate verification scores and flags
"""

import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass


# Superscript number mapping
SUPERSCRIPT_MAP = {
    '¹': 1, '²': 2, '³': 3, '⁴': 4, '⁵': 5,
    '⁶': 6, '⁷': 7, '⁸': 8, '⁹': 9, '⁰': 0,
    '¹⁰': 10, '¹¹': 11, '¹²': 12
}

# Reverse mapping for display
NUM_TO_SUPERSCRIPT = {v: k for k, v in SUPERSCRIPT_MAP.items()}


@dataclass
class CitationCheck:
    """Result of checking a single citation."""
    citation_number: int
    cited_text: str  # Text near the citation
    source_url: Optional[str]
    source_topic: Optional[str]
    found_in_source: bool
    confidence: float  # 0-1 confidence that the claim is in the source
    issues: List[str]


@dataclass
class VerificationResult:
    """Complete verification result for a response."""
    total_citations: int
    verified_citations: int
    suspicious_citations: int
    verification_score: float  # 0-1 overall score
    checks: List[CitationCheck]
    overall_issues: List[str]


def extract_citations_from_response(response: str) -> List[Tuple[int, str]]:
    """
    Extract citation numbers and their surrounding text from a response.
    
    Args:
        response: The LLM response text
        
    Returns:
        List of tuples (citation_number, surrounding_text)
    """
    citations = []
    
    # Pattern to find superscript numbers (¹²³ etc) with context
    # Capture text before the citation for context
    patterns = [
        # Superscript numbers: "text¹"
        (r'([^.!?\n]{10,100})[¹²³⁴⁵⁶⁷⁸⁹⁰]+', 'superscript'),
        # Bracketed numbers: "text[1]" or "text [1]"
        (r'([^.!?\n]{10,100})\s*\[(\d+)\]', 'bracket'),
    ]
    
    for pattern, style in patterns:
        for match in re.finditer(pattern, response):
            context_text = match.group(1).strip()
            
            if style == 'superscript':
                # Extract the superscript number
                full_match = match.group(0)
                superscript_part = full_match[len(context_text):]
                
                # Parse superscript to number
                for char, num in SUPERSCRIPT_MAP.items():
                    if char in superscript_part:
                        citations.append((num, context_text))
                        break
            else:
                # Bracket style [1]
                num = int(match.group(2))
                citations.append((num, context_text))
    
    return citations


def extract_source_references(response: str) -> Dict[int, Dict[str, str]]:
    """
    Extract the Sources section from the response and map numbers to URLs/titles.
    
    Args:
        response: The LLM response text
        
    Returns:
        Dict mapping citation numbers to source info {url, title}
    """
    sources = {}
    
    # Find Sources section
    sources_section = None
    for marker in ['**Sources:**', 'Sources:', '**References:**', 'References:']:
        if marker in response:
            idx = response.find(marker)
            sources_section = response[idx:]
            break
    
    if not sources_section:
        return sources
    
    # Parse source lines
    # Format: ¹ [Title](URL) or 1. [Title](URL)
    patterns = [
        # Superscript format: ¹ [Title](URL)
        r'([¹²³⁴⁵⁶⁷⁸⁹⁰]+)\s*\[([^\]]+)\]\(([^)]+)\)',
        # Numbered format: 1. [Title](URL)
        r'(\d+)[\.\)]\s*\[([^\]]+)\]\(([^)]+)\)',
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, sources_section):
            num_str = match.group(1)
            title = match.group(2)
            url = match.group(3)
            
            # Convert to integer
            if num_str in SUPERSCRIPT_MAP:
                num = SUPERSCRIPT_MAP[num_str]
            else:
                try:
                    num = int(num_str)
                except ValueError:
                    continue
            
            sources[num] = {"title": title, "url": url}
    
    return sources


def verify_citation_in_chunk(
    cited_text: str,
    chunk_content: str,
    threshold: float = 0.3
) -> Tuple[bool, float]:
    """
    Verify that a cited claim appears in the source chunk.
    
    Uses keyword overlap as a simple verification method.
    
    Args:
        cited_text: The text near the citation (the claimed fact)
        chunk_content: The full content of the source chunk
        threshold: Minimum overlap ratio to consider verified
        
    Returns:
        Tuple of (is_verified, confidence_score)
    """
    # Normalize texts
    cited_lower = cited_text.lower()
    chunk_lower = chunk_content.lower()
    
    # Extract significant words (skip common words)
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                  'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                  'would', 'could', 'should', 'may', 'might', 'can', 'to', 'of',
                  'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'or',
                  'and', 'but', 'if', 'than', 'because', 'when', 'where', 'how',
                  'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
                  'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
                  'than', 'too', 'very', 'just', 'your', 'their', 'this', 'that'}
    
    # Extract words from cited text
    cited_words = set(
        word for word in re.findall(r'\b\w+\b', cited_lower)
        if len(word) > 2 and word not in stop_words
    )
    
    if not cited_words:
        return True, 0.5  # No significant words to check
    
    # Count how many appear in chunk
    found_words = sum(1 for word in cited_words if word in chunk_lower)
    overlap_ratio = found_words / len(cited_words)
    
    # Also check for key numbers/percentages
    numbers_in_cited = set(re.findall(r'\d+%?', cited_text))
    if numbers_in_cited:
        numbers_found = sum(1 for n in numbers_in_cited if n in chunk_content)
        number_ratio = numbers_found / len(numbers_in_cited)
        # Numbers are important - weight them more
        overlap_ratio = (overlap_ratio + number_ratio * 2) / 3
    
    is_verified = overlap_ratio >= threshold
    return is_verified, overlap_ratio


def verify_citations(
    response: str,
    chunks: List[Dict[str, Any]]
) -> VerificationResult:
    """
    Verify all citations in a response against the source chunks.
    
    Args:
        response: The LLM response text
        chunks: List of source chunks (with 'text', 'metadata' keys)
        
    Returns:
        VerificationResult with detailed check results
    """
    # Extract citations from response
    citations = extract_citations_from_response(response)
    source_refs = extract_source_references(response)
    
    checks = []
    verified_count = 0
    suspicious_count = 0
    overall_issues = []
    
    # Build chunk index by citation number (1-based from context order)
    chunk_by_index = {i+1: chunk for i, chunk in enumerate(chunks)}
    
    for citation_num, cited_text in citations:
        check = CitationCheck(
            citation_number=citation_num,
            cited_text=cited_text,
            source_url=None,
            source_topic=None,
            found_in_source=False,
            confidence=0.0,
            issues=[]
        )
        
        # Get source info from Sources section
        if citation_num in source_refs:
            check.source_url = source_refs[citation_num].get("url")
            check.source_topic = source_refs[citation_num].get("title")
        else:
            check.issues.append(f"Citation {citation_num} not found in Sources section")
        
        # Find corresponding chunk
        if citation_num in chunk_by_index:
            chunk = chunk_by_index[citation_num]
            chunk_text = chunk.get("text", "")
            chunk_meta = chunk.get("metadata", {})
            
            # Verify the citation
            is_verified, confidence = verify_citation_in_chunk(cited_text, chunk_text)
            check.found_in_source = is_verified
            check.confidence = confidence
            
            if not is_verified:
                check.issues.append(f"Low confidence ({confidence:.2f}) that claim appears in source")
                suspicious_count += 1
            else:
                verified_count += 1
            
            # Check URL consistency
            chunk_url = chunk_meta.get("url") or chunk_meta.get("source_url")
            if check.source_url and chunk_url:
                if check.source_url != chunk_url:
                    check.issues.append(f"URL mismatch: cited {check.source_url} but chunk has {chunk_url}")
        else:
            check.issues.append(f"Citation {citation_num} has no corresponding source chunk")
            suspicious_count += 1
        
        checks.append(check)
    
    # Calculate overall score
    total = len(citations)
    if total > 0:
        verification_score = verified_count / total
    else:
        verification_score = 1.0  # No citations to verify
    
    # Add overall issues
    if suspicious_count > total * 0.3:
        overall_issues.append(f"High rate of suspicious citations ({suspicious_count}/{total})")
    
    # Check for citations beyond chunk count
    max_chunk = len(chunks)
    for check in checks:
        if check.citation_number > max_chunk:
            overall_issues.append(f"Citation {check.citation_number} exceeds chunk count ({max_chunk})")
    
    return VerificationResult(
        total_citations=total,
        verified_citations=verified_count,
        suspicious_citations=suspicious_count,
        verification_score=verification_score,
        checks=checks,
        overall_issues=overall_issues
    )


def get_verification_summary(result: VerificationResult) -> Dict[str, Any]:
    """
    Get a summary dict suitable for logging/analytics.
    
    Args:
        result: VerificationResult from verify_citations
        
    Returns:
        Dict with summary statistics
    """
    return {
        "total_citations": result.total_citations,
        "verified": result.verified_citations,
        "suspicious": result.suspicious_citations,
        "score": result.verification_score,
        "issues_count": len(result.overall_issues) + sum(len(c.issues) for c in result.checks),
        "overall_issues": result.overall_issues
    }

