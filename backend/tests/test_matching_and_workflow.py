from matching import compute_job_match, normalize_app_status, sanitize_markdown
from routers.common import clamp_score, compute_penalty_from_rules
from vector_store import VectorStore
import utils


def test_compute_job_match_prefers_stronger_alignment():
    strong = compute_job_match(
        applicant_role="Backend Developer",
        applicant_skills=["python", "fastapi", "postgresql"],
        applicant_score=85,
        job_role="Backend Engineer",
        job_skills_str="python,fastapi,postgresql",
        job_min_score=70,
        job_department="Engineering",
    )
    weak = compute_job_match(
        applicant_role="UI Designer",
        applicant_skills=["figma"],
        applicant_score=50,
        job_role="Backend Engineer",
        job_skills_str="python,fastapi,postgresql",
        job_min_score=70,
        job_department="Engineering",
    )
    assert strong > weak


def test_normalize_application_action():
    assert normalize_app_status("save") == "saved"
    assert normalize_app_status("saved") == "saved"
    assert normalize_app_status("apply") == "applied"
    assert normalize_app_status("random-value") == "applied"


def test_markdown_sanitizer_trims_and_limits():
    src = "\n\n# Title\nText\n"
    out = sanitize_markdown(src)
    assert out.startswith("# Title")
    assert out.endswith("Text")


def test_clamp_score_bounds():
    assert clamp_score(-10) == 0
    assert clamp_score(42.2) == 42
    assert clamp_score(999) == 100


def test_compute_penalty_from_rules_applies_missing_only():
    rules = [
        {
            "category": "git",
            "label": "Version Control",
            "keywords": ["git", "github"],
            "penalty_value": 3,
            "is_active": True,
        },
        {
            "category": "projects",
            "label": "Projects",
            "keywords": ["project", "built"],
            "penalty_value": 4,
            "is_active": True,
        },
    ]

    info = compute_penalty_from_rules("Built APIs with FastAPI and GitHub actions", rules)
    assert info["penalty_total"] == 0
    assert len(info["found_keywords"]) == 2

    info2 = compute_penalty_from_rules("Experience summary only", rules)
    assert info2["penalty_total"] == 7
    assert len(info2["missing_keywords"]) == 2


def test_generate_resume_insights_fallback_shape(monkeypatch):
    monkeypatch.setattr(utils, "client", None)
    out = utils.generate_resume_insights(
        resume_text="Built APIs with FastAPI and PostgreSQL for student platform.",
        role_mode="targeted",
        target_role="Backend Developer",
    )
    assert out["role_mode"] == "targeted"
    assert out["target_role"] == "Backend Developer"
    assert out["source"] == "fallback"
    assert len(out["sections"]) >= 1
    assert len(out["action_plan"]) >= 1


# ── PRECISE Role-Discrimination Tests ─────────────────────────────────────────

# Representative backend-developer resume that mentions RAG/LangChain from a
# Coursera certificate (the exact scenario that caused ML Engineer to win).
BACKEND_DEV_RESUME = """
John Doe  |  john@example.com  |  +91 9876543210
github.com/johndoe  |  linkedin.com/in/johndoe

Summary
Backend Engineer with 2 years of experience building scalable REST APIs and
microservices using Python and FastAPI.

Experience
Backend Developer — Wobot AI (2023–present)
- Designed and built RESTful APIs using Python and FastAPI; deployed via Docker
  and GitHub Actions CI/CD pipelines on AWS EC2
- Managed PostgreSQL databases; implemented Redis caching for high-traffic endpoints
- Integrated MongoDB for flexible document storage; used JWT and OAuth for auth
- Built microservices architecture; improved API latency by 40%

Projects
- Student Portal API: FastAPI + PostgreSQL + Docker, deployed on GCP Cloud Run
- CI/CD pipeline using GitHub Actions, Docker, pytest with 90% test coverage

Education
B.Tech Computer Science — SMVDU (2019–2023)

Certifications
- Generative AI with LangChain and LlamaIndex — Coursera (2024)
- RAG pipelines and HuggingFace Transformers — Coursera (2024)

Skills
Python, FastAPI, Django, PostgreSQL, MongoDB, Redis, Docker, Kubernetes,
GitHub Actions, AWS, GCP, Git, pytest, REST APIs, microservices
"""

