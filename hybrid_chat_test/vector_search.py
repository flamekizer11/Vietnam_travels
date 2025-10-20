# vector_search.py
# Pinecone vector search utilities

from typing import List, Dict, Any
import pinecone
from pinecone import Pinecone, ServerlessSpec
import config
from embed import embed_text

pc = Pinecone(api_key=config.PINECONE_API_KEY)

def create_index_if_not_exists():
    """Create Pinecone index if it doesn't exist."""
    if config.PINECONE_INDEX_NAME not in pc.list_indexes().names():
        print(f"Creating managed index: {config.PINECONE_INDEX_NAME}")
        pc.create_index(
            name=config.PINECONE_INDEX_NAME,
            dimension=config.PINECONE_VECTOR_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )

def query_pinecone(query_text: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """Query Pinecone index using embedding."""
    index = pc.Index(config.PINECONE_INDEX_NAME)
    vec = embed_text(query_text)
    res = index.query(
        vector=vec,
        top_k=top_k,
        include_metadata=True,
        include_values=False
    )
    return res.get("matches", [])

def upsert_vectors(vectors: List[Dict[str, Any]]):
    """Upsert vectors to Pinecone."""
    index = pc.Index(config.PINECONE_INDEX_NAME)
    index.upsert(vectors)