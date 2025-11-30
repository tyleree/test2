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


# =============================================================================
# OPTION 7: Number/Percentage Verification (Zero Tokens)
# =============================================================================

def verify_numbers_in_response(response: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Verify that numbers and percentages in the response actually appear in source chunks.
    This catches common hallucinations like invented statistics or rating percentages.
    
    Args:
        response: The LLM response text
        chunks: List of source chunks used to generate the response
        
    Returns:
        Dict with verification results:
        - hallucinated_percentages: List of percentages not in sources
        - hallucinated_numbers: List of suspicious numbers not in sources
        - dc_codes_verified: Whether DC codes in response match sources
        - is_clean: True if no hallucinated numbers detected
    """
    # Combine all chunk text for searching
    chunk_text = " ".join(c.get("text", "") for c in chunks)
    chunk_text_lower = chunk_text.lower()
    
    # Extract percentages from response (e.g., "30%", "10 percent")
    response_percentages = set(re.findall(r'\b(\d+)%', response))
    response_percentages.update(re.findall(r'\b(\d+)\s*percent', response.lower()))
    
    # Extract percentages from chunks
    chunk_percentages = set(re.findall(r'\b(\d+)%', chunk_text))
    chunk_percentages.update(re.findall(r'\b(\d+)\s*percent', chunk_text_lower))
    
    # Find hallucinated percentages (in response but not in chunks)
    hallucinated_pct = response_percentages - chunk_percentages
    
    # VA-specific: Check diagnostic codes (7xxx format)
    response_dc_codes = set(re.findall(r'\b(7\d{3})\b', response))
    chunk_dc_codes = set(re.findall(r'\b(7\d{3})\b', chunk_text))
    hallucinated_dc = response_dc_codes - chunk_dc_codes
    
    # Check for suspiciously specific numbers that might be hallucinated
    # Focus on numbers that look like ratings or criteria (common hallucination targets)
    suspicious_patterns = [
        r'\b(\d+)\s*(?:days?|months?|years?)\b',  # Time periods
        r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # Dollar amounts
    ]
    
    hallucinated_specifics = []
    for pattern in suspicious_patterns:
        response_matches = set(re.findall(pattern, response, re.IGNORECASE))
        chunk_matches = set(re.findall(pattern, chunk_text, re.IGNORECASE))
        hallucinated_specifics.extend(response_matches - chunk_matches)
    
    is_clean = (len(hallucinated_pct) == 0 and 
                len(hallucinated_dc) == 0 and 
                len(hallucinated_specifics) == 0)
    
    result = {
        "hallucinated_percentages": list(hallucinated_pct),
        "hallucinated_dc_codes": list(hallucinated_dc),
        "hallucinated_specifics": hallucinated_specifics[:5],  # Limit to avoid noise
        "is_clean": is_clean,
        "issues": []
    }
    
    # Build issues list for logging
    if hallucinated_pct:
        result["issues"].append(f"Percentages not in sources: {', '.join(f'{p}%' for p in hallucinated_pct)}")
    if hallucinated_dc:
        result["issues"].append(f"DC codes not in sources: {', '.join(hallucinated_dc)}")
    if hallucinated_specifics:
        result["issues"].append(f"Suspicious numbers: {', '.join(str(s) for s in hallucinated_specifics[:3])}")
    
    return result


# =============================================================================
# OPTION 3: Clean Hallucinated Citations (Zero Tokens)
# =============================================================================

def clean_hallucinated_citations(response: str, max_valid_citation: int) -> str:
    """
    Remove citations from the response that reference non-existent sources.
    This is a post-processing step that costs zero tokens.
    
    Args:
        response: The LLM response text
        max_valid_citation: Maximum valid citation number (len(chunks))
        
    Returns:
        Cleaned response with invalid citations removed
    """
    cleaned = response
    
    # Remove superscript citations beyond valid range
    for i in range(max_valid_citation + 1, 20):  # Check up to 20
        superscript = NUM_TO_SUPERSCRIPT.get(i, '')
        if superscript and superscript in cleaned:
            print(f"[CITATION_CLEANUP] Removing hallucinated citation {superscript} (source {i} doesn't exist)")
            cleaned = cleaned.replace(superscript, '')
    
    # Remove [N] style citations beyond valid range
    def replace_bracket_citation(match):
        num = int(match.group(1))
        if num > max_valid_citation or num < 1:
            print(f"[CITATION_CLEANUP] Removing hallucinated citation [{num}]")
            return ''
        return match.group(0)
    
    cleaned = re.sub(r'\[(\d+)\]', replace_bracket_citation, cleaned)
    
    # Clean up Sources section - remove lines citing non-existent sources
    lines = cleaned.split('\n')
    cleaned_lines = []
    in_sources_section = False
    
    for line in lines:
        # Detect sources section
        if any(marker in line for marker in ['**Sources:**', 'Sources:', '**References:**']):
            in_sources_section = True
            cleaned_lines.append(line)
            continue
        
        if in_sources_section:
            # Check if this line cites a valid source
            # Match superscript or number at start of line
            source_match = re.match(r'^([¹²³⁴⁵⁶⁷⁸⁹⁰]+|\d+[\.\)])', line.strip())
            if source_match:
                num_str = source_match.group(1).rstrip('.)')
                # Convert superscript to number
                if num_str in SUPERSCRIPT_MAP:
                    num = SUPERSCRIPT_MAP[num_str]
                else:
                    try:
                        num = int(num_str)
                    except ValueError:
                        num = 0
                
                if num > max_valid_citation or num < 1:
                    print(f"[CITATION_CLEANUP] Removing source line for non-existent citation {num}")
                    continue  # Skip this line
        
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def sanitize_response(
    response: str, 
    chunks: List[Dict[str, Any]],
    remove_hallucinated_numbers: bool = False
) -> Tuple[str, Dict[str, Any]]:
    """
    Full response sanitization: verify and clean citations and numbers.
    
    Args:
        response: The LLM response text
        chunks: Source chunks used
        remove_hallucinated_numbers: If True, add warnings for hallucinated numbers
        
    Returns:
        Tuple of (cleaned_response, sanitization_report)
    """
    max_citation = len(chunks)
    
    # Step 1: Clean hallucinated citations
    cleaned = clean_hallucinated_citations(response, max_citation)
    
    # Step 2: Verify numbers
    number_check = verify_numbers_in_response(cleaned, chunks)
    
    # Step 3: Add warning prefix if hallucinated numbers detected
    if remove_hallucinated_numbers and not number_check["is_clean"]:
        issues = number_check["issues"]
        if issues:
            warning = "⚠️ **Note:** Some specific numbers in this response could not be verified against my sources. Please verify key statistics with official VA documentation.\n\n"
            # Only add warning if not already present
            if "could not be verified" not in cleaned:
                cleaned = warning + cleaned
    
    report = {
        "citations_cleaned": response != cleaned,
        "number_verification": number_check,
        "original_length": len(response),
        "cleaned_length": len(cleaned)
    }
    
    return cleaned, report

