from openai import OpenAI
from src import config

client = OpenAI(api_key=config.OPENAI_API_KEY)

def embed_text(text: str) -> list:
    """Generate embeddings for text"""
    emb = client.embeddings.create(model=config.EMBED_MODEL, input=text)
    return emb.data[0].embedding

def chat(messages, model=None, max_tokens=None, temperature=0):
    """Generate chat completion"""
    return client.chat.completions.create(
        model=model or config.FINAL_GEN_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens or config.MAX_OUTPUT_TOKENS
    ).choices[0].message.content









