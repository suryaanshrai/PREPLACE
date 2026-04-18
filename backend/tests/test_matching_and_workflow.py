from matching import compute_job_match, normalize_app_status, sanitize_markdown


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
