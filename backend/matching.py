import re


def sanitize_markdown(md: str) -> str:
    if not md:
        return ""
    clean = md.replace("\r\n", "\n").strip()
    return clean[:12000]


def normalize_app_status(action: str) -> str:
    action = (action or "").strip().lower()
    if action in {"save", "saved"}:
        return "saved"
    if action in {"apply", "applied"}:
        return "applied"
    return "applied"


def _skill_match(job_skill: str, app_skills: list) -> bool:
    """Return True if the job skill appears as a whole word in any applicant skill."""
    pattern = re.compile(r"\b" + re.escape(job_skill) + r"\b", re.IGNORECASE)
    return any(pattern.search(s) for s in app_skills)


def compute_job_match(
    applicant_role: str,
    applicant_skills: list,
    applicant_score: int,
    job_role: str,
    job_skills_str: str,
    job_min_score: int,
    job_department: str,
) -> int:
    match_score = 0.0

    role_score = 0.0
    if applicant_role and job_role:
        app_words = set(applicant_role.lower().split())
        job_words = set(job_role.lower().split())
        filler = {"intern", "senior", "junior", "lead", "associate", "the", "a", "an", "for"}
        app_clean = app_words - filler
        job_clean = job_words - filler
        if app_clean and job_clean:
            overlap = len(app_clean & job_clean)
            total = len(app_clean | job_clean)
            role_score = (overlap / total) * 40

        dept_lower = (job_department or "").lower()
        role_lower = applicant_role.lower()
        if ("engineer" in role_lower or "developer" in role_lower or "sde" in role_lower) and "engineering" in dept_lower:
            role_score = min(role_score + 10, 40)
        if ("data" in role_lower or "ml" in role_lower or "analyst" in role_lower) and "data" in dept_lower:
            role_score = min(role_score + 10, 40)
        if ("product" in role_lower or "manager" in role_lower) and "product" in dept_lower:
            role_score = min(role_score + 10, 40)
        if ("design" in role_lower or "ui" in role_lower or "ux" in role_lower) and "design" in dept_lower:
            role_score = min(role_score + 10, 40)
    match_score += role_score

    skill_score = 0.0
    if job_skills_str:
        job_skills = [s.strip().lower() for s in job_skills_str.split(",") if s.strip()]
        if job_skills and applicant_skills:
            # Use word-boundary matching to avoid "React" matching "Reactive", etc.
            matched = sum(1 for js in job_skills if _skill_match(js, applicant_skills))
            skill_score = (matched / len(job_skills)) * 35
        # If job has skills listed but applicant has none, skill_score stays 0.
    # If job lists no required skills: neutral — award 0 rather than an
    # arbitrary free boost (previously 15 was given, inflating all scores).
    match_score += skill_score

    min_sc = job_min_score or 0
    score_val = applicant_score or 0
    if min_sc > 0:
        # Linear interpolation: full 25 pts when score_val >= min_sc,
        # scaled down proportionally below.  No discontinuity at the boundary.
        ratio = min(score_val / min_sc, 1.0)
        score_fit = 25 * ratio
    else:
        score_fit = (score_val / 100) * 25
    match_score += score_fit

    return min(max(int(round(match_score)), 0), 100)
