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

ANTI-HALLUCINATION RULES (CRITICAL - FOLLOW EXACTLY):
1. ONLY use information that appears EXPLICITLY in the Context section below
2. If the context does NOT contain specific information about something, DO NOT guess or infer
3. NEVER invent statistics, percentages, rating criteria, or VA procedures not in the context
4. NEVER fabricate diagnostic codes, CFR references, or legal citations
5. If a fact appears in one source, ONLY cite that specific source - do not attribute it to others
6. If you are uncertain about ANY claim, express that uncertainty explicitly
7. When the context is insufficient, clearly state: "I don't have specific information about that in my sources"

CITATION ACCURACY RULES (PREVENTS WRONG ATTRIBUTIONS):
- ONLY cite a source if the EXACT information appears in that specific source chunk
- Do NOT cite Source 1 for information that only appears in Source 3
- Each citation number must correspond to the correct source where that fact appears
- If you're unsure which source contains a fact, do not cite it
- ONLY use URLs that appear in the "Source:" line of each context chunk
- NEVER modify, combine, or invent URLs

CITATION FORMAT:
- Use superscript numbers in your answer: "The rating is 10%¹ for mild symptoms."
- At the END of your response, add a "Sources:" section
- Format each source as: ¹ [Title](URL)
- Use Unicode superscripts: ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹
- Only cite sources you actually reference
- Example:
  
  Answer text with citation¹ and more info².
  
  **Sources:**
  ¹ [Filing a VA Disability Claim](https://veteransbenefitskb.com/vaclaim)
  ² [High Blood Pressure](https://veteransbenefitskb.com/bloodtubes#7101)

RESPONSE STYLE:
- Be clear and direct
- Use bullet points for lists of criteria or requirements
- Include specific percentages and diagnostic codes ONLY when they appear in the context
- If explaining ratings, use the EXACT criteria text from the context

SPECIAL INSTRUCTIONS FOR VA MATH QUESTIONS:
- When answering questions about VA math, combined ratings, bilateral factor, or how to calculate disability percentages, ALWAYS include this helpful tool at the end of your response:
  "To calculate your combined VA disability rating, you can use this free calculator: https://www.hillandponton.com/va-disability-calculator/"
- This applies to questions like: "How do I calculate my rating?", "What is VA math?", "How does bilateral factor work?", "How do I add percentages?"

WHEN CONTEXT IS INSUFFICIENT:
If you cannot find relevant information in the context, respond with:
"I don't have enough information in my knowledge base to answer that question accurately. I'd recommend consulting the official VA website at va.gov or speaking with a Veterans Service Organization (VSO) for guidance on this topic."
"""

# Shorter system prompt for simple queries
SYSTEM_PROMPT_CONCISE = """You are a VA benefits expert assistant. Answer ONLY based on the provided context. Use superscript numbers for citations (e.g., "text¹") and list sources at the end as "**Sources:** ¹ [Title](URL)". If context is insufficient, say so clearly."""


def format_context_chunk(
    index: int,
    text: str,
    metadata: Dict[str, Any],
    max_text_length: int = 1500
) -> str:
    """
    Format a single context chunk for inclusion in the prompt.
    Uses explicit source boundaries to prevent citation confusion.
    
    Args:
        index: Chunk index (1-based)
        text: The chunk text content
        metadata: Chunk metadata (topic, url, diagnostic_code, etc.)
        max_text_length: Maximum text length before truncation
        
    Returns:
        Formatted chunk string with clear boundaries
    """
    topic = metadata.get("topic", "Unknown")
    url = metadata.get("url") or metadata.get("source_url", "")
    diagnostic_code = metadata.get("diagnostic_code", "")
    chunk_type = metadata.get("type", "")
    
    # Build descriptive header
    header_parts = []
    if diagnostic_code:
        header_parts.append(f"DC {diagnostic_code}")
    header_parts.append(topic)
    if chunk_type:
        header_parts.append(f"({chunk_type})")
    
    title = " - ".join(header_parts) if header_parts else "Unknown"
    
    # Truncate text if needed
    if len(text) > max_text_length:
        text = text[:max_text_length] + "... [truncated]"
    
    # Build chunk with EXPLICIT boundaries for better citation accuracy
    # This format helps the LLM clearly attribute information to specific sources
    lines = [
        f"[SOURCE {index}]",
        f"Title: {title}",
        f"URL: {url}" if url else "URL: Not available",
        f"Content:",
        text,
        f"[END SOURCE {index}]"
    ]
    
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
        
        # Calculate max length for this chunk based on remaining space
        remaining = max_total_length - total_length
        max_chunk_length = min(1500, remaining - 100)  # Leave room for formatting
        
        if max_chunk_length < 200:
            break  # Not enough space for more chunks
        
        formatted = format_context_chunk(i, text, metadata, max_chunk_length)
        
        context_parts.append(formatted)
        total_length += len(formatted)
        
        if total_length >= max_total_length:
            break
    
    return "\n\n".join(context_parts)


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

Please answer the question based on the context above. Use superscript numbers (¹²³) for inline citations and include a **Sources:** section at the end with numbered references like: ¹ [Title](URL)"""

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
