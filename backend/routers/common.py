from datetime import datetime
import json
import os
import re

from fastapi import HTTPException

from database import SessionLocal
import models
from matching import compute_job_match
from utils import extract_skills_from_analysis
from vector_store import vector_store

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
HYBRID_VECTOR_WEIGHT = float(os.getenv("HYBRID_VECTOR_WEIGHT", "0.55"))
HYBRID_RULE_WEIGHT = max(0.0, 1.0 - HYBRID_VECTOR_WEIGHT)


def clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def to_iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def extract_role(analysis_text: str) -> str:
    if not analysis_text:
        return ""
    match = re.search(r"Suggested Role:\\s*(.+)", analysis_text, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip(".")[:80]
    match = re.search(r"Role:\\s*(.+)", analysis_text, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip(".")[:80]
    return ""


def get_user_or_404(db, user_id: int):
    user = db.query(models.UserDB).filter(models.UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_latest_resume(db, user_id: int):
    return (
        db.query(models.Resume)
        .filter(models.Resume.user_id == user_id, models.Resume.is_deleted == False)
        .order_by(models.Resume.is_active.desc(), models.Resume.id.desc())
        .first()
    )


def score_from_analysis(analysis: str, fallback: int = 0) -> int:
    try:
        return int(analysis.split("Score:")[1].split("\n")[0].strip())
    except Exception:
        return fallback


def compute_applicant_rank_score(applicant_score: int, applicant_role: str, applicant_skills: list) -> float:
    rank = 0.0
    rank += (applicant_score or 0) * 0.5
    skill_count = min(len(applicant_skills), 15)
    rank += (skill_count / 15) * 30
    if applicant_role:
        role_words = len(applicant_role.split())
        rank += min(role_words / 3, 1.0) * 20
    return round(rank, 1)


def job_vector_text(job: models.JobListing) -> str:
    return (
        f"Role: {job.role_title}. Department: {job.department}. "
        f"Type: {job.job_type}. Location: {job.location}. "
        f"Skills: {job.skills}. Experience: {job.experience}. "
        f"Description: {job.description}"
    )


def resume_vector_text(resume: models.Resume) -> str:
    # Use actual parsed content so job-matching embeddings reflect real resume text.
    # Prefix with role to anchor the embedding; truncation (if any) will drop
    # the tail rather than the role signal.
    role_prefix = f"Role: {resume.suggested_role or 'Unknown'}. "
    content = (resume.parsed_text or resume.analysis or "").strip()
    return role_prefix + content


def get_resume_text_for_scoring(resume: models.Resume) -> str:
    # Prefer parsed PDF text for deterministic scoring, fallback to analysis blob.
    return (resume.parsed_text or "").strip() or (resume.analysis or "")


def resolve_penalty_rules(db, recruiter_id: int | None = None, listing_id: int | None = None) -> list[dict]:
    if listing_id is None:
        return []
    rows = (
        db.query(models.PenaltyRule)
        .filter(models.PenaltyRule.recruiter_id == recruiter_id, models.PenaltyRule.listing_id == listing_id)
        .order_by(models.PenaltyRule.id.asc())
        .all()
    )
    return [
        {
            "category": r.category,
            "label": r.label,
            "keywords": [k.strip().lower() for k in (r.keywords or "").split(",") if k.strip()],
            "penalty_value": int(r.penalty_value or 0),
            "is_active": bool(r.is_active),
        }
        for r in rows
    ]


def compute_penalty_from_rules(resume_text: str, rules: list[dict]) -> dict:
    lower_text = (resume_text or "").lower()
    missing = []
    found = []
    penalty_total = 0

    for rule in rules:
        if not rule.get("is_active", True):
            continue
        keywords = [k.strip().lower() for k in (rule.get("keywords") or []) if str(k).strip()]
        if not keywords:
            continue
        has_match = any(k in lower_text for k in keywords)
        label = rule.get("label") or str(rule.get("category", "")).replace("_", " ").title()
        category = rule.get("category") or "custom"
        penalty_value = int(rule.get("penalty_value", 0) or 0)

        if has_match:
            found.append({"category": category, "label": label})
        else:
            penalty_total += penalty_value
            missing.append({"category": category, "label": label, "penalty": penalty_value})

    return {
        "penalty_total": penalty_total,
        "missing_keywords": missing,
        "found_keywords": found,
    }


def build_scoring_target(role_title: str = "", description: str = "") -> str:
    return f"Role: {role_title or ''}. Description: {description or ''}".strip()


def upsert_job_vector(db, job: models.JobListing) -> None:
    vector_store.upsert_job(
        job.id,
        job_vector_text(job),
        {
            "job_id": job.id,
            "recruiter_id": job.recruiter_id,
            "status": job.status,
            "department": job.department or "",
        },
    )
    job.indexed_at = datetime.utcnow()
    db.commit()


def upsert_resume_vector(db, resume: models.Resume) -> None:
    vector_store.upsert_resume(
        resume.id,
        resume_vector_text(resume),
        {
            "resume_id": resume.id,
            "user_id": resume.user_id,
            "score": resume.score or 0,
            "role": resume.suggested_role or "",
        },
    )
    resume.indexed_at = datetime.utcnow()
    db.commit()


def evaluate_resume_for_job(resume: models.Resume, job: models.JobListing) -> dict:
    skills = extract_skills_from_analysis(resume.analysis or "")
    rule_score = compute_job_match(
        applicant_role=resume.suggested_role or "",
        applicant_skills=skills,
        applicant_score=resume.score or 0,
        job_role=job.role_title,
        job_skills_str=job.skills,
        job_min_score=job.min_score,
        job_department=job.department,
    )
    vector_score = float(vector_store.query_resumes(job_vector_text(job), top_k=50).get(resume.id, 0.0))
    hybrid = int(round(HYBRID_RULE_WEIGHT * rule_score + HYBRID_VECTOR_WEIGHT * vector_score))
    return {
        "rule_score": rule_score,
        "vector_score": vector_score,
        "hybrid": hybrid,
    }


def evaluate_resume_for_job_with_db(db, resume: models.Resume, job: models.JobListing) -> dict:
    skills = extract_skills_from_analysis(resume.analysis or "")
    rule_score = compute_job_match(
        applicant_role=resume.suggested_role or "",
        applicant_skills=skills,
        applicant_score=resume.score or 0,
        job_role=job.role_title,
        job_skills_str=job.skills,
        job_min_score=job.min_score,
        job_department=job.department,
    )
    vector_score = float(vector_store.query_resumes(job_vector_text(job), top_k=50).get(resume.id, 0.0))
    fallback_hybrid = int(round(HYBRID_RULE_WEIGHT * rule_score + HYBRID_VECTOR_WEIGHT * vector_score))

    rules = resolve_penalty_rules(db, recruiter_id=job.recruiter_id, listing_id=job.id)
    resume_text = get_resume_text_for_scoring(resume)
    penalty = compute_penalty_from_rules(resume_text, rules)
    penalty_total = int(penalty["penalty_total"])

    if vector_score > 0:
        match = clamp_score(vector_score - penalty_total)
        engine = "vector_penalty_v2"
        fallback_reason = None
    else:
        match = fallback_hybrid
        engine = "fallback_hybrid"
        fallback_reason = "no_vector_score"

    return {
        "rule_score": rule_score,
        "vector_score": vector_score,
        "hybrid": fallback_hybrid,
        "match": match,
        "penalty_total": penalty_total,
        "missing_keywords": penalty["missing_keywords"],
        "found_keywords": penalty["found_keywords"],
        "scoring_engine": engine,
        "fallback_reason": fallback_reason,
    }


def score_resume_against_target(db, resume: models.Resume, target_text: str, recruiter_id: int | None = None, listing_id: int | None = None) -> dict:
    resume_text = get_resume_text_for_scoring(resume)
    vector_score = float(vector_store.text_similarity_score(resume_text, target_text))
    rules = resolve_penalty_rules(db, recruiter_id=recruiter_id, listing_id=listing_id)
    penalty = compute_penalty_from_rules(resume_text, rules)
    penalty_total = int(penalty["penalty_total"])

    if target_text.strip() and vector_score > 0:
        final_score = clamp_score(vector_score - penalty_total)
        engine = "vector_penalty_v2"
        fallback_reason = None
    else:
        final_score = resume.score or 0
        engine = "fallback_hybrid"
        fallback_reason = "no_target_or_zero_similarity"

    breakdown = {
        "vector_score": round(vector_score, 2),
        "penalty_total": penalty_total,
        "missing_keywords": penalty["missing_keywords"],
        "found_keywords": penalty["found_keywords"],
        "final_score": final_score,
        "scoring_engine": engine,
        "scoring_version": "v2",
        "fallback_reason": fallback_reason,
    }
    return breakdown


def ensure_recruiter_owns_listing(db, recruiter_id: int, listing_id: int):
    listing = db.query(models.JobListing).filter(models.JobListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.recruiter_id != recruiter_id:
        raise HTTPException(status_code=403, detail="Not authorized for this listing")
    return listing


def log_audit(db, action: str, actor_id: int | None = None, target_type: str = "", target_id: int | None = None, detail: str = ""):
    entry = models.AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail[:1500] if detail else "",
    )
    db.add(entry)
    db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
