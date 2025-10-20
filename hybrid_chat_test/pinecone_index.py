# print_pinecone_index.py
import config
from vector_search import pc
print("Indexes:", pc.list_indexes())
idx = pc.Index(config.PINECONE_INDEX_NAME)
print("Describe stats:")
print(idx.describe_index_stats())
