from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

import models
from matching import compute_job_match, sanitize_markdown
from schemas import JobListingCreate, JobListingUpdate, PenaltyRulesUpsert
from vector_store import vector_store
from utils import extract_skills_from_analysis
from .common import (
    HYBRID_RULE_WEIGHT,
    HYBRID_VECTOR_WEIGHT,
    compute_applicant_rank_score,
    ensure_recruiter_owns_listing,
    evaluate_resume_for_job_with_db,
    get_db,
    get_latest_resume,
    get_user_or_404,
    job_vector_text,
    log_audit,
    resume_vector_text,
    resolve_penalty_rules,
    to_iso,
    upsert_job_vector,
)

router = APIRouter()


def _serialize_penalty_rule(rule: models.PenaltyRule) -> dict:
    return {
        "id": rule.id,
        "category": rule.category,
        "label": rule.label,
        "keywords": [k.strip() for k in (rule.keywords or "").split(",") if k.strip()],
        "penalty_value": int(rule.penalty_value or 0),
        "is_active": bool(rule.is_active),
    }


@router.post("/job-listings", tags=["Jobs"])
def create_job_listing(recruiter_id: int, job: JobListingCreate, db=Depends(get_db)):
    recruiter = get_user_or_404(db, recruiter_id)
    if recruiter.role != "recruiter":
        return {"error": "Only recruiters can create job listings"}

    profile = db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == recruiter_id).first()
    if not profile or profile.status != "approved":
        return {"error": "Recruiter account is not approved by admin"}

    listing = models.JobListing(
        recruiter_id=recruiter_id,
        role_title=job.role_title.strip(),
        department=(job.department or "").strip(),
        job_type=(job.job_type or "Internship").strip(),
        location=(job.location or "").strip(),
        ctc=(job.ctc or "").strip(),
        description=sanitize_markdown(job.description),
        skills=(job.skills or "").strip(),
        min_cgpa=job.min_cgpa,
        min_score=job.min_score,
        experience=(job.experience or "Fresher (0 years)").strip(),
        status="pending_approval",
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)

    upsert_job_vector(db, listing)
    log_audit(db, "job.create", actor_id=recruiter_id, target_type="job_listing", target_id=listing.id, detail=f"status={listing.status}")
    return {"message": "Job listing submitted for admin approval", "id": listing.id}


@router.get("/job-listings", tags=["Jobs"])
def get_job_listings(
    recruiter_id: int,
    q: str = "",
    status: str = "",
    sort_by: str = Query("latest", pattern="^(latest|oldest|role)$"),
    db=Depends(get_db),
):
    query = db.query(models.JobListing).filter(models.JobListing.recruiter_id == recruiter_id)
    if status:
        query = query.filter(models.JobListing.status == status)
    if q:
        ql = f"%{q.lower()}%"
        query = query.filter(
            text(
                "LOWER(role_title) LIKE :q OR LOWER(department) LIKE :q OR LOWER(location) LIKE :q OR LOWER(skills) LIKE :q"
            )
        ).params(q=ql)

    if sort_by == "oldest":
        query = query.order_by(models.JobListing.id.asc())
    elif sort_by == "role":
        query = query.order_by(models.JobListing.role_title.asc())
    else:
        query = query.order_by(models.JobListing.id.desc())

    listings = query.all()
    return [
        {
            "id": l.id,
            "role_title": l.role_title,
            "department": l.department,
            "job_type": l.job_type,
            "location": l.location,
            "ctc": l.ctc,
            "description": l.description,
            "skills": l.skills,
            "min_cgpa": l.min_cgpa,
            "min_score": l.min_score,
            "experience": l.experience,
            "status": l.status,
            "created_at": to_iso(l.created_at),
        }
        for l in listings
    ]


@router.get("/recruiter/penalties", tags=["Jobs"])
def get_recruiter_penalties(recruiter_id: int, listing_id: int, db=Depends(get_db)):
    recruiter = get_user_or_404(db, recruiter_id)
    if recruiter.role != "recruiter":
        return {"error": "Only recruiters can access this"}

    listing = ensure_recruiter_owns_listing(db, recruiter_id, listing_id)
    rows = (
        db.query(models.PenaltyRule)
        .filter(models.PenaltyRule.recruiter_id == recruiter_id, models.PenaltyRule.listing_id == listing.id)
        .order_by(models.PenaltyRule.id.asc())
        .all()
    )
    return {"rules": [_serialize_penalty_rule(x) for x in rows]}


