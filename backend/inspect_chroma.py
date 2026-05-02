"""Quick script to inspect the top 3 entries in each ChromaDB collection."""

import os
import chromadb

CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db")

client = chromadb.PersistentClient(path=CHROMA_PATH)

for col_name in ["jobs", "resumes"]:
    try:
        col = client.get_collection(col_name)
    except Exception as e:
        print(f"[{col_name}] Collection not found: {e}\n")
        continue

    total = col.count()
    print(f"=== Collection: '{col_name}' ({total} total entries) ===")

    if total == 0:
        print("  (empty)\n")
        continue

    result = col.get(limit=3, include=["metadatas", "embeddings", "documents"])

    ids = result["ids"]
    metadatas = result["metadatas"]
    embeddings = result["embeddings"]
    documents = result["documents"]

    for i, doc_id in enumerate(ids):
        print(f"\n  --- Entry {i + 1} ---")
        print(f"  ID       : {doc_id}")
        print(f"  Metadata : {metadatas[i]}")
        print(f"  Document : {documents[i][:200]}{'...' if len(documents[i]) > 200 else ''}")
        vec = embeddings[i]
        print(f"  Vector   : dim={len(vec)}, first 8 values={[round(v, 6) for v in vec[:8]]}")
    print()
