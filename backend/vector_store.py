import os
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


class VectorStore:
    def __init__(self):
        self.enabled = False
        self._job_collection = None
        self._resume_collection = None

        try:
            import chromadb
            from chromadb.utils import embedding_functions

            os.makedirs(CHROMA_PATH, exist_ok=True)
            self._client = chromadb.PersistentClient(path=CHROMA_PATH)
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
            self._job_collection = self._client.get_or_create_collection(
                name="jobs",
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._resume_collection = self._client.get_or_create_collection(
                name="resumes",
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            self.enabled = True
        except Exception:
            self.enabled = False

    def upsert_job(self, job_id: int, content: str, metadata: Dict):
        if not self.enabled:
            return
        self._job_collection.upsert(
            ids=[f"job:{job_id}"],
            documents=[content],
            metadatas=[metadata],
        )

    def upsert_resume(self, resume_id: int, content: str, metadata: Dict):
        if not self.enabled:
            return
        self._resume_collection.upsert(
            ids=[f"resume:{resume_id}"],
            documents=[content],
            metadatas=[metadata],
        )

    def delete_job(self, job_id: int):
        if not self.enabled:
            return
        self._job_collection.delete(ids=[f"job:{job_id}"])

    def delete_resume(self, resume_id: int):
        if not self.enabled:
            return
        self._resume_collection.delete(ids=[f"resume:{resume_id}"])

    def query_jobs(self, query_text: str, top_k: int = 20) -> Dict[int, float]:
        if not self.enabled or not query_text.strip():
            return {}
        result = self._job_collection.query(query_texts=[query_text], n_results=top_k)
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        scored: Dict[int, float] = {}
        for raw_id, distance in zip(ids, distances):
            if not raw_id.startswith("job:"):
                continue
            job_id = int(raw_id.split(":", 1)[1])
            sim = max(0.0, 1.0 - min(float(distance), 2.0) / 2.0)
            scored[job_id] = round(sim * 100, 2)
        return scored

    def query_resumes(self, query_text: str, top_k: int = 30) -> Dict[int, float]:
        if not self.enabled or not query_text.strip():
            return {}
        result = self._resume_collection.query(query_texts=[query_text], n_results=top_k)
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        scored: Dict[int, float] = {}
        for raw_id, distance in zip(ids, distances):
            if not raw_id.startswith("resume:"):
                continue
            resume_id = int(raw_id.split(":", 1)[1])
            sim = max(0.0, 1.0 - min(float(distance), 2.0) / 2.0)
            scored[resume_id] = round(sim * 100, 2)
        return scored


vector_store = VectorStore()