@router.put("/recruiter/penalties", tags=["Jobs"])
def upsert_recruiter_penalties(
    recruiter_id: int,
    payload: PenaltyRulesUpsert,
    listing_id: int,
    db=Depends(get_db),
):
    recruiter = get_user_or_404(db, recruiter_id)
    if recruiter.role != "recruiter":
        return {"error": "Only recruiters can access this"}

    if listing_id is not None:
        ensure_recruiter_owns_listing(db, recruiter_id, listing_id)

    query = db.query(models.PenaltyRule).filter(models.PenaltyRule.recruiter_id == recruiter_id)
    if listing_id is None:
        query = query.filter(models.PenaltyRule.listing_id.is_(None))
    else:
        query = query.filter(models.PenaltyRule.listing_id == listing_id)
    try:
        query.delete()
        for rule in payload.rules:
            db.add(
                models.PenaltyRule(
                    recruiter_id=recruiter_id,
                    listing_id=listing_id,
                    category=rule.category.strip(),
                    label=rule.label.strip(),
                    keywords=",".join([k.strip().lower() for k in rule.keywords if k.strip()]),
                    penalty_value=max(0, int(rule.penalty_value)),
                    is_active=bool(rule.is_active),
                    created_by=recruiter_id,
                )
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        return {"error": f"Failed to save rules: {exc}"}
    log_audit(
        db,
        "recruiter.penalties_update",
        actor_id=recruiter_id,
        target_type="penalty_rules",
        detail=f"listing_id={listing_id};count={len(payload.rules)}",
    )
    return {"message": "Penalty rules updated", "count": len(payload.rules)}


@router.put("/job-listings/{listing_id}", tags=["Jobs"])
def update_job_listing(listing_id: int, recruiter_id: int, payload: JobListingUpdate, db=Depends(get_db)):
    listing = ensure_recruiter_owns_listing(db, recruiter_id, listing_id)

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "description":
            setattr(listing, key, sanitize_markdown(value or ""))
        else:
            setattr(listing, key, value)

    from datetime import datetime

    listing.updated_at = datetime.utcnow()
    if listing.status in {"active", "rejected"}:
        listing.status = "pending_approval"

    db.commit()
    db.refresh(listing)
    upsert_job_vector(db, listing)
    log_audit(db, "job.update", actor_id=recruiter_id, target_type="job_listing", target_id=listing.id, detail=f"status={listing.status}")
    return {"message": "Job listing updated", "status": listing.status}


@router.delete("/job-listings/{listing_id}", tags=["Jobs"])
def delete_job_listing(listing_id: int, recruiter_id: int, db=Depends(get_db)):
    listing = ensure_recruiter_owns_listing(db, recruiter_id, listing_id)
    vector_store.delete_job(listing.id)
    db.query(models.Application).filter(models.Application.job_listing_id == listing.id).delete()
    deleted_listing_id = listing.id
    db.delete(listing)
    db.commit()
    log_audit(db, "job.delete", actor_id=recruiter_id, target_type="job_listing", target_id=deleted_listing_id)
    return {"message": "Job listing deleted"}


@router.patch("/job-listings/{listing_id}/toggle", tags=["Jobs"])
def toggle_job_listing(listing_id: int, db=Depends(get_db)):
    listing = db.query(models.JobListing).filter(models.JobListing.id == listing_id).first()
    if not listing:
        return {"error": "Listing not found"}
    if listing.status == "pending_approval":
        return {"error": "Cannot toggle a pending listing. Wait for admin approval."}

    from datetime import datetime

    listing.status = "closed" if listing.status == "active" else "active"
    listing.updated_at = datetime.utcnow()
    db.commit()
    upsert_job_vector(db, listing)
    log_audit(db, "job.toggle", actor_id=listing.recruiter_id, target_type="job_listing", target_id=listing.id, detail=f"status={listing.status}")
    return {"message": "Status updated", "status": listing.status}


@router.get("/matched-jobs", tags=["Matching"])
def get_matched_jobs(
    user_id: int,
    q: str = "",
    department: str = "",
    min_match: int = Query(0, ge=0, le=100),
    sort_by: str = Query("hybrid", pattern="^(hybrid|rule|vector)$"),
    db=Depends(get_db),
):
    latest_resume = get_latest_resume(db, user_id)
    if not latest_resume:
        return []

    applicant_role = latest_resume.suggested_role or ""
    applicant_score = latest_resume.score or 0
    applicant_analysis = latest_resume.analysis or ""
    applicant_skills = extract_skills_from_analysis(applicant_analysis)

    query = db.query(models.JobListing).filter(models.JobListing.status == "active")
    if department:
        query = query.filter(models.JobListing.department == department)
    if q:
        ql = f"%{q.lower()}%"
        query = query.filter(
            text(
                "LOWER(role_title) LIKE :q OR LOWER(description) LIKE :q OR LOWER(skills) LIKE :q OR LOWER(location) LIKE :q"
            )
        ).params(q=ql)
    listings = query.all()

    vector_scores = vector_store.query_jobs(resume_vector_text(latest_resume), top_k=max(25, len(listings) + 5))

    app_records = db.query(models.Application).filter(models.Application.applicant_id == user_id).all()
    app_map = {a.job_listing_id: a for a in app_records}

    result = []
    for l in listings:
        recruiter = db.query(models.UserDB).filter(models.UserDB.id == l.recruiter_id).first()
        profile = (
            db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == l.recruiter_id).first()
            if recruiter
            else None
        )

        rule_score = compute_job_match(
            applicant_role=applicant_role,
            applicant_skills=applicant_skills,
            applicant_score=applicant_score,
            job_role=l.role_title,
            job_skills_str=l.skills,
            job_min_score=l.min_score,
            job_department=l.department,
        )
        vector_score = float(vector_scores.get(l.id, 0.0))
        legacy_hybrid = int(round(HYBRID_RULE_WEIGHT * rule_score + HYBRID_VECTOR_WEIGHT * vector_score))
        v2_metrics = evaluate_resume_for_job_with_db(db, latest_resume, l)
        match_score = v2_metrics["match"]
        if match_score < min_match:
            continue

        app_state = app_map.get(l.id)
        result.append(
            {
                "id": l.id,
                "role_title": l.role_title,
                "department": l.department,
                "job_type": l.job_type,
                "location": l.location,
                "ctc": l.ctc,
                "description": l.description,
                "skills": l.skills,
                "min_cgpa": l.min_cgpa,
                "min_score": l.min_score,
                "experience": l.experience,
                "company_name": profile.company_name if profile else (recruiter.name if recruiter else "Unknown"),
                "match": match_score,
                "rule_score": v2_metrics["rule_score"],
                "vector_score": round(v2_metrics["vector_score"], 2),
                "penalty_total": v2_metrics["penalty_total"],
                "scoring_engine": v2_metrics["scoring_engine"],
                "fallback_reason": v2_metrics["fallback_reason"],
                "legacy_hybrid": legacy_hybrid,
                "application_status": app_state.status if app_state else None,
            }
        )

    key_map = {
        "hybrid": lambda x: x["match"],
        "rule": lambda x: x["rule_score"],
        "vector": lambda x: x["vector_score"],
    }
    result.sort(key=key_map.get(sort_by, key_map["hybrid"]), reverse=True)
    return result