# Representative ML-engineer resume — primary work experience IS in ML
ML_ENGINEER_RESUME = """
Jane Smith  |  jane@example.com  |  +91 9876543211
github.com/janesmith  |  linkedin.com/in/janesmith

Summary
Machine Learning Engineer with 3 years of experience training and deploying
production ML models using PyTorch, TensorFlow, and scikit-learn.

Experience
ML Engineer — DataSci Corp (2022–present)
- Trained and deployed classification and regression models using PyTorch and scikit-learn
- Built RAG pipelines using LangChain and HuggingFace Transformers for a production Q&A system
- Tracked experiments with MLflow; managed model registry and reproducibility
- Applied feature engineering techniques; reduced model error by 22% through dimensionality reduction
- Deployed models on AWS SageMaker using Docker; orchestrated jobs with Airflow

Projects
- Sentiment Analysis Pipeline: PyTorch + HuggingFace Transformers + MLflow
- Anomaly Detection: scikit-learn, pandas, numpy, deployed to GCP Vertex AI

Education
M.Tech Data Science — IIT Delhi (2019–2022)

Skills
Python, PyTorch, TensorFlow, scikit-learn, LangChain, HuggingFace, MLflow,
Airflow, Pandas, NumPy, SQL, Docker, AWS SageMaker, DVC
"""

BACKEND_TEMPLATE = (
    "Role: Backend Developer. Description: Design and build scalable RESTful APIs using "
    "Python (FastAPI/Django/Flask) or Node.js (Express/NestJS). Architect microservices and "
    "distributed systems; integrate PostgreSQL and MySQL. Use Redis or MongoDB for caching. "
    "Containerise workloads with Docker; deploy via Kubernetes with CI/CD pipelines on AWS or GCP. "
    "Implement authentication and authorisation using OAuth 2.0 and JWT. "
    "Write comprehensive tests with pytest or Jest."
)

ML_TEMPLATE = (
    "Role: ML Engineer. Description: Build, train, and deploy ML and deep learning models using "
    "Python, PyTorch, TensorFlow, and scikit-learn. Design feature engineering pipelines. "
    "Work with LLMs, RAG pipelines, and embeddings using LangChain, LlamaIndex, and HuggingFace Transformers. "
    "Track experiments with MLflow; manage model registry with DVC. "
    "Maintain MLOps infrastructure using Kubeflow or Airflow."
)


def test_precise_backend_beats_ml_for_backend_resume():
    """A backend developer resume (even with Coursera RAG mention) must score
    higher against the Backend Developer template than the ML Engineer template."""
    vs = VectorStore.__new__(VectorStore)
    vs.enabled = False
    vs._embedding_function = None

    backend_score = vs._precise_score(BACKEND_DEV_RESUME, BACKEND_TEMPLATE)
    ml_score = vs._precise_score(BACKEND_DEV_RESUME, ML_TEMPLATE)
    assert backend_score > ml_score, (
        f"Expected Backend ({backend_score:.1f}) > ML Engineer ({ml_score:.1f}) "
        f"for a backend-developer resume, but ML Engineer won."
    )


def test_precise_ml_beats_backend_for_ml_resume():
    """An ML engineer resume must score higher against the ML Engineer template
    than the Backend Developer template."""
    vs = VectorStore.__new__(VectorStore)
    vs.enabled = False
    vs._embedding_function = None

    ml_score = vs._precise_score(ML_ENGINEER_RESUME, ML_TEMPLATE)
    backend_score = vs._precise_score(ML_ENGINEER_RESUME, BACKEND_TEMPLATE)
    assert ml_score > backend_score, (
        f"Expected ML Engineer ({ml_score:.1f}) > Backend ({backend_score:.1f}) "
        f"for an ML-engineer resume, but Backend Developer won."
    )


