from datetime import datetime
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func

import models
from schemas import PenaltyRulesUpsert, ScoringTemplateCreate, ScoringTemplateUpdate
from security import get_current_user
from vector_store import vector_store
from .common import get_db, log_audit, to_iso, upsert_job_vector, upsert_resume_vector

router = APIRouter()


def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that enforces the caller has the 'admin' role."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _serialize_penalty_rule(rule: models.PenaltyRule) -> dict:
    return {
        "id": rule.id,
        "category": rule.category,
        "label": rule.label,
        "keywords": [k.strip() for k in (rule.keywords or "").split(",") if k.strip()],
        "penalty_value": int(rule.penalty_value or 0),
        "is_active": bool(rule.is_active),
    }


@router.get("/admin/recruiters", tags=["Admin"])
def admin_get_recruiters(admin: dict = Depends(_require_admin), db=Depends(get_db)):
    recruiters = db.query(models.UserDB).filter(models.UserDB.role == "recruiter").all()
    result = []
    for r in recruiters:
        profile = db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == r.id).first()
        listings_count = db.query(models.JobListing).filter(models.JobListing.recruiter_id == r.id).count()
        result.append(
            {
                "id": r.id,
                "name": r.name,
                "email": r.email,
                "company_name": profile.company_name if profile else "",
                "roles_hiring": profile.roles_hiring if profile else "",
                "status": profile.status if profile else "pending",
                "listings_count": listings_count,
            }
        )
    return result


@router.patch("/admin/recruiters/{user_id}/status", tags=["Admin"])
def admin_update_recruiter_status(user_id: int, status: str, admin: dict = Depends(_require_admin), db=Depends(get_db)):
    profile = db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Recruiter profile not found")
    allowed_statuses = {"pending", "approved", "rejected"}
    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(sorted(allowed_statuses))}")
    profile.status = status
    db.commit()
    log_audit(db, "admin.recruiter_status", actor_id=admin["user_id"], target_type="recruiter_profile", target_id=profile.id, detail=f"status={status}")
    return {"message": f"Recruiter status updated to {status}"}


@router.delete("/admin/recruiters/{user_id}", tags=["Admin"])
def admin_delete_recruiter(user_id: int, admin: dict = Depends(_require_admin), db=Depends(get_db)):
    listing_ids = [x.id for x in db.query(models.JobListing).filter(models.JobListing.recruiter_id == user_id).all()]
    if listing_ids:
        db.query(models.Application).filter(models.Application.job_listing_id.in_(listing_ids)).delete()
        for listing_id in listing_ids:
            vector_store.delete_job(listing_id)

    db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == user_id).delete()
    db.query(models.JobListing).filter(models.JobListing.recruiter_id == user_id).delete()
    db.query(models.UserDB).filter(models.UserDB.id == user_id).delete()
    db.commit()
    log_audit(db, "admin.recruiter_delete", actor_id=admin["user_id"], target_type="user", target_id=user_id)
    return {"message": "Recruiter deleted"}


@router.get("/admin/job-listings", tags=["Admin"])
def admin_get_all_job_listings(admin: dict = Depends(_require_admin), db=Depends(get_db)):
    listings = db.query(models.JobListing).order_by(models.JobListing.id.desc()).all()
    result = []
    for l in listings:
        recruiter = db.query(models.UserDB).filter(models.UserDB.id == l.recruiter_id).first()
        profile = (
            db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == l.recruiter_id).first()
            if recruiter
            else None
        )
        result.append(
            {
                "id": l.id,
                "role_title": l.role_title,
                "department": l.department,
                "job_type": l.job_type,
                "location": l.location,
                "ctc": l.ctc,
                "skills": l.skills,
                "description": l.description,
                "min_cgpa": l.min_cgpa,
                "min_score": l.min_score,
                "experience": l.experience,
                "status": l.status,
                "company_name": profile.company_name if profile else (recruiter.name if recruiter else "Unknown"),
                "recruiter_name": recruiter.name if recruiter else "Unknown",
            }
        )
    return result


