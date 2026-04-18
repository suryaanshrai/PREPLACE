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
            app_skills_lower = [s.lower() for s in applicant_skills]
            matched = sum(1 for js in job_skills if any(js in as_ or as_ in js for as_ in app_skills_lower))
            skill_score = (matched / len(job_skills)) * 35
    else:
        skill_score = 15
    match_score += skill_score

    min_sc = job_min_score or 0
    score_val = applicant_score or 0
    if min_sc > 0:
        if score_val >= min_sc:
            ratio = min(score_val / min_sc, 1.5)
            score_fit = 25 * min(ratio / 1.5, 1.0)
        else:
            score_fit = 25 * (score_val / min_sc) * 0.5
    else:
        score_fit = (score_val / 100) * 25
    match_score += score_fit

    return min(max(int(round(match_score)), 0), 100)
