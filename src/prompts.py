"""
RAG Prompts for Veterans Benefits AI

This module contains system prompts and prompt building functions for the RAG pipeline.
The prompts are designed to:
- Keep answers grounded in the provided context
- Include proper citations with source URLs
- Handle cases where context is insufficient
- Maintain a helpful, accurate tone for veterans
"""

from typing import List, Dict, Any, Optional

# System prompt for the RAG assistant
SYSTEM_PROMPT = """You are a helpful AI assistant specializing in VA (Veterans Affairs) disability benefits and claims. Your role is to provide accurate, helpful information to veterans based ONLY on the provided context.

CRITICAL RULES:
1. ONLY answer based on the information provided in the Context section below
2. If the context doesn't contain enough information to fully answer the question, say so clearly
3. NEVER make up information, ratings, percentages, or procedures not in the context
4. When citing information, use this format: [source: TITLE](URL)
5. If multiple sources support your answer, cite all relevant ones
6. Be empathetic and supportive - remember you're helping veterans

CITATION FORMAT:
- When referencing specific information, cite it like this: [source: High Blood Pressure](https://veteransbenefitskb.com/bloodtubes#7101)
- Always include the source URL when available
- If a diagnostic code is mentioned, include it in your answer

RESPONSE STYLE:
- Be clear and direct
- Use bullet points for lists of criteria or requirements
- Include specific percentages and diagnostic codes when they appear in the context
- If the question is about ratings, try to explain the rating criteria clearly

If you cannot find relevant information in the context, respond with:
"I don't have enough information in my knowledge base to answer that question accurately. I'd recommend consulting the official VA website at va.gov or speaking with a Veterans Service Organization (VSO) for guidance on this topic."
"""

# Shorter system prompt for simple queries
SYSTEM_PROMPT_CONCISE = """You are a VA benefits expert assistant. Answer ONLY based on the provided context. Cite sources using [source: TITLE](URL) format. If context is insufficient, say so clearly."""


def format_context_chunk(
    index: int,
    text: str,
    metadata: Dict[str, Any],
    max_text_length: int = 1500
) -> str:
    """
    Format a single context chunk for inclusion in the prompt.
    
    Args:
        index: Chunk index (1-based)
        text: The chunk text content
        metadata: Chunk metadata (topic, url, diagnostic_code, etc.)
        max_text_length: Maximum text length before truncation
        
    Returns:
        Formatted chunk string
    """
    topic = metadata.get("topic", "Unknown")
    url = metadata.get("url") or metadata.get("source_url", "")
    diagnostic_code = metadata.get("diagnostic_code", "")
    chunk_type = metadata.get("type", "")
    
    # Build header
    header_parts = [f"[{index}]"]
    if diagnostic_code:
        header_parts.append(f"DC {diagnostic_code}")
    header_parts.append(topic)
    if chunk_type:
        header_parts.append(f"({chunk_type})")
    
    header = " - ".join(header_parts[:2]) + (f" - {header_parts[2]}" if len(header_parts) > 2 else "")
    
    # Truncate text if needed
    if len(text) > max_text_length:
        text = text[:max_text_length] + "... [truncated]"
    
    # Build chunk string
    lines = [header, text]
    if url:
        lines.append(f"Source: {url}")
    
    return "\n".join(lines)


def build_context_section(
    chunks: List[Dict[str, Any]],
    max_total_length: int = 8000
) -> str:
    """
    Build the context section from retrieved chunks.
    
    Args:
        chunks: List of chunk dicts with 'text', 'metadata', 'score' keys
        max_total_length: Maximum total context length
        
    Returns:
        Formatted context section string
    """
    if not chunks:
        return "No relevant context found."
    
    context_parts = []
    total_length = 0
    
    for i, chunk in enumerate(chunks, 1):
        text = chunk.get("text", "")
        metadata = chunk.get("metadata", {})
        score = chunk.get("score", 0)
        
        # Calculate max length for this chunk based on remaining space
        remaining = max_total_length - total_length
        max_chunk_length = min(1500, remaining - 100)  # Leave room for formatting
        
        if max_chunk_length < 200:
            break  # Not enough space for more chunks
        
        formatted = format_context_chunk(i, text, metadata, max_chunk_length)
        
        # Add relevance indicator for debugging (can be removed in production)
        if score > 0:
            formatted = f"{formatted}\nRelevance: {score:.2f}"
        
        context_parts.append(formatted)
        total_length += len(formatted)
        
        if total_length >= max_total_length:
            break
    
    return "\n\n---\n\n".join(context_parts)


def build_rag_prompt(
    question: str,
    context_chunks: List[Dict[str, Any]],
    conversation_history: Optional[List[Dict[str, str]]] = None,
    use_concise: bool = False
) -> List[Dict[str, str]]:
    """
    Build the full RAG prompt with system message, context, and user question.
    
    Args:
        question: The user's question
        context_chunks: Retrieved context chunks
        conversation_history: Optional previous conversation turns
        use_concise: Use shorter system prompt
        
    Returns:
        List of message dicts for OpenAI chat completion
    """
    system_prompt = SYSTEM_PROMPT_CONCISE if use_concise else SYSTEM_PROMPT
    
    # Build context section
    context_section = build_context_section(context_chunks)
    
    # Construct the user message with context
    user_content = f"""Context:
{context_section}

---

Question: {question}

Please answer the question based on the context above. Remember to cite your sources using [source: TITLE](URL) format."""

    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Add conversation history if provided (last 2-3 turns for context)
    if conversation_history:
        # Limit to last 3 exchanges (6 messages)
        recent_history = conversation_history[-6:]
        for msg in recent_history:
            if msg.get("role") in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
    
    # Add the current question with context
    messages.append({"role": "user", "content": user_content})
    
    return messages


def build_query_expansion_prompt(question: str) -> List[Dict[str, str]]:
    """
    Build a prompt to expand/rephrase the query for better retrieval.
    
    This is optional but can help with:
    - Fixing typos
    - Expanding abbreviations
    - Adding synonyms
    
    Args:
        question: Original user question
        
    Returns:
        List of message dicts for OpenAI chat completion
    """
    system = """You are a search query optimizer for a VA benefits knowledge base. 
Your task is to rephrase the user's question to improve search results.

Rules:
1. Keep the core meaning intact
2. Expand common abbreviations (PTSD, TBI, VA, etc.)
3. Add relevant medical/VA terminology if applicable
4. Keep the rephrased query concise (under 100 words)
5. Output ONLY the rephrased query, nothing else"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Rephrase this question for better VA benefits search results:\n\n{question}"}
    ]


def extract_sources_from_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract source information from chunks for the API response.
    
    Args:
        chunks: List of retrieved chunks
        
    Returns:
        List of source dicts with id, title, url, etc.
    """
    sources = []
    seen_ids = set()
    
    for chunk in chunks:
        chunk_id = chunk.get("id", "")
        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        
        metadata = chunk.get("metadata", {})
        sources.append({
            "id": chunk_id,
            "title": metadata.get("topic", ""),
            "section": metadata.get("subtopic") or metadata.get("original_heading", ""),
            "source_url": metadata.get("url") or metadata.get("source_url", ""),
            "diagnostic_code": metadata.get("diagnostic_code"),
            "type": metadata.get("type", ""),
            "score": chunk.get("score", 0)
        })
    
    return sources