@router.patch("/admin/job-listings/{listing_id}/status", tags=["Admin"])
def admin_update_job_status(listing_id: int, status: str, admin: dict = Depends(_require_admin), db=Depends(get_db)):
    listing = db.query(models.JobListing).filter(models.JobListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    listing.status = status
    listing.updated_at = datetime.utcnow()
    db.commit()
    upsert_job_vector(db, listing)
    log_audit(db, "admin.job_status", actor_id=admin["user_id"], target_type="job_listing", target_id=listing.id, detail=f"status={status}")
    return {"message": f"Job listing status updated to {status}"}


@router.get("/admin/stats", tags=["Admin"])
def admin_stats(admin: dict = Depends(_require_admin), db=Depends(get_db)):
    total_applicants = db.query(models.UserDB).filter(models.UserDB.role == "applicant").count()
    total_recruiters = db.query(models.UserDB).filter(models.UserDB.role == "recruiter").count()
    pending_recruiters = db.query(models.RecruiterProfile).filter(models.RecruiterProfile.status == "pending").count()
    total_resumes = db.query(models.Resume).count()
    total_listings = db.query(models.JobListing).count()
    pending_jobs = db.query(models.JobListing).filter(models.JobListing.status == "pending_approval").count()
    total_applications = db.query(models.Application).count()
    pipeline = (
        db.query(models.Application.status, func.count(models.Application.id))
        .group_by(models.Application.status)
        .all()
    )
    dept_counts = (
        db.query(models.JobListing.department, func.count(models.JobListing.id))
        .group_by(models.JobListing.department)
        .all()
    )

    return {
        "total_applicants": total_applicants,
        "total_recruiters": total_recruiters,
        "pending_recruiters": pending_recruiters,
        "total_resumes": total_resumes,
        "total_listings": total_listings,
        "pending_jobs": pending_jobs,
        "total_applications": total_applications,
        "vector_enabled": vector_store.enabled,
        "pipeline_breakdown": {status: count for status, count in pipeline},
        "department_breakdown": {dept or "Unspecified": count for dept, count in dept_counts},
    }


@router.get("/analytics/recruiter-overview", tags=["Analytics"])
def recruiter_analytics(recruiter_id: int, user: dict = Depends(get_current_user), db=Depends(get_db)):
    # Allow admins to view any recruiter's analytics, or a recruiter to view their own.
    caller_role = user.get("role")
    caller_id = user.get("user_id")
    if caller_role != "admin" and not (caller_role == "recruiter" and caller_id == recruiter_id):
        raise HTTPException(status_code=403, detail="Access denied")
    listings = db.query(models.JobListing).filter(models.JobListing.recruiter_id == recruiter_id).all()
    listing_ids = [l.id for l in listings]
    if not listing_ids:
        return {
            "total_listings": 0,
            "active_listings": 0,
            "total_applications": 0,
            "pipeline_breakdown": {},
            "applications_per_listing": [],
        }

    apps = db.query(models.Application).filter(models.Application.job_listing_id.in_(listing_ids)).all()
    breakdown = {}
    for app_row in apps:
        breakdown[app_row.status] = breakdown.get(app_row.status, 0) + 1

    per_listing = []
    for listing in listings:
        cnt = sum(1 for a in apps if a.job_listing_id == listing.id)
        per_listing.append({"job_listing_id": listing.id, "role_title": listing.role_title, "applications": cnt, "status": listing.status})
    per_listing.sort(key=lambda x: x["applications"], reverse=True)

    return {
        "total_listings": len(listings),
        "active_listings": sum(1 for l in listings if l.status == "active"),
        "total_applications": len(apps),
        "pipeline_breakdown": breakdown,
        "applications_per_listing": per_listing,
    }


@router.get("/analytics/applicant-overview", tags=["Analytics"])
def applicant_analytics(user_id: int, admin: dict = Depends(_require_admin), db=Depends(get_db)):
    apps = db.query(models.Application).filter(models.Application.applicant_id == user_id).all()
    resumes = db.query(models.Resume).filter(models.Resume.user_id == user_id).all()
    breakdown = {}
    for app_row in apps:
        breakdown[app_row.status] = breakdown.get(app_row.status, 0) + 1

    avg_score = 0
    if resumes:
        avg_score = round(sum((r.score or 0) for r in resumes) / len(resumes), 2)

    return {
        "total_resumes": len(resumes),
        "avg_resume_score": avg_score,
        "total_applications": len(apps),
        "application_breakdown": breakdown,
    }


@router.get("/admin/audit-logs", tags=["Audit"])
def get_admin_audit_logs(action: str = "", actor_id: int | None = None, limit: int = Query(100, ge=1, le=500), admin: dict = Depends(_require_admin), db=Depends(get_db)):
    query = db.query(models.AuditLog)
    if action:
        query = query.filter(models.AuditLog.action == action)
    if actor_id is not None:
        query = query.filter(models.AuditLog.actor_id == actor_id)
    logs = query.order_by(models.AuditLog.id.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "actor_id": log.actor_id,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail,
            "created_at": to_iso(log.created_at),
        }
        for log in logs
    ]


@router.get("/admin/scoring-templates", tags=["Admin"])
def admin_get_scoring_templates(admin: dict = Depends(_require_admin), db=Depends(get_db)):
    rows = db.query(models.ScoringTemplate).order_by(models.ScoringTemplate.id.desc()).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "role_title": row.role_title,
            "description": row.description,
            "category": row.category,
            "is_active": bool(row.is_active),
            "created_at": to_iso(row.created_at),
        }
        for row in rows
    ]


