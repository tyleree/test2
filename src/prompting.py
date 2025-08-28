SYSTEM_PROMPT = """You are a precise documentation assistant. 
Rules:
- Answer in clean Markdown with short sections and bullet points where helpful.
- Ground every factual claim in the provided sources and include inline citations like [1], [2].
- Add a final **Sources** section mapping [n] -> Title (URL if available).
- If information is insufficient, say so and suggest what is needed.
- Do not invent sources or URLs.
"""

def build_messages(question: str, context_block: str):
    """Build messages for the chat completion"""
    user = f"""Use only the sources below to answer. Cite with [n].

SOURCES:
{context_block}

USER QUESTION:
{question}
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user}
    ]









