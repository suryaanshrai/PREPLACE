import logging
import os
import re
from math import sqrt
from typing import Dict, List

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

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
            logger.info("VectorStore: ChromaDB + sentence-transformers loaded successfully (model=%s)", EMBED_MODEL)
            print(f"[VectorStore] Semantic embeddings ENABLED — model={EMBED_MODEL}")
        except Exception:
            self.enabled = False
            self._embedding_function = None
            logger.exception(
                "VectorStore: ChromaDB failed to initialize — falling back to PRECISE scorer only. "
                "Scores will be based on keyword/taxonomy matching rather than semantic embeddings."
            )
            print("[VectorStore] Semantic embeddings DISABLED — PRECISE-only fallback active. Check logs for details.")

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
                embed_score = self._chunked_similarity(text_a, text_b)
                precise_score = self._precise_score(text_a, text_b)
                # Blend: embeddings capture semantic proximity; PRECISE adds
                # skill-taxonomy discriminability for sparse JD descriptions.
                blended = 0.65 * embed_score + 0.35 * precise_score
                return round(min(100.0, blended), 2)
            except Exception:
                pass

        # PRECISE engine fallback — reliable, cost-free, no external calls.
        return self._precise_score(text_a, text_b)

    # -- Internal helpers --------------------------------------------------

    def _precise_score(self, resume_text: str, target_text: str) -> float:
        """
        PRECISE v3 — profile-role scoring with stronger discrimination.

        Dimensions:
            A. Skill group coverage (JD-specific, dominant weight)
            B. Experience quality (resume quality, capped)
            C. Role alignment (title overlap)
        """
        resume_lower = resume_text.lower()
        target_lower = target_text.lower()

        # Extract role upfront — used for sparse-JD inference and role alignment.
        # Use IGNORECASE so "Role:" and "role:" both match regardless of how
        # job_vector_text() constructs the string.
        _role_m = re.search(r"role:\s*([^.]+)", target_lower, re.IGNORECASE)
        role_raw = _role_m.group(1).strip() if _role_m else ""

        # ── A. Skill Group Coverage ──────────────────────────────────────────
        TAXONOMY: dict[str, tuple[float, frozenset]] = {
            "prog_lang":    (0.15, frozenset({"python","java","javascript","typescript","golang","rust","kotlin","swift","c#","ruby","php","scala","bash","perl"})),
            "web_backend":  (0.12, frozenset({"django","fastapi","flask","express","spring","rails","laravel","nestjs","fastify","gin","fiber","actix","hapi","koa","node.js","nodejs"})),
            "web_frontend": (0.06, frozenset({"react","vue","angular","svelte","nextjs","nuxt","ember","backbone","jquery","gatsby","remix"})),
            "db_sql":       (0.08, frozenset({"postgresql","mysql","sqlite","mariadb","mssql","oracle","postgres"})),
            "db_nosql":     (0.06, frozenset({"mongodb","redis","cassandra","dynamodb","elasticsearch","couchdb","firestore","neo4j"})),
            "cloud":        (0.07, frozenset({"aws","gcp","azure","s3","ec2","lambda","cloudrun","firebase","heroku","digitalocean","vercel","netlify"})),
            "devops":       (0.10, frozenset({"docker","kubernetes","terraform","ansible","jenkins","helm","ci/cd","cicd","github-actions"})),
            "api_arch":     (0.08, frozenset({"graphql","grpc","microservices","websocket","kafka","rabbitmq","celery"})),
            "security":     (0.04, frozenset({"authentication","authorization","oauth","jwt","ssl","tls","encryption","owasp","rbac","saml"})),
            "testing":      (0.05, frozenset({"pytest","jest","unittest","mocha","jasmine","cypress","selenium","tdd","bdd","coverage"})),
            "ai_ml":        (0.04, frozenset({"pytorch","tensorflow","scikit-learn","llm","rag","langchain","mlops","transformers","embeddings","huggingface","keras"})),
            "vcs":          (0.04, frozenset({"git","github","gitlab","bitbucket"})),
            "mobile":       (0.04, frozenset({"react-native","flutter","android","ios","xcode","gradle"})),
            "data":         (0.07, frozenset({"pandas","numpy","spark","hadoop","airflow","dbt","tableau","powerbi","looker","etl"})),
        }

        relevant_weight = 0.0
        matched_weight  = 0.0

        for _group, (weight, members) in TAXONOMY.items():
            jd_hits = {m for m in members
                       if re.search(r"\b" + re.escape(m) + r"\b", target_lower)}
            if not jd_hits:
                continue
            relevant_weight += weight
            resume_hits = {m for m in jd_hits
                           if re.search(r"\b" + re.escape(m) + r"\b", resume_lower)}
            if resume_hits:
                # Soft synonym coverage: cap denominator at 3 so that having
                # 1-of-5 equivalent frameworks (e.g. fastapi from
                # fastapi/django/flask/express/nestjs) earns 33% credit rather
                # than 20%. This prevents narrow JDs from scoring higher than
                # broad ones for the same skill hit.
                effective_denom = min(len(jd_hits), 3)
                group_weight = weight * min(1.0, len(resume_hits) / effective_denom)

                # Education-context penalty (ai_ml only): when ALL matched ai_ml
                # keywords appear exclusively near educational context words
                # (coursera, certificate, course, etc.), reduce credit to 35%.
                # This prevents a Coursera LangChain certificate from making the
                # resume look like an ML Engineer's primary profile.
                if _group == "ai_ml" and all(
                    self._is_education_only(kw, resume_lower) for kw in resume_hits
                ):
                    group_weight *= 0.35

                matched_weight += group_weight

        if relevant_weight > 0:
            skill_score = (matched_weight / relevant_weight) * 100.0
        elif role_raw:
            # Sparse JD: infer expected skill groups from the role title so
            # PRECISE stays discriminative even when the description has no keywords.
            skill_score = self._infer_skill_score(role_raw, resume_lower, TAXONOMY)
        else:
            skill_score = 50.0

        # ── B. Experience Quality Signal ─────────────────────────────────────
        EXP_SIGNALS: list[tuple[str, float]] = [
            (r"\b\d+\s*%",                                                              6.0),
            (r"\b(backend|front.end|full.stack|software|data)\s+(engineer|developer|architect)\b", 5.0),
            (r"\b(microservices?|distributed|scalable|high.performance)\b",             4.0),
            (r"\b\d{1,3}[,\s]?\d{3}\b|\b\d+\s*k\b|\bmillion\b|\bthousand\b",         4.0),
            (r"\b(reduc|improv|increas|optimiz|decreas)\w*\b",                          3.0),
            (r"\b(production|deployed|live|prod)\b",                                    3.0),
            (r"\b(led|managed|mentored|coordinated)\b",                                 3.0),
            (r"\b(concurren|parallel|async|asynchronous)\w*\b",                        3.0),
            (r"\b(b\.?tech|bachelor|master|phd|m\.?tech)\b",                          3.0),
            (r"\b(projects?|capstone|hackathon)\b",                                     3.0),
            (r"\b(designed|architected|built|engineered|developed|implemented|created)\b", 2.0),
            (r"\b(code.reviews?|pull.requests?|code.quality)\b",                       2.0),
            (r"\b(certification|certified|certificate|coursera|udemy|edx)\b",           2.0),
            (r"\b(open.source|github)\b",                                               2.0),
            (r"\b(leetcode|hackerrank|codechef|competitive)\b",                         2.0),
            (r"\b(intern|internship)\b",                                                2.0),
            (r"\b(rag|llm|langchain|machine.learning|deep.learning)\b",                 2.0),
        ]

        exp_raw = sum(pts for pattern, pts in EXP_SIGNALS
                      if re.search(pattern, resume_lower))
        # Cap experience contribution so role-agnostic quality signals do not
        # dominate JD-specific skill fit.
        exp_score = min(70.0, (exp_raw / 20.0) * 100.0)

        # ── C. Role Alignment ────────────────────────────────────────────────
        if role_raw:
            ROLE_STOP = {"and","or","the","a","an","of","in","to","for","with",
                         "entry","senior","junior","lead","staff","principal","mid"}
            role_words = [w for w in re.findall(r"[a-z]+", role_raw)
                          if w not in ROLE_STOP and len(w) > 2]
            if role_words:
                hits = sum(1 for w in role_words
                           if re.search(r"\b" + re.escape(w) + r"\b", resume_lower))
                role_score = (hits / len(role_words)) * 100.0
            else:
                role_score = 50.0
        else:
            role_score = 50.0

        # ── Combine and calibrate ────────────────────────────────────────────
        # Skill fit stays dominant for role discrimination.
        # Cap at 90 (not 100) so the PRECISE-only fallback path (no ChromaDB)
        # stays within real cosine similarity range and leaves headroom for
        # structural/boost bonuses without inflating scores to 100.
        raw = 0.75 * skill_score + 0.12 * exp_score + 0.13 * role_score
        calibrated = min(90.0, raw * 1.05)
        return round(calibrated, 2)

    def _infer_skill_score(self, role_raw: str, resume_lower: str, taxonomy: dict) -> float:
        """
        Infer relevant skill groups from the role title and score the resume
        against those groups when the JD contains no explicit skill keywords.
        """
        ROLE_SKILL_INFERENCE: dict[str, frozenset] = {
            "backend":          frozenset({"prog_lang", "web_backend", "db_sql", "db_nosql", "devops", "api_arch", "vcs"}),
            "frontend":         frozenset({"web_frontend", "prog_lang", "vcs"}),
            "fullstack":        frozenset({"prog_lang", "web_backend", "web_frontend", "db_sql", "devops", "vcs"}),
            "full stack":       frozenset({"prog_lang", "web_backend", "web_frontend", "db_sql", "devops", "vcs"}),
            "data analyst":     frozenset({"data", "prog_lang", "db_sql"}),
            "data scientist":   frozenset({"ai_ml", "data", "prog_lang"}),
            "ml engineer":      frozenset({"ai_ml", "prog_lang", "data"}),
            "machine learning": frozenset({"ai_ml", "prog_lang", "data"}),
            "devops":           frozenset({"devops", "cloud", "vcs"}),
            "sre":              frozenset({"devops", "cloud", "vcs"}),
            "security":         frozenset({"security", "prog_lang"}),
            "mobile":           frozenset({"mobile", "prog_lang"}),
            "android":          frozenset({"mobile", "prog_lang"}),
            "ios":              frozenset({"mobile", "prog_lang"}),
        }

        inferred_groups: set[str] = set()
        role_lower = role_raw.lower()
        for role_key, groups in ROLE_SKILL_INFERENCE.items():
            if role_key in role_lower:
                inferred_groups |= groups

        if not inferred_groups:
            return 50.0  # No inference possible — neutral default

        inferred_relevant = 0.0
        inferred_matched = 0.0
        for group_name in inferred_groups:
            if group_name not in taxonomy:
                continue
            weight, members = taxonomy[group_name]
            inferred_relevant += weight
            resume_hits = {m for m in members
                           if re.search(r"\b" + re.escape(m) + r"\b", resume_lower)}
            if resume_hits:
                # Soft coverage: having 2+ skills from a group earns full weight.
                coverage = min(1.0, len(resume_hits) / 2)
                inferred_matched += weight * coverage

        if inferred_relevant == 0:
            return 50.0
        return (inferred_matched / inferred_relevant) * 100.0

    def _is_education_only(self, keyword: str, resume_lower: str) -> bool:
        """
        Return True if every occurrence of `keyword` in the resume appears
        within 300 characters of an educational context word (coursera, udemy,
        edx, certificate, certification, course, degree, hackathon, intern).
        Used to detect ML keywords that come from certifications rather than
        primary work experience.
        """
        EDU_MARKERS = (
            "coursera", "udemy", "edx", "certificate", "certification",
            "course", "degree", "hackathon", "intern",
        )
        WINDOW = 300
        pattern = re.compile(r"\b" + re.escape(keyword) + r"\b")
        occurrences = [m.start() for m in pattern.finditer(resume_lower)]
        if not occurrences:
            return True  # No occurrence → treat as education-only (no real-world evidence)
        for pos in occurrences:
            ctx = resume_lower[max(0, pos - WINDOW): pos + len(keyword) + WINDOW]
            if not any(marker in ctx for marker in EDU_MARKERS):
                # This occurrence is NOT near any educational marker → real-world use
                return False
        return True

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
        # Calibrate: practical ceiling for MiniLM resume-vs-JD cosine is ~0.52.
        # Mapping [0, 52] → [0, 100] gives more useful scores for role-specific JDs.
        calibrated = min(100.0, raw * (100.0 / 52.0))
        return round(calibrated, 2)


vector_store = VectorStore()
