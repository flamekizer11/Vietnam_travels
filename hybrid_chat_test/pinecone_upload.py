# pinecone_upload.py
import json
import time
from tqdm import tqdm
from embed import embed_texts
from vector_search import create_index_if_not_exists, upsert_vectors
import config

# -----------------------------
# Config
# -----------------------------
DATA_FILE = "vietnam_travel_dataset.json"
BATCH_SIZE = 32

# -----------------------------
# Main upload
# -----------------------------
def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        nodes = json.load(f)

    items = []
    for node in nodes:
        semantic_text = node.get("semantic_text") or (node.get("description") or "")[:1000]
        if not semantic_text.strip():
            continue
        meta = {
            "id": node.get("id"),
            "type": node.get("type"),
            "name": node.get("name"),
            "city": node.get("city", node.get("region", "")),
            "tags": node.get("tags", [])
        }
        items.append((node["id"], semantic_text, meta))

    print(f"Preparing to upsert {len(items)} items to Pinecone...")

    # Create index if needed
    create_index_if_not_exists()

    for batch in tqdm(list(chunked(items, BATCH_SIZE)), desc="Uploading batches"):
        ids = [item[0] for item in batch]
        texts = [item[1] for item in batch]
        metas = [item[2] for item in batch]

        embeddings = embed_texts(texts, model="text-embedding-3-small", use_cache=True)

        vectors = [
            {"id": _id, "values": emb, "metadata": meta}
            for _id, emb, meta in zip(ids, embeddings, metas)
        ]

        upsert_vectors(vectors)
        time.sleep(0.2)

    print("All items uploaded successfully.")

def chunked(iterable, n):
    for i in range(0, len(iterable), n):
        yield iterable[i:i+n]

# -----------------------------
if __name__ == "__main__":
    main()
