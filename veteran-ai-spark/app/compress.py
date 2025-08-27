"""
Context compression module using small LLM to extract minimal verbatim quotes.
"""

import json
import logging
from typing import List, Dict, Any, Optional
import openai

from .settings import settings
from .utils import count_tokens, merge_and_deduplicate_quotes
from .schemas import CompressedPack

logger = logging.getLogger(__name__)


class ContextCompressor:
    """Compress context using small model to extract minimal verbatim quotes."""
    
    def __init__(self):
        self.client = None
    
    def _build_compression_prompt(self, query: str, passages: List[Dict[str, Any]]) -> str:
        """Build prompt for context compression."""
        
        # System prompt enforces verbatim extraction
        system_prompt = """You are a precise quote extraction assistant. Your task is to extract minimal verbatim quotes from passages that directly answer the user's question.

CRITICAL RULES:
1. Extract ONLY verbatim text - no paraphrasing or summarization
2. Keep quotes minimal but complete - around 50-120 tokens each
3. Only include quotes that directly address the question
4. Return valid JSON with the exact format specified
5. If a passage has no relevant information, omit it entirely

Return JSON format:
{
  "quotes": [
    {
      "doc_id": "document_id",
      "chunk_id": "chunk_identifier", 
      "url": "source_url",
      "quote": "exact verbatim text from passage"
    }
  ]
}"""

        # Build user prompt with passages
        passages_text = []
        for i, passage in enumerate(passages, 1):
            doc_id = passage.get('doc_id', f'doc_{i}')
            chunk_id = passage.get('chunk_id', f'chunk_{i}')
            url = passage.get('url', '')
            text = passage.get('text', '').strip()
            
            if text:
                passages_text.append(f"""
PASSAGE {i}:
Doc ID: {doc_id}
Chunk ID: {chunk_id}
URL: {url}
Text: {text}
""")
        
        user_prompt = f"""Question: {query}

{chr(10).join(passages_text)}

Extract minimal verbatim quotes that answer the question. Return JSON only."""

        return system_prompt, user_prompt
    
    def compress_context(
        self, 
        query: str, 
        passages: List[Dict[str, Any]], 
        max_tokens: int = None
    ) -> CompressedPack:
        """
        Compress passages into minimal verbatim quotes.
        
        Args:
            query: The user question
            passages: List of retrieved passages
            max_tokens: Token budget for compression (defaults to settings.compress_budget_tokens)
        
        Returns:
            CompressedPack with quotes, sources, and metadata
        """
        if max_tokens is None:
            max_tokens = settings.compress_budget_tokens
        
        if not passages:
            return CompressedPack(quotes=[], sources=[], top_doc_ids=[])
        
        try:
            # Build compression prompt
            system_prompt, user_prompt = self._build_compression_prompt(query, passages)
            
            # Initialize client if needed
            if self.client is None:
                self.client = openai.OpenAI(api_key=settings.openai_api_key)
            
            # Call small model for compression
            response = self.client.chat.completions.create(
                model=settings.model_small,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=min(max_tokens // 2, 1000),  # Leave room for quotes
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            content = response.choices[0].message.content.strip()
            result = json.loads(content)
            
            quotes = result.get('quotes', [])
            
            # Validate and clean quotes
            valid_quotes = []
            for quote in quotes:
                if (isinstance(quote, dict) and 
                    'quote' in quote and 
                    quote['quote'].strip()):
                    
                    # Ensure required fields
                    quote.setdefault('doc_id', 'unknown')
                    quote.setdefault('chunk_id', 'unknown')
                    quote.setdefault('url', '')
                    
                    valid_quotes.append(quote)
            
            # Merge and deduplicate within token budget
            final_quotes = merge_and_deduplicate_quotes(valid_quotes, max_tokens)
            
            # Extract unique sources
            sources = {}
            top_doc_ids = []
            
            for quote in final_quotes:
                doc_id = quote['doc_id']
                url = quote.get('url', '')
                
                if doc_id not in sources:
                    sources[doc_id] = {'doc_id': doc_id, 'url': url}
                    top_doc_ids.append(doc_id)
            
            sources_list = list(sources.values())
            
            logger.info(f"Compressed {len(passages)} passages to {len(final_quotes)} quotes, {len(sources_list)} sources")
            
            return CompressedPack(
                quotes=final_quotes,
                sources=sources_list,
                top_doc_ids=top_doc_ids
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed in compression: {e}")
            return self._fallback_compression(query, passages, max_tokens)
            
        except Exception as e:
            logger.error(f"Context compression failed: {e}")
            return self._fallback_compression(query, passages, max_tokens)
    
    def _fallback_compression(
        self, 
        query: str, 
        passages: List[Dict[str, Any]], 
        max_tokens: int
    ) -> CompressedPack:
        """
        Fallback compression using simple truncation.
        Used when LLM compression fails.
        """
        logger.warning("Using fallback compression due to LLM failure")
        
        quotes = []
        sources = {}
        top_doc_ids = []
        current_tokens = 0
        
        for passage in passages:
            text = passage.get('text', '').strip()
            if not text:
                continue
            
            # Truncate passage to fit budget
            passage_tokens = count_tokens(text)
            if current_tokens + passage_tokens > max_tokens:
                remaining_tokens = max_tokens - current_tokens
                if remaining_tokens < 50:  # Not worth including
                    break
                
                # Truncate text
                words = text.split()
                truncated_words = words[:int(len(words) * (remaining_tokens / passage_tokens))]
                text = ' '.join(truncated_words)
                
                if len(text) < 50:  # Too short to be useful
                    break
            
            doc_id = passage.get('doc_id', 'unknown')
            chunk_id = passage.get('chunk_id', 'unknown')
            url = passage.get('url', '')
            
            quotes.append({
                'doc_id': doc_id,
                'chunk_id': chunk_id,
                'url': url,
                'quote': text
            })
            
            if doc_id not in sources:
                sources[doc_id] = {'doc_id': doc_id, 'url': url}
                top_doc_ids.append(doc_id)
            
            current_tokens += count_tokens(text)
            
            if current_tokens >= max_tokens:
                break
        
        sources_list = list(sources.values())
        
        return CompressedPack(
            quotes=quotes,
            sources=sources_list,
            top_doc_ids=top_doc_ids
        )
    
    def estimate_compression_ratio(self, original_passages: List[Dict[str, Any]], compressed_pack: CompressedPack) -> float:
        """
        Estimate compression ratio achieved.
        
        Args:
            original_passages: Original passages before compression
            compressed_pack: Compressed result
        
        Returns:
            Compression ratio (0.0 to 1.0, lower is better compression)
        """
        original_tokens = sum(count_tokens(p.get('text', '')) for p in original_passages)
        compressed_tokens = sum(count_tokens(q.get('quote', '')) for q in compressed_pack.quotes)
        
        if original_tokens == 0:
            return 1.0
        
        ratio = compressed_tokens / original_tokens
        logger.info(f"Compression ratio: {ratio:.2f} ({original_tokens} -> {compressed_tokens} tokens)")
        
        return ratio


# Global compressor instance
compressor = ContextCompressor()

