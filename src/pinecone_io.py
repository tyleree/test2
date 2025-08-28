from pinecone import Pinecone
from src import config

pc = Pinecone(api_key=config.PINECONE_API_KEY)
index = pc.Index(config.PINECONE_INDEX)

def upsert_vectors(items):
    """Upsert vectors to Pinecone index"""
    # items: list of dicts {id, values, metadata}
    index.upsert(items=items)

def query(vector, top_k, metadata_filter=None):
    """Query vectors from Pinecone index"""
    return index.query(
        vector=vector, 
        top_k=top_k, 
        include_metadata=True, 
        filter=metadata_filter or {}
    )









