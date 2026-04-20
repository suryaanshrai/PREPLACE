from matching import compute_job_match, normalize_app_status, sanitize_markdown
from routers.common import clamp_score, compute_penalty_from_rules


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