@router.post("/admin/scoring-templates", tags=["Admin"])
def admin_create_scoring_template(payload: ScoringTemplateCreate, admin: dict = Depends(_require_admin), db=Depends(get_db)):
    admin_id = admin["user_id"]
    row = models.ScoringTemplate(
        title=payload.title.strip(),
        role_title=payload.role_title.strip(),
        description=(payload.description or "").strip(),
        category=(payload.category or "General").strip(),
        is_active=bool(payload.is_active),
        created_by=admin_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_audit(db, "admin.template_create", actor_id=admin_id, target_type="scoring_template", target_id=row.id)
    return {"message": "Template created", "id": row.id}


@router.patch("/admin/scoring-templates/{template_id}", tags=["Admin"])
def admin_update_scoring_template(template_id: int, payload: ScoringTemplateUpdate, admin: dict = Depends(_require_admin), db=Depends(get_db)):
    admin_id = admin["user_id"]
    row = db.query(models.ScoringTemplate).filter(models.ScoringTemplate.id == template_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")

    patch = payload.model_dump(exclude_unset=True)
    for key, value in patch.items():
        setattr(row, key, value)
    row.updated_at = datetime.utcnow()
    db.commit()
    log_audit(db, "admin.template_update", actor_id=admin_id, target_type="scoring_template", target_id=row.id)
    return {"message": "Template updated"}


@router.delete("/admin/scoring-templates/{template_id}", tags=["Admin"])
def admin_delete_scoring_template(template_id: int, admin: dict = Depends(_require_admin), db=Depends(get_db)):
    admin_id = admin["user_id"]
    row = db.query(models.ScoringTemplate).filter(models.ScoringTemplate.id == template_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(row)
    db.commit()
    log_audit(db, "admin.template_delete", actor_id=admin_id, target_type="scoring_template", target_id=template_id)
    return {"message": "Template deleted"}


@router.get("/admin/penalty-defaults", tags=["Admin"])
def admin_get_penalty_defaults(admin: dict = Depends(_require_admin), db=Depends(get_db)):
    rules = (
        db.query(models.PenaltyRule)
        .filter(models.PenaltyRule.recruiter_id.is_(None), models.PenaltyRule.listing_id.is_(None))
        .order_by(models.PenaltyRule.id.asc())
        .all()
    )
    if not rules:
        return {"rules": []}
    return {"rules": [_serialize_penalty_rule(rule) for rule in rules]}


@router.post("/admin/reindex", tags=["Admin"])
def admin_reindex_vectors(admin: dict = Depends(_require_admin), db=Depends(get_db)):
    """Re-upsert all resumes and jobs into ChromaDB.

    Run this after moving the app to a new machine where chroma_db/ is empty.
    Without it, every resume falls back to the PRECISE-only scorer which is
    more generous than real cosine similarity, inflating scores toward 100.
    """
    if not vector_store.enabled:
        return {"error": "VectorStore is disabled — ChromaDB/sentence-transformers not available"}

    resumes = db.query(models.Resume).all()
    jobs = db.query(models.JobListing).all()

    for resume in resumes:
        upsert_resume_vector(db, resume)
    for job in jobs:
        upsert_job_vector(db, job)

    log_audit(db, "admin.reindex", actor_id=admin["user_id"], target_type="vector_store",
              detail=f"resumes={len(resumes)} jobs={len(jobs)}")
    return {"message": "Re-index complete", "resumes_indexed": len(resumes), "jobs_indexed": len(jobs)}


@router.put("/admin/penalty-defaults", tags=["Admin"])
def admin_upsert_penalty_defaults(payload: PenaltyRulesUpsert, admin: dict = Depends(_require_admin), db=Depends(get_db)):
    admin_id = admin["user_id"]
    db.query(models.PenaltyRule).filter(
        models.PenaltyRule.recruiter_id.is_(None),
        models.PenaltyRule.listing_id.is_(None),
    ).delete()

    for rule in payload.rules:
        row = models.PenaltyRule(
            recruiter_id=None,
            listing_id=None,
            category=rule.category.strip(),
            label=rule.label.strip(),
            keywords=",".join([k.strip().lower() for k in rule.keywords if k.strip()]),
            penalty_value=max(0, int(rule.penalty_value)),
            is_active=bool(rule.is_active),
            created_by=admin_id,
        )
        db.add(row)

    db.commit()
    log_audit(db, "admin.penalty_defaults_update", actor_id=admin_id, target_type="penalty_rules", detail=f"count={len(payload.rules)}")
    return {"message": "Penalty defaults updated", "count": len(payload.rules)}
