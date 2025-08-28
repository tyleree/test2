from typing import List, Dict, Tuple
from src import llm, pinecone_io, config
import tiktoken

def retrieve_top_chunks(question: str, k: int = None, score_threshold: float = None):
    """Retrieve top chunks from Pinecone based on question embedding"""
    vec = llm.embed_text(question)
    res = pinecone_io.query(vec, top_k=k or config.TOP_K)
    scored = []
    
    for m in res.matches:
        score = m.score or 0.0
        if score_threshold is None or score >= score_threshold:
            scored.append({
                "text": m.metadata.get("text", ""),
                "title": m.metadata.get("title") or m.metadata.get("source_title") or "Untitled",
                "url": m.metadata.get("url"),
                "section": m.metadata.get("section"),
                "score": score,
                "doc_id": m.metadata.get("doc_id")
            })
    
    return scored

def cheap_distill(question: str, snippet: str) -> str:
    """Optional pre-summarization to save tokens"""
    sys = {
        "role": "system",
        "content": "Extract only the lines strictly relevant to answering the user question. Keep quotes verbatim. Return 2-4 sentences max."
    }
    usr = {
        "role": "user",
        "content": f"Question:\n{question}\n\nSnippet:\n{snippet}"
    }
    return llm.chat([sys, usr], model=config.GEN_MODEL, max_tokens=160)

ENC = tiktoken.get_encoding("cl100k_base")

def token_len(s: str) -> int:
    """Count tokens in a string"""
    return len(ENC.encode(s or ""))

def pack_context(question: str, chunks: List[Dict], max_ctx_tokens: int) -> Tuple[List[Dict], str]:
    """Optionally distill then pack into a numbered source list under token budget"""
    packed = []
    ctx_lines = []
    total = 0
    i = 1
    
    for ch in chunks:
        distilled = cheap_distill(question, ch["text"])
        block = f"[{i}] {ch['title'] or 'Untitled'}\n{distilled}\n"
        t = token_len(block)
        
        if total + t > max_ctx_tokens:
            break
        
        ctx_lines.append(block)
        ch["number"] = i
        packed.append(ch)
        total += t
        i += 1
    
    return packed, "\n".join(ctx_lines)