def test_is_education_only_coursera_context():
    """Keywords that appear only near 'Coursera' should be flagged as education-only."""
    vs = VectorStore.__new__(VectorStore)
    vs.enabled = False
    vs._embedding_function = None

    # "langchain" appears only right next to "coursera" — should be flagged
    resume_edu = "certifications: generative ai with langchain — coursera 2024."
    assert vs._is_education_only("langchain", resume_edu) is True

    # "fastapi" appears only in real work context (no educational marker nearby)
    padding = " " * 350  # ensure work section is >300 chars away from any edu section
    resume_work = (
        "certifications: generative ai with llm — coursera 2024." +
        padding +
        "built high-traffic apis with fastapi and postgresql."
    )
    assert vs._is_education_only("fastapi", resume_work) is False


def test_is_education_only_work_context():
    """Keywords used in work experience context must NOT be flagged as education-only."""
    vs = VectorStore.__new__(VectorStore)
    vs.enabled = False
    vs._embedding_function = None

    resume = (
        "experience: ml engineer at datacorp 2022-present. built rag pipelines using langchain "
        "and huggingface for production q&a system. tracked experiments with mlflow."
    )
    assert vs._is_education_only("langchain", resume) is False
    assert vs._is_education_only("mlflow", resume) is False


# ── compute_job_match edge cases ──────────────────────────────────────────────

def test_compute_job_match_no_skills_required():
    """A job with no required skills should not penalise any applicant."""
    score = compute_job_match(
        applicant_role="Backend Developer",
        applicant_skills=["python"],
        applicant_score=70,
        job_role="Backend Engineer",
        job_skills_str="",          # no required skills
        job_min_score=0,
        job_department="Engineering",
    )
    # Should be a non-negative, reasonable score — not inflated by a free bonus
    assert 0 <= score <= 100


def test_compute_job_match_no_applicant_skills():
    """An applicant with no skills should score lower than one with matching skills."""
    with_skills = compute_job_match(
        applicant_role="Backend Developer",
        applicant_skills=["python", "fastapi"],
        applicant_score=75,
        job_role="Backend Engineer",
        job_skills_str="python,fastapi",
        job_min_score=0,
        job_department="Engineering",
    )
    without_skills = compute_job_match(
        applicant_role="Backend Developer",
        applicant_skills=[],
        applicant_score=75,
        job_role="Backend Engineer",
        job_skills_str="python,fastapi",
        job_min_score=0,
        job_department="Engineering",
    )
    assert with_skills > without_skills


def test_compute_job_match_score_never_negative():
    """Even a completely mismatched applicant must not produce a negative match score."""
    score = compute_job_match(
        applicant_role="Graphic Designer",
        applicant_skills=["photoshop"],
        applicant_score=-10,        # invalid input — must be clamped internally
        job_role="Data Scientist",
        job_skills_str="python,tensorflow,pytorch",
        job_min_score=80,
        job_department="Data",
    )
    assert score >= 0


def test_compute_job_match_word_boundary_skills():
    """'React' must not match 'Reactive' or 'Reacting'."""
    react_score = compute_job_match(
        applicant_role="Frontend Developer",
        applicant_skills=["react"],
        applicant_score=70,
        job_role="Frontend Engineer",
        job_skills_str="react",
        job_min_score=0,
        job_department="Engineering",
    )
    reactive_score = compute_job_match(
        applicant_role="Frontend Developer",
        applicant_skills=["reactive programming"],  # does NOT contain 'react' as a word
        applicant_score=70,
        job_role="Frontend Engineer",
        job_skills_str="react",
        job_min_score=0,
        job_department="Engineering",
    )
    assert react_score > reactive_score


def test_extract_skills_from_analysis_handles_empty():
    """extract_skills_from_analysis must not crash on empty or None-like input."""
    from utils import extract_skills_from_analysis
    assert extract_skills_from_analysis("") == []
    assert extract_skills_from_analysis("No skills section here.") == []

