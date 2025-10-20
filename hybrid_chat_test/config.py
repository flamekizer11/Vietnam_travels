# config.py 
import os

# Neo4j connection (use a secure secret store or env vars in production)
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "<REPLACE_ME>")

# API keys should come from environment variables or a secrets manager.
# Do NOT store secrets in source control.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "<REPLACE_ME>")

# Pinecone configuration — keep keys out of source control and set via env vars.
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "<REPLACE_ME>")
PINECONE_ENV = os.environ.get("PINECONE_ENV", "us-east-1")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "vietnam-travel")
PINECONE_VECTOR_DIM = int(os.environ.get("PINECONE_VECTOR_DIM", "1536"))

# Optional tuning for Neo4j async driver
# Increase this if you plan to run many concurrent fetches
NEO4J_MAX_CONN_POOL_SIZE = 50

# Enable the background async runner by default (set to False to opt out)
ENABLE_ASYNC_RUNNER = True

# Embedding cache settings
# Optional Redis URL for async embedding cache (set to empty to disable)
EMBEDDING_REDIS_URL = "" 
# TTL for embeddings cached in Redis (seconds)
EMBEDDING_CACHE_TTL_SECONDS = 86400 #1 day