@router.get("/job-listings/{listing_id}", tags=["Jobs"])
def get_job_listing_detail(listing_id: int, user_id: int, db=Depends(get_db)):
    user = get_user_or_404(db, user_id)
    listing = db.query(models.JobListing).filter(models.JobListing.id == listing_id).first()
    if not listing:
        return {"error": "Listing not found"}

    if user.role == "applicant" and listing.status != "active":
        return {"error": "Job is unavailable"}

    recruiter = db.query(models.UserDB).filter(models.UserDB.id == listing.recruiter_id).first()
    profile = (
        db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == listing.recruiter_id).first()
        if recruiter
        else None
    )
    app = None
    if user.role == "applicant":
        app = (
            db.query(models.Application)
            .filter(models.Application.applicant_id == user_id, models.Application.job_listing_id == listing.id)
            .first()
        )

    return {
        "id": listing.id,
        "role_title": listing.role_title,
        "department": listing.department,
        "job_type": listing.job_type,
        "location": listing.location,
        "ctc": listing.ctc,
        "description": listing.description,
        "skills": listing.skills,
        "min_cgpa": listing.min_cgpa,
        "min_score": listing.min_score,
        "experience": listing.experience,
        "status": listing.status,
        "company_name": profile.company_name if profile else (recruiter.name if recruiter else "Unknown"),
        "application_status": app.status if app else None,
        "created_at": to_iso(listing.created_at),
        "updated_at": to_iso(listing.updated_at),
    }


