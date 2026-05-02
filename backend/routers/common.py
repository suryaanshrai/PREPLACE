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
    rows = []

    # Tier 1: listing-specific recruiter rules.
    if recruiter_id is not None and listing_id is not None:
        rows = (
            db.query(models.PenaltyRule)
            .filter(models.PenaltyRule.recruiter_id == recruiter_id, models.PenaltyRule.listing_id == listing_id)
            .order_by(models.PenaltyRule.id.asc())
            .all()
        )
        if rows:
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

    # Tier 2: recruiter defaults (listing_id = null).
    if recruiter_id is not None:
        rows = (
            db.query(models.PenaltyRule)
            .filter(models.PenaltyRule.recruiter_id == recruiter_id, models.PenaltyRule.listing_id.is_(None))
            .order_by(models.PenaltyRule.id.asc())
            .all()
        )
        if rows:
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

    # Tier 3: admin global defaults.
    rows = (
        db.query(models.PenaltyRule)
        .filter(models.PenaltyRule.recruiter_id.is_(None), models.PenaltyRule.listing_id.is_(None))
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
    boost_total = 0

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
            # Found keyword boosts score by the same value it would have penalised.
            boost_total += penalty_value
            found.append({"category": category, "label": label, "boost": penalty_value})
        else:
            penalty_total += penalty_value
            missing.append({"category": category, "label": label, "penalty": penalty_value})

    return {
        "penalty_total": penalty_total,
        "boost_total": min(boost_total, 20),
        "missing_keywords": missing,
        "found_keywords": found,
    }


def compute_structural_bonus(resume_text: str) -> dict:
    """
    Detect structural quality signals in a resume and return a bonus score (max 15).
    Structural completeness is a resume quality dimension independent of role fit.
    """
    text = resume_text or ""
    lower = text.lower()
    signals: list[str] = []
    bonus = 0

    # Contact information
    if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', text):
        bonus += 2
        signals.append("email_present")
    if re.search(r'(\+\d[\d\s\-]{7,}|\b\d{10}\b|\b\d{3}[\s\-]\d{3}[\s\-]\d{4}\b)', text):
        bonus += 1
        signals.append("phone_present")

    # Professional links
    if re.search(r'linkedin\.com', lower):
        bonus += 1
        signals.append("linkedin_link")
    if re.search(r'github\.com', lower):
        bonus += 1
        signals.append("github_link")

    # Resume sections
    if re.search(r'\b(summary|objective|profile|about me|professional summary)\b', lower):
        bonus += 2
        signals.append("summary_section")
    if re.search(r'\b(experience|work history|employment)\b', lower):
        bonus += 2
        signals.append("experience_section")
    if re.search(r'\b(education|degree|bachelor|master|b\.tech|m\.tech|university|college)\b', lower):
        bonus += 2
        signals.append("education_section")
    if re.search(r'\b(project|projects|portfolio)\b', lower):
        bonus += 1
        signals.append("projects_section")
    if re.search(r'\b(skills|technologies|tech stack|tools|frameworks)\b', lower):
        bonus += 1
        signals.append("skills_section")

    # Quality signals
    if re.search(r'\b\d+\s*%|\b(reduced|improved|increased|optimized)\b', lower):
        bonus += 2
        signals.append("quantified_achievements")
    if re.search(r'\b(certification|certified|certificate|coursera|udemy|edx)\b', lower):
        bonus += 1
        signals.append("certifications")

    return {
        "structural_bonus": min(bonus, 15),
        "structural_signals": signals,
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

    # When Chroma is unavailable, vector_score from the index is 0.
    # Fall back to PRECISE text similarity so scores are not capped by the
    # hybrid formula (max 0.45 × rule_score = 45).
    used_precise_fallback = False
    if vector_score == 0:
        job_target = (
            f"Role: {job.role_title or ''}. "
            f"Skills: {job.skills or ''}. "
            f"Description: {job.description or ''}"
        )
        vector_score = float(vector_store.text_similarity_score(resume_text, job_target))
        used_precise_fallback = True

    boost_total = int(penalty["boost_total"])
    structural = compute_structural_bonus(resume_text)
    structural_bonus = structural["structural_bonus"]

    if vector_score > 0:
        # Blend JD-text similarity with deterministic rule scoring to reduce
        # inflated matches caused by generic overlap in resume/JD text.
        blended = (0.55 * vector_score) + (0.45 * rule_score)
        # Bonuses can only fill remaining headroom to 100; they cannot push a
        # mediocre score over the line by themselves.
        headroom = max(0.0, 100.0 - blended)
        bonus_applied = min(float(boost_total + structural_bonus), headroom)
        raw_match = blended + bonus_applied - penalty_total
        # When ChromaDB is not indexed (PRECISE fallback), cap at 90 — scores
        # above 90 require real embedding similarity to be meaningful. Run
        # POST /admin/reindex to populate ChromaDB and unlock full scoring.
        score_ceiling = 90 if used_precise_fallback else 100
        match = max(0, min(score_ceiling, int(round(raw_match))))
        engine = "precise_fallback_v3" if used_precise_fallback else "vector_rule_penalty_v3"
        fallback_reason = "chroma_not_indexed" if used_precise_fallback else None
    else:
        headroom = max(0.0, 100.0 - fallback_hybrid)
        bonus_applied = min(float(structural_bonus), headroom)
        match = clamp_score(fallback_hybrid + bonus_applied)
        engine = "fallback_hybrid"
        fallback_reason = "no_vector_score"

    return {
        "rule_score": rule_score,
        "vector_score": vector_score,
        "hybrid": fallback_hybrid,
        "match": match,
        "penalty_total": penalty_total,
        "boost_total": boost_total,
        "structural_bonus": structural_bonus,
        "structural_signals": structural["structural_signals"],
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
    boost_total = int(penalty["boost_total"])

    structural = compute_structural_bonus(resume_text)
    structural_bonus = structural["structural_bonus"]

    if target_text.strip() and vector_score > 0:
        final_score = clamp_score(vector_score + boost_total + structural_bonus - penalty_total)
        engine = "vector_penalty_v2"
        fallback_reason = None
    else:
        final_score = clamp_score((resume.score or 0) + structural_bonus)
        engine = "fallback_hybrid"
        fallback_reason = "no_target_or_zero_similarity"

    breakdown = {
        "vector_score": round(vector_score, 2),
        "penalty_total": penalty_total,
        "boost_total": boost_total,
        "structural_bonus": structural_bonus,
        "structural_signals": structural["structural_signals"],
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
