"""
Quote-only compression system using deterministic LLM calls.
Extracts minimal verbatim spans from reranked candidates.
"""

import logging
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import openai

from .config import config
from .rerank import RerankedCandidate
from .utils import get_token_count

logger = logging.getLogger(__name__)

@dataclass
class Quote:
    """Represents a compressed quote with source information."""
    text: str
    source_url: str
    title: str
    section: str
    chunk_id: str
    token_count: int

@dataclass
class CompressionResult:
    """Result of the compression process."""
    quotes: List[Quote]
    sources: List[Dict[str, str]]
    total_tokens: int
    compression_ratio: float
    status: str  # 'success', 'no_evidence', 'error'
    error_message: Optional[str] = None

class QuoteCompressor:
    """Compresses reranked candidates into minimal quotes."""
    
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=config.openai_api_key)
    
    def prepare_compression_prompt(self, query: str, candidates: List[RerankedCandidate]) -> str:
        """Prepare the compression prompt with candidates."""
        
        # Build context from candidates
        context_parts = []
        for i, candidate in enumerate(candidates, 1):
            source_info = f"Source {i}: {candidate.source_url}"
            if candidate.title:
                source_info += f" - {candidate.title}"
            if candidate.section:
                source_info += f" ({candidate.section})"
            
            context_parts.append(f"{source_info}\n{candidate.text}\n")
        
        context = "\n".join(context_parts)
        
        prompt = f"""Extract minimal verbatim quotes from the provided sources that directly answer the user's question. Follow these strict requirements:

REQUIREMENTS:
1. Copy EXACT text spans only - no paraphrasing or summarization
2. Each quote must be ≤{config.quote_max_tokens} tokens
3. Maximum {config.max_quotes} quotes total
4. Only include quotes that directly answer the question
5. Each quote must include its source URL

QUESTION: {query}

SOURCES:
{context}

Return your response as valid JSON in this exact format:
{{
  "quotes": [
    {{
      "text": "exact verbatim quote here",
      "source_url": "https://...",
      "source_title": "document title",
      "source_section": "section name if any"
    }}
  ],
  "sources": [
    {{
      "url": "https://...",
      "title": "document title"
    }}
  ]
}}

If no relevant quotes can be found, return:
{{
  "quotes": [],
  "sources": [],
  "no_evidence": true
}}

</END>"""
        
        return prompt
    
    def parse_compression_response(self, response: str, candidates: List[RerankedCandidate]) -> CompressionResult:
        """Parse and validate the compression response."""
        try:
            # Clean response
            response = response.strip()
            if response.endswith('</END>'):
                response = response[:-6].strip()
            
            # Parse JSON
            data = json.loads(response)
            
            # Check for no evidence
            if data.get('no_evidence', False):
                return CompressionResult(
                    quotes=[],
                    sources=[],
                    total_tokens=0,
                    compression_ratio=0.0,
                    status='no_evidence'
                )
            
            # Validate structure
            if 'quotes' not in data or 'sources' not in data:
                raise ValueError("Missing required fields: quotes, sources")
            
            # Create candidate lookup for chunk_id mapping
            candidate_lookup = {candidate.source_url: candidate for candidate in candidates}
            
            # Process quotes
            quotes = []
            for quote_data in data['quotes']:
                if not isinstance(quote_data, dict):
                    continue
                
                quote_text = quote_data.get('text', '').strip()
                source_url = quote_data.get('source_url', '').strip()
                
                if not quote_text or not source_url:
                    continue
                
                # Find corresponding candidate for chunk_id
                candidate = candidate_lookup.get(source_url)
                chunk_id = candidate.chunk_id if candidate else 'unknown'
                
                # Validate quote length
                quote_tokens = get_token_count(quote_text)
                if quote_tokens > config.quote_max_tokens:
                    logger.warning(f"Quote exceeds token limit ({quote_tokens} > {config.quote_max_tokens}), truncating")
                    # Truncate quote (rough approximation)
                    words = quote_text.split()
                    truncated_words = words[:config.quote_max_tokens]
                    quote_text = ' '.join(truncated_words)
                    quote_tokens = get_token_count(quote_text)
                
                quote = Quote(
                    text=quote_text,
                    source_url=source_url,
                    title=quote_data.get('source_title', ''),
                    section=quote_data.get('source_section', ''),
                    chunk_id=chunk_id,
                    token_count=quote_tokens
                )
                quotes.append(quote)
            
            # Limit number of quotes
            if len(quotes) > config.max_quotes:
                logger.warning(f"Too many quotes ({len(quotes)} > {config.max_quotes}), keeping first {config.max_quotes}")
                quotes = quotes[:config.max_quotes]
            
            # Process sources
            sources = []
            for source_data in data['sources']:
                if isinstance(source_data, dict) and 'url' in source_data:
                    sources.append({
                        'url': source_data['url'],
                        'title': source_data.get('title', '')
                    })
            
            # Calculate metrics
            total_tokens = sum(quote.token_count for quote in quotes)
            original_tokens = sum(candidate.token_count for candidate in candidates)
            compression_ratio = 1.0 - (total_tokens / original_tokens) if original_tokens > 0 else 0.0
            
            return CompressionResult(
                quotes=quotes,
                sources=sources,
                total_tokens=total_tokens,
                compression_ratio=compression_ratio,
                status='success'
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse compression response as JSON: {e}")
            return CompressionResult(
                quotes=[],
                sources=[],
                total_tokens=0,
                compression_ratio=0.0,
                status='error',
                error_message=f"JSON parsing error: {e}"
            )
        except Exception as e:
            logger.error(f"Error processing compression response: {e}")
            return CompressionResult(
                quotes=[],
                sources=[],
                total_tokens=0,
                compression_ratio=0.0,
                status='error',
                error_message=f"Processing error: {e}"
            )
    
    def compress(self, query: str, candidates: List[RerankedCandidate]) -> CompressionResult:
        """Main compression function."""
        if not candidates:
            return CompressionResult(
                quotes=[],
                sources=[],
                total_tokens=0,
                compression_ratio=0.0,
                status='no_evidence'
            )
        
        logger.info(f"Compressing {len(candidates)} candidates for query: '{query[:50]}...'")
        
        # Prepare prompt
        prompt = self.prepare_compression_prompt(query, candidates)
        
        # Check if prompt is too long
        prompt_tokens = get_token_count(prompt)
        if prompt_tokens > config.compress_budget_tokens:
            logger.warning(f"Prompt too long ({prompt_tokens} tokens), truncating candidates")
            # Reduce candidates to fit budget
            while prompt_tokens > config.compress_budget_tokens and len(candidates) > 1:
                candidates = candidates[:-1]
                prompt = self.prepare_compression_prompt(query, candidates)
                prompt_tokens = get_token_count(prompt)
        
        try:
            # Make deterministic API call
            response = self.openai_client.chat.completions.create(
                model=config.model_small,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                top_p=1,
                max_tokens=1000,
                stop=["</END>"]
            )
            
            response_text = response.choices[0].message.content
            
            # Parse response
            result = self.parse_compression_response(response_text, candidates)
            
            # Validate token budget
            if result.total_tokens > config.compress_budget_tokens:
                logger.warning(f"Compressed quotes exceed budget ({result.total_tokens} > {config.compress_budget_tokens})")
                # Truncate quotes to fit budget
                budget_remaining = config.compress_budget_tokens
                filtered_quotes = []
                
                for quote in result.quotes:
                    if quote.token_count <= budget_remaining:
                        filtered_quotes.append(quote)
                        budget_remaining -= quote.token_count
                    else:
                        break
                
                result.quotes = filtered_quotes
                result.total_tokens = sum(q.token_count for q in filtered_quotes)
            
            logger.info(f"Compression complete: {len(result.quotes)} quotes, {result.total_tokens} tokens, {result.compression_ratio:.2%} compression")
            return result
            
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return CompressionResult(
                quotes=[],
                sources=[],
                total_tokens=0,
                compression_ratio=0.0,
                status='error',
                error_message=str(e)
            )
    
    def get_debug_info(self, result: CompressionResult) -> Dict[str, Any]:
        """Get debug information about compression result."""
        return {
            'status': result.status,
            'quotes_count': len(result.quotes),
            'sources_count': len(result.sources),
            'total_tokens': result.total_tokens,
            'compression_ratio': round(result.compression_ratio, 3),
            'token_budget': config.compress_budget_tokens,
            'max_quotes': config.max_quotes,
            'quote_max_tokens': config.quote_max_tokens,
            'error_message': result.error_message,
            'quotes_preview': [
                {
                    'text': quote.text[:100] + "..." if len(quote.text) > 100 else quote.text,
                    'source_url': quote.source_url,
                    'token_count': quote.token_count
                }
                for quote in result.quotes[:3]  # First 3 quotes for debug
            ]
        }