@router.get("/job-listings/{listing_id}/matched-candidates", tags=["Matching"])
def matched_candidates_for_listing(
    listing_id: int,
    recruiter_id: int,
    q: str = "",
    status: str = "",
    db=Depends(get_db),
):
    listing = ensure_recruiter_owns_listing(db, recruiter_id, listing_id)

    applicants = db.query(models.UserDB).filter(models.UserDB.role == "applicant").all()
    vector_scores = vector_store.query_resumes(job_vector_text(listing), top_k=max(30, len(applicants) + 5))

    app_records = db.query(models.Application).filter(models.Application.job_listing_id == listing_id).all()
    app_map = {a.applicant_id: a for a in app_records}

    result = []
    for user in applicants:
        latest_resume = get_latest_resume(db, user.id)
        if not latest_resume:
            continue

        applicant_skills = extract_skills_from_analysis(latest_resume.analysis or "")
        metrics = evaluate_resume_for_job_with_db(db, latest_resume, listing)
        hybrid = metrics["match"]

        app_state = app_map.get(user.id)
        app_status = app_state.status if app_state else "not_applied"
        if status and app_status != status:
            continue

        if q:
            ql = q.lower()
            if ql not in user.name.lower() and ql not in user.email.lower() and ql not in (latest_resume.suggested_role or "").lower():
                continue

        result.append(
            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "score": latest_resume.score,
                "analysis": latest_resume.analysis,
                "suggested_role": latest_resume.suggested_role or "",
                "rule_score": metrics["rule_score"],
                "vector_score": round(metrics["vector_score"], 2),
                "penalty_total": metrics["penalty_total"],
                "scoring_engine": metrics["scoring_engine"],
                "match": hybrid,
                "application_id": app_state.id if app_state else None,
                "application_status": app_status,
                "recruiter_note": app_state.recruiter_note if app_state else "",
            }
        )

    result.sort(key=lambda x: x["match"], reverse=True)
    return result


@router.get("/applicants", tags=["Applicants"])
def get_all_applicants(
    q: str = "",
    min_score: int = Query(0, ge=0, le=100),
    sort_by: str = Query("rank", pattern="^(rank|score|latest)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    users = db.query(models.UserDB).filter(models.UserDB.role == "applicant").all()
    result = []
    for user in users:
        resume = get_latest_resume(db, user.id)
        app_analysis = resume.analysis if resume else ""
        app_role = resume.suggested_role if resume else ""
        app_score = resume.score if resume else 0
        app_skills = extract_skills_from_analysis(app_analysis)
        rank_score = compute_applicant_rank_score(app_score, app_role, app_skills)

        if app_score < min_score:
            continue
        if q:
            ql = q.lower()
            blob = f"{user.name} {user.email} {app_role}".lower()
            if ql not in blob:
                continue

        result.append(
            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "score": app_score if resume else None,
                "analysis": app_analysis if resume else None,
                "suggested_role": app_role or "",
                "rank_score": rank_score,
            }
        )

    if sort_by == "score":
        result.sort(key=lambda x: (x["score"] or 0), reverse=True)
    elif sort_by == "latest":
        result.sort(key=lambda x: x["id"], reverse=True)
    else:
        result.sort(key=lambda x: x["rank_score"], reverse=True)

    return result[offset: offset + limit]
