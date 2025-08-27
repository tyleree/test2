"""
Answer generation module using big model with compressed context.
"""

import logging
from typing import List, Dict, Any, Tuple
import openai

from .settings import settings
from .utils import format_citations, validate_and_clean_response, count_tokens
from .schemas import CompressedPack, Citation, TokenUsage

logger = logging.getLogger(__name__)


class AnswerGenerator:
    """Generate final answers using big model with compressed context."""
    
    def __init__(self):
        self.client = None
    
    def _build_answer_prompt(self, query: str, compressed_pack: CompressedPack) -> Tuple[str, str]:
        """Build system and user prompts for answer generation."""
        
        # System prompt enforces citation format and source usage
        system_prompt = """You are a helpful AI assistant that provides accurate, well-sourced answers. 

CRITICAL RULES:
1. Use ONLY the provided quotes to answer the question
2. Cite sources using [n] format where n matches the source number
3. Every factual claim must be cited
4. If the quotes don't contain enough information, say so clearly
5. Keep answers concise but comprehensive (300-700 tokens target)
6. Maintain a professional, informative tone
7. Do not make assumptions beyond what's explicitly stated in the quotes

CITATION FORMAT:
- Use [1], [2], etc. to cite sources
- Numbers correspond to the source list provided
- Multiple citations can be used: [1][2] or [1, 2]

If you cannot adequately answer based on the provided quotes, respond with: "I don't have enough information in the provided sources to fully answer that question."""

        # Build user prompt with quotes and sources
        if not compressed_pack.quotes:
            user_prompt = f"""Question: {query}

No relevant quotes were found to answer this question."""
            return system_prompt, user_prompt
        
        # Format quotes
        quotes_text = []
        for i, quote in enumerate(compressed_pack.quotes, 1):
            quote_text = quote.get('quote', '').strip()
            if quote_text:
                quotes_text.append(f"Quote {i}: {quote_text}")
        
        # Format sources
        sources_text = []
        for i, source in enumerate(compressed_pack.sources, 1):
            url = source.get('url', 'No URL')
            doc_id = source.get('doc_id', 'Unknown')
            sources_text.append(f"[{i}] {doc_id} ({url})")
        
        user_prompt = f"""Question: {query}

QUOTES:
{chr(10).join(quotes_text)}

SOURCES:
{chr(10).join(sources_text)}

Please provide a comprehensive answer using only the information from these quotes. Cite each source using [n] format."""

        return system_prompt, user_prompt
    
    def generate_answer(
        self, 
        query: str, 
        compressed_pack: CompressedPack,
        max_tokens: int = 700
    ) -> Tuple[str, List[Citation], Dict[str, Any]]:
        """
        Generate answer using big model with compressed context.
        
        Args:
            query: The user question
            compressed_pack: Compressed context with quotes and sources
            max_tokens: Maximum tokens for answer generation
        
        Returns:
            Tuple of (answer, citations, token_usage_info)
        """
        try:
            # Build prompts
            system_prompt, user_prompt = self._build_answer_prompt(query, compressed_pack)
            
            # Calculate input tokens for monitoring
            input_tokens = count_tokens(system_prompt + user_prompt, settings.model_big)
            
            # Initialize client if needed
            if self.client is None:
                self.client = openai.OpenAI(api_key=settings.openai_api_key)
            
            # Generate answer using big model
            response = self.client.chat.completions.create(
                model=settings.model_big,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0,  # Deterministic for consistency
                presence_penalty=0.1,  # Slight penalty for repetition
                frequency_penalty=0.1
            )
            
            # Extract answer
            answer = response.choices[0].message.content.strip()
            
            # Validate and clean answer
            answer = validate_and_clean_response(answer)
            
            # Extract token usage
            usage = response.usage
            output_tokens = usage.completion_tokens if usage else count_tokens(answer, settings.model_big)
            
            token_usage_info = {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': input_tokens + output_tokens,
                'model': settings.model_big
            }
            
            # Format citations from sources
            citations = format_citations(compressed_pack.sources)
            
            logger.info(f"Generated answer: {len(answer)} chars, {output_tokens} tokens, {len(citations)} citations")
            
            return answer, citations, token_usage_info
            
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            
            # Fallback response
            fallback_answer = "I apologize, but I'm unable to generate an answer at this time due to a technical issue. Please try again."
            fallback_citations = []
            fallback_usage = {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'model': settings.model_big,
                'error': str(e)
            }
            
            return fallback_answer, fallback_citations, fallback_usage
    
    def enhance_answer_with_detail(
        self, 
        original_answer: str,
        query: str, 
        compressed_pack: CompressedPack,
        max_tokens: int = 1000
    ) -> Tuple[str, List[Citation], Dict[str, Any]]:
        """
        Enhance existing answer with more detail.
        Used when user requests more detail via ?detail=more parameter.
        
        Args:
            original_answer: Previously generated answer
            query: The user question
            compressed_pack: Compressed context (may be expanded)
            max_tokens: Maximum tokens for enhanced answer
        
        Returns:
            Tuple of (enhanced_answer, citations, token_usage_info)
        """
        try:
            # Build enhanced prompt
            system_prompt = """You are a helpful AI assistant providing detailed, comprehensive answers.

TASK: Expand the previous answer with more detail and context while maintaining accuracy.

RULES:
1. Use ONLY the provided quotes to expand the answer
2. Maintain all existing citations and add new ones as needed
3. Provide more comprehensive coverage of the topic
4. Include additional context and nuance where supported by quotes
5. Keep the enhanced answer well-structured and readable
6. Target 500-1000 tokens for detailed response

CITATION FORMAT: Use [1], [2], etc. matching the source list."""

            # Format quotes and sources
            quotes_text = []
            for i, quote in enumerate(compressed_pack.quotes, 1):
                quote_text = quote.get('quote', '').strip()
                if quote_text:
                    quotes_text.append(f"Quote {i}: {quote_text}")
            
            sources_text = []
            for i, source in enumerate(compressed_pack.sources, 1):
                url = source.get('url', 'No URL')
                doc_id = source.get('doc_id', 'Unknown')
                sources_text.append(f"[{i}] {doc_id} ({url})")
            
            user_prompt = f"""Original Question: {query}

Previous Answer: {original_answer}

QUOTES FOR EXPANSION:
{chr(10).join(quotes_text)}

SOURCES:
{chr(10).join(sources_text)}

Please provide a more detailed and comprehensive answer using the quotes above. Expand on the previous answer with additional context, examples, and nuance where supported by the quotes."""

            # Initialize client if needed
            if self.client is None:
                self.client = openai.OpenAI(api_key=settings.openai_api_key)
            
            # Generate enhanced answer
            response = self.client.chat.completions.create(
                model=settings.model_big,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.1,  # Slightly more creative for detail
                presence_penalty=0.1,
                frequency_penalty=0.1
            )
            
            enhanced_answer = response.choices[0].message.content.strip()
            enhanced_answer = validate_and_clean_response(enhanced_answer)
            
            # Token usage
            usage = response.usage
            input_tokens = count_tokens(system_prompt + user_prompt, settings.model_big)
            output_tokens = usage.completion_tokens if usage else count_tokens(enhanced_answer, settings.model_big)
            
            token_usage_info = {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': input_tokens + output_tokens,
                'model': settings.model_big,
                'enhancement': True
            }
            
            citations = format_citations(compressed_pack.sources)
            
            logger.info(f"Enhanced answer: {len(enhanced_answer)} chars, {output_tokens} tokens")
            
            return enhanced_answer, citations, token_usage_info
            
        except Exception as e:
            logger.error(f"Answer enhancement failed: {e}")
            # Return original answer if enhancement fails
            return original_answer, format_citations(compressed_pack.sources), {'error': str(e)}
    
    def validate_citations(self, answer: str, citations: List[Citation]) -> bool:
        """
        Validate that answer contains proper citations.
        
        Args:
            answer: Generated answer text
            citations: List of citations
        
        Returns:
            True if citations are properly formatted, False otherwise
        """
        if not citations:
            return '[' not in answer  # No citations expected
        
        # Check if answer contains citation markers
        citation_markers = []
        for i in range(1, len(citations) + 1):
            if f'[{i}]' in answer:
                citation_markers.append(i)
        
        # Should have at least some citations if sources are provided
        has_citations = len(citation_markers) > 0
        
        if not has_citations:
            logger.warning("Generated answer lacks proper citations")
        
        return has_citations


# Global answer generator instance
answer_generator = AnswerGenerator()

