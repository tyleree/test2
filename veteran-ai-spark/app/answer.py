"""
Answer generation system with citations and HTML sanitization.
Generates structured responses with numbered citations.
"""

import logging
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import openai
from bs4 import BeautifulSoup

from .config import config
from .compress import CompressionResult, Quote
from .utils import sanitize_html, get_token_count

logger = logging.getLogger(__name__)

@dataclass
class Citation:
    """Represents a citation with number and URL."""
    n: int
    url: str
    title: str = ""

@dataclass
class AnswerResult:
    """Complete answer result with all formats."""
    answer_plain: str
    answer_html: str
    citations: List[Citation]
    token_usage: Dict[str, int]
    status: str  # 'success', 'no_evidence', 'error'
    error_message: Optional[str] = None

class AnswerGenerator:
    """Generates answers with proper citations and formatting."""
    
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=config.openai_api_key)
    
    def prepare_answer_prompt(self, query: str, compression_result: CompressionResult) -> str:
        """Prepare the answer generation prompt."""
        
        if compression_result.status == 'no_evidence':
            return self._get_no_evidence_prompt(query)
        
        # Build quotes context with numbered references
        quotes_context = []
        citation_map = {}  # url -> citation number
        
        for i, quote in enumerate(compression_result.quotes, 1):
            # Assign citation numbers
            if quote.source_url not in citation_map:
                citation_map[quote.source_url] = len(citation_map) + 1
            
            citation_num = citation_map[quote.source_url]
            
            quote_text = f"[{citation_num}] {quote.text}"
            if quote.title or quote.section:
                source_info = " - "
                if quote.title:
                    source_info += quote.title
                if quote.section:
                    source_info += f" ({quote.section})"
                quote_text += source_info
            
            quotes_context.append(quote_text)
        
        quotes_text = "\n\n".join(quotes_context)
        
        # Build sources list
        sources_list = []
        for source in compression_result.sources:
            if source['url'] in citation_map:
                citation_num = citation_map[source['url']]
                sources_list.append(f"[{citation_num}] {source['url']} - {source.get('title', '')}")
        
        sources_text = "\n".join(sources_list)
        
        prompt = f"""Answer the user's question using ONLY the provided quotes. Follow these strict requirements:

REQUIREMENTS:
1. Use ONLY information from the provided quotes - no external knowledge
2. Cite every fact with [n] where n is the citation number
3. If the quotes don't fully answer the question, acknowledge the limitations
4. Write in a clear, helpful tone
5. Return response as valid JSON in the exact format specified below

QUESTION: {query}

QUOTES:
{quotes_text}

SOURCES:
{sources_text}

Return your response as valid JSON in this exact format:
{{
  "answer_plain": "Your answer here with citations [1], [2], etc.",
  "answer_html": "<p>Your answer with HTML formatting and citations [1], [2], etc.</p><p><strong>Sources</strong></p><ol><li><a href='url'>[1] Title</a></li><li><a href='url'>[2] Title</a></li></ol>",
  "citations": [
    {{"n": 1, "url": "https://...", "title": "Source Title"}},
    {{"n": 2, "url": "https://...", "title": "Source Title"}}
  ]
}}

HTML FORMATTING RULES:
- Use <p> for paragraphs
- Use <ul><li> for bullet lists
- Use <ol><li> for numbered lists
- Use <strong> for emphasis
- Use <em> for italics
- End with Sources section: <p><strong>Sources</strong></p><ol><li><a href='url'>[n] Title</a></li></ol>
- Only use allowed HTML tags: p, ul, ol, li, strong, em, a, br, h3

</END>"""
        
        return prompt
    
    def _get_no_evidence_prompt(self, query: str) -> str:
        """Get prompt for no evidence case."""
        return f"""The user asked: "{query}"

However, no relevant evidence was found in the knowledge base to answer this question.

Return a helpful response in JSON format:
{{
  "answer_plain": "I don't have sufficient information in my knowledge base to answer this question about [topic]. For accurate information, please consult official VA resources or speak with a VA representative.",
  "answer_html": "<p>I don't have sufficient information in my knowledge base to answer this question about [topic]. For accurate information, please consult official VA resources or speak with a VA representative.</p>",
  "citations": []
}}

Replace [topic] with the relevant topic from the user's question.

</END>"""
    
    def parse_answer_response(self, response: str, compression_result: CompressionResult) -> AnswerResult:
        """Parse and validate the answer response."""
        try:
            # Clean response
            response = response.strip()
            if response.endswith('</END>'):
                response = response[:-6].strip()
            
            # Parse JSON
            data = json.loads(response)
            
            # Validate required fields
            required_fields = ['answer_plain', 'answer_html', 'citations']
            for field in required_fields:
                if field not in data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Extract data
            answer_plain = data['answer_plain'].strip()
            answer_html = data['answer_html'].strip()
            citations_data = data['citations']
            
            # Validate and sanitize HTML
            answer_html = sanitize_html(answer_html)
            
            # Process citations
            citations = []
            for citation_data in citations_data:
                if isinstance(citation_data, dict) and all(k in citation_data for k in ['n', 'url']):
                    citation = Citation(
                        n=int(citation_data['n']),
                        url=citation_data['url'],
                        title=citation_data.get('title', '')
                    )
                    citations.append(citation)
            
            # Sort citations by number
            citations.sort(key=lambda x: x.n)
            
            # Validate citations are used in text
            cited_numbers = set(re.findall(r'\[(\d+)\]', answer_plain))
            citation_numbers = {str(c.n) for c in citations}
            
            if cited_numbers != citation_numbers:
                logger.warning(f"Citation mismatch - used: {cited_numbers}, defined: {citation_numbers}")
            
            # Determine status
            status = 'no_evidence' if not citations else 'success'
            
            return AnswerResult(
                answer_plain=answer_plain,
                answer_html=answer_html,
                citations=citations,
                token_usage={},  # Will be filled by caller
                status=status
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse answer response as JSON: {e}")
            return self._create_error_result(f"JSON parsing error: {e}")
        except Exception as e:
            logger.error(f"Error processing answer response: {e}")
            return self._create_error_result(f"Processing error: {e}")
    
    def _create_error_result(self, error_message: str) -> AnswerResult:
        """Create an error result."""
        return AnswerResult(
            answer_plain="I apologize, but I encountered an error while generating the response. Please try again.",
            answer_html="<p>I apologize, but I encountered an error while generating the response. Please try again.</p>",
            citations=[],
            token_usage={},
            status='error',
            error_message=error_message
        )
    
    def _create_no_evidence_result(self, query: str) -> AnswerResult:
        """Create a no evidence result."""
        # Extract topic from query for more helpful message
        topic = "this topic"
        if "rating" in query.lower():
            topic = "VA ratings"
        elif "benefit" in query.lower():
            topic = "VA benefits"
        elif "disability" in query.lower():
            topic = "VA disability"
        elif "healthcare" in query.lower() or "health care" in query.lower():
            topic = "VA healthcare"
        
        answer_plain = f"I don't have sufficient information in my knowledge base to answer this question about {topic}. For accurate information, please consult official VA resources or speak with a VA representative."
        answer_html = f"<p>I don't have sufficient information in my knowledge base to answer this question about {topic}. For accurate information, please consult official VA resources or speak with a VA representative.</p>"
        
        return AnswerResult(
            answer_plain=answer_plain,
            answer_html=answer_html,
            citations=[],
            token_usage={},
            status='no_evidence'
        )
    
    def generate_answer(self, query: str, compression_result: CompressionResult) -> AnswerResult:
        """Main answer generation function."""
        logger.info(f"Generating answer for query: '{query[:50]}...'")
        
        # Handle no evidence case
        if compression_result.status == 'no_evidence':
            return self._create_no_evidence_result(query)
        
        # Handle compression error
        if compression_result.status == 'error':
            return self._create_error_result(compression_result.error_message or "Compression failed")
        
        # Prepare prompt
        prompt = self.prepare_answer_prompt(query, compression_result)
        
        try:
            # Make deterministic API call
            response = self.openai_client.chat.completions.create(
                model=config.model_big,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                max_tokens=1500,
                stop=["</END>"]
            )
            
            response_text = response.choices[0].message.content
            
            # Track token usage
            token_usage = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }
            
            # Parse response
            result = self.parse_answer_response(response_text, compression_result)
            result.token_usage = token_usage
            
            logger.info(f"Answer generation complete: {result.status}, {len(result.citations)} citations")
            return result
            
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return self._create_error_result(str(e))
    
    def get_debug_info(self, result: AnswerResult) -> Dict[str, Any]:
        """Get debug information about answer generation."""
        return {
            'status': result.status,
            'citations_count': len(result.citations),
            'token_usage': result.token_usage,
            'answer_length': {
                'plain': len(result.answer_plain),
                'html': len(result.answer_html)
            },
            'error_message': result.error_message,
            'citations': [
                {
                    'n': citation.n,
                    'url': citation.url,
                    'title': citation.title
                }
                for citation in result.citations
            ],
            'html_valid': self._validate_html_structure(result.answer_html)
        }
    
    def _validate_html_structure(self, html: str) -> Dict[str, Any]:
        """Validate HTML structure for debugging."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Check for required elements
            has_paragraphs = len(soup.find_all('p')) > 0
            has_sources = 'Sources' in html or 'sources' in html.lower()
            has_citations = len(re.findall(r'\[\d+\]', html)) > 0
            has_links = len(soup.find_all('a')) > 0
            
            # Check tag usage
            all_tags = [tag.name for tag in soup.find_all()]
            allowed_tags = {'p', 'ul', 'ol', 'li', 'strong', 'em', 'a', 'br', 'h3'}
            invalid_tags = set(all_tags) - allowed_tags
            
            return {
                'valid': len(invalid_tags) == 0,
                'has_paragraphs': has_paragraphs,
                'has_sources': has_sources,
                'has_citations': has_citations,
                'has_links': has_links,
                'invalid_tags': list(invalid_tags),
                'tag_counts': {tag: all_tags.count(tag) for tag in set(all_tags)}
            }
            
        except Exception as e:
            return {'valid': False, 'error': str(e)}