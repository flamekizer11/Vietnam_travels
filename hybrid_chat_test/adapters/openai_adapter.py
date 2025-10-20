# adapters/openai_adapter.py
# OpenAI API adapter for compatibility

from openai import OpenAI
import config

def create_client():
    """Create OpenAI client with error handling."""
    try:
        return OpenAI(api_key=config.OPENAI_API_KEY)
    except Exception as e:
        raise RuntimeError(f"Failed to create OpenAI client: {e}")

def embed_texts(client, texts, model="text-embedding-3-small"):
    """Embed texts with retry."""
    try:
        resp = client.embeddings.create(model=model, input=texts)
        return [data.embedding for data in resp.data]
    except Exception as e:
        raise RuntimeError(f"Embedding failed: {e}")

def chat_completion(client, messages, model="gpt-4o-mini", **kwargs):
    """Chat completion with retry."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        return resp.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"Chat completion failed: {e}")