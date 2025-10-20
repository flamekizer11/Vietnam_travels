# adapters/pinecone_adapter.py
# Pinecone API adapter for compatibility

from pinecone import Pinecone, ServerlessSpec
import config

def create_client():
    """Create Pinecone client."""
    try:
        return Pinecone(api_key=config.PINECONE_API_KEY)
    except Exception as e:
        raise RuntimeError(f"Failed to create Pinecone client: {e}")

def list_indexes(client):
    """List indexes with compatibility."""
    try:
        return client.list_indexes().names()
    except AttributeError:
        # Fallback for older API
        return client.list_indexes()

def create_index(client, name, dimension, metric="cosine", spec=None):
    """Create index."""
    try:
        client.create_index(name=name, dimension=dimension, metric=metric, spec=spec)
    except Exception as e:
        raise RuntimeError(f"Index creation failed: {e}")

def query_index(index, **kwargs):
    """Query index with compatibility."""
    try:
        return index.query(**kwargs)
    except Exception as e:
        raise RuntimeError(f"Query failed: {e}")

def upsert_index(index, vectors):
    """Upsert vectors."""
    try:
        return index.upsert(vectors)
    except Exception as e:
        raise RuntimeError(f"Upsert failed: {e}")