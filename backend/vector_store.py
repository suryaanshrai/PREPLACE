import os
import re
from math import sqrt
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
            self._embedding_function = ef
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
            self._embedding_function = None

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
            # cosine distance = 1 - cosine_similarity → similarity = 1 - distance
            sim = max(0.0, 1.0 - float(distance))
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
            # cosine distance = 1 - cosine_similarity → similarity = 1 - distance
            sim = max(0.0, 1.0 - float(distance))
            scored[resume_id] = round(sim * 100, 2)
        return scored

    def text_similarity_score(self, text_a: str, text_b: str) -> float:
        if not (text_a or "").strip() or not (text_b or "").strip():
            return 0.0

        if self.enabled and self._embedding_function is not None:
            try:
                return self._chunked_similarity(text_a, text_b)
            except Exception:
                pass

        # Weighted keyword coverage fallback — reliable, cost-free, no external calls.
        return self._skill_coverage_score(text_a, text_b)

    # -- Internal helpers --------------------------------------------------

    def _skill_coverage_score(self, resume_text: str, target_text: str) -> float:
        """
        Weighted keyword coverage scorer for JD-vs-resume matching.

        Extracts meaningful terms from the target description, weights technical
        terms (stack names, tools, acronyms) 2.5x over generic words, and
        measures weighted recall against the full resume text.

        Calibration uses a power curve (coverage^0.65 * 96) that expands the
        mid-range so partial matches score proportionally:
            40% keyword match  → ~54 / 100
            60% keyword match  → ~70 / 100
            75% keyword match  → ~80 / 100
            90% keyword match  → ~89 / 100

        A role-title bonus (+4 pts) rewards resumes that explicitly state the
        target role (e.g. "Backend Developer" in a Backend Developer search).
        """
        # Generic words that carry no signal in a JD/resume match
        STOPWORDS = {
            'a','an','the','and','or','of','in','to','for','with','on','at','by',
            'from','is','are','was','were','be','been','being','have','has','had',
            'will','would','could','should','may','might','must','shall','can',
            'do','does','did','not','no','nor','so','as','if','its','it',
            'this','that','these','those','our','your','their','we','you',
            'they','he','she','i','any','all','both','each','few','more',
            'most','other','some','such','only','own','same','than','too',
            'very','into','through','during','including','across','within',
            'between','under','over','above','also','new','well','role',
            'description','responsibilities','requirements','experience',
            'knowledge','skills','skill','ability','understanding','strong',
            'solid','good','best','key','main','various','multiple','large',
            'small','high','low','help','team','teams','senior','junior',
            'build','building','work','working','develop','developing',
            'design','manage','managing','support','contribute','contributing',
            'implement','write','create','use','ensure','enable','allow',
            'participate','collaborate','maintain','monitor','integrate',
            'required','preferred','plus','advantage','expected','needed',
        }

        resume_lower = resume_text.lower()
        target_lower = target_text.lower()

        # Split on whitespace and common punctuation (keep internal . + # / -)
        raw_tokens = re.findall(r"[a-z0-9][a-z0-9_.+#/-]*", target_lower)

        total_weight  = 0.0
        matched_weight = 0.0
        seen: set[str] = set()

        for tok in raw_tokens:
            if len(tok) < 3 or tok in STOPWORDS or tok in seen:
                continue
            seen.add(tok)

            # Technical terms: contain non-alpha chars (e.g. node.js, ci/cd,
            # c++, aws) OR are 6+ character domain words (microservices,
            # kubernetes, postgresql, authentication…)
            is_tech = bool(re.search(r"[0-9_.+#/-]", tok)) or len(tok) >= 6
            weight = 2.5 if is_tech else 1.0
            total_weight += weight

            if re.search(r"\b" + re.escape(tok) + r"\b", resume_lower):
                matched_weight += weight

        if total_weight == 0:
            return 0.0

        coverage = matched_weight / total_weight  # [0.0, 1.0]

        # Power calibration: sub-linear so partial matches are not crushed
        base = min(96.0, (coverage ** 0.65) * 96.0)

        # Role-title bonus: reward resumes that name the target role directly
        role_match = re.search(r"role:\s*([^.]+)", target_lower)
        if role_match:
            role_words = role_match.group(1).strip().split()
            role_words = [w for w in role_words if w not in STOPWORDS and len(w) > 2]
            if role_words:
                hits = sum(1 for w in role_words if re.search(r"\b" + re.escape(w) + r"\b", resume_lower))
                role_bonus = (hits / len(role_words)) * 4.0
                base = min(100.0, base + role_bonus)

        return round(base, 2)

    def _cosine_from_vecs(self, emb_a, emb_b) -> float:
        """Cosine similarity in [0, 100] from two pre-computed embeddings."""
        dot = sum(x * y for x, y in zip(emb_a, emb_b))
        norm_a = sqrt(sum(x * x for x in emb_a))
        norm_b = sqrt(sum(y * y for y in emb_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        cosine = max(-1.0, min(1.0, dot / (norm_a * norm_b)))
        # Sentence-transformer cosine ∈ [0,1]; map directly to [0,100]
        return max(0.0, cosine) * 100.0

    def _chunked_similarity(self, resume_text: str, target_text: str) -> float:
        """
        all-MiniLM-L6-v2 (and most sentence-transformers) silently truncate
        input to 256 tokens (~180 words). A typical resume is 400-800 words,
        so skills and experience sections are never embedded without chunking.

        Strategy: split the resume into overlapping 150-word windows, embed
        all chunks + the target in one batched forward pass, then aggregate as
            0.65 * best_chunk_score + 0.35 * mean(top-3 chunk scores)
        to reward resumes whose best section strongly matches the target.
        """
        CHUNK_WORDS = 150   # safely under the 256-token model limit
        STRIDE      = 100   # overlap between windows

        words = resume_text.split()
        if len(words) <= CHUNK_WORDS:
            emb_a, emb_b = self._embedding_function([resume_text, target_text])
            return round(self._cosine_from_vecs(emb_a, emb_b), 2)

        chunks: list[str] = []
        i = 0
        while i < len(words):
            chunks.append(" ".join(words[i: i + CHUNK_WORDS]))
            if i + CHUNK_WORDS >= len(words):
                break
            i += STRIDE

        # Single batched call — embed all chunks and the target together
        embeddings = self._embedding_function(chunks + [target_text])
        target_emb = embeddings[-1]
        chunk_embs = embeddings[:-1]

        scores = [self._cosine_from_vecs(e, target_emb) for e in chunk_embs]
        top3   = sorted(scores, reverse=True)[:3]
        raw    = 0.65 * top3[0] + 0.35 * (sum(top3) / len(top3))
        # Calibrate: practical ceiling for MiniLM resume-vs-JD cosine is ~0.72.
        # Mapping [0, 72] → [0, 100] gives intuitive scores without distorting rank order.
        calibrated = min(100.0, raw * (100.0 / 72.0))
        return round(calibrated, 2)


vector_store = VectorStore()
