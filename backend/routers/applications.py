from datetime import datetime
import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

import models
from matching import compute_job_match, normalize_app_status
from schemas import ApplicationCreate, ApplicationStatusUpdate, RecruiterNoteUpdate
from utils import extract_skills_from_analysis
from vector_store import vector_store
from .common import (
    HYBRID_RULE_WEIGHT,
    HYBRID_VECTOR_WEIGHT,
    evaluate_resume_for_job_with_db,
    get_db,
    get_latest_resume,
    get_user_or_404,
    job_vector_text,
    log_audit,
    to_iso,
)

router = APIRouter()


@router.post("/applications", tags=["Applications"])
def create_or_update_application(user_id: int, payload: ApplicationCreate, db=Depends(get_db)):
    user = get_user_or_404(db, user_id)
    if user.role != "applicant":
        return {"error": "Only applicants can apply"}

    job = db.query(models.JobListing).filter(models.JobListing.id == payload.job_listing_id).first()
    if not job or job.status != "active":
        return {"error": "Job is unavailable"}

    selected_resume = None
    if payload.resume_id is not None:
        selected_resume = (
            db.query(models.Resume)
            .filter(models.Resume.id == payload.resume_id, models.Resume.user_id == user_id, models.Resume.is_deleted == False)
            .first()
        )
        if not selected_resume:
            return {"error": "Selected resume not found"}
    else:
        selected_resume = get_latest_resume(db, user_id)

    if not selected_resume:
        return {"error": "Upload at least one resume before applying"}

    new_status = normalize_app_status(payload.action)
    app_record = (
        db.query(models.Application)
        .filter(
            models.Application.applicant_id == user_id,
            models.Application.job_listing_id == payload.job_listing_id,
        )
        .first()
    )

    if not app_record:
        app_record = models.Application(
            applicant_id=user_id,
            job_listing_id=payload.job_listing_id,
            resume_id=selected_resume.id,
            status=new_status,
            recruiter_note="",
            resume_filename_snapshot=selected_resume.original_filename or selected_resume.filename or "Resume",
            resume_score_snapshot=selected_resume.score,
            resume_role_snapshot=selected_resume.suggested_role or "",
            resume_deleted=False,
        )
        db.add(app_record)
    else:
        app_record.resume_id = selected_resume.id
        app_record.status = new_status
        app_record.resume_filename_snapshot = selected_resume.original_filename or selected_resume.filename or "Resume"
        app_record.resume_score_snapshot = selected_resume.score
        app_record.resume_role_snapshot = selected_resume.suggested_role or ""
        app_record.resume_deleted = False
        app_record.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(app_record)
    log_audit(
        db,
        "application.update",
        actor_id=user_id,
        target_type="application",
        target_id=app_record.id,
        detail=f"status={app_record.status};job={payload.job_listing_id};resume={selected_resume.id}",
    )
    return {
        "message": "Application updated",
        "application_id": app_record.id,
        "status": app_record.status,
        "resume_id": app_record.resume_id,
    }


@router.get("/my-applications", tags=["Applications"])
def my_applications(user_id: int, status: str = "", q: str = "", db=Depends(get_db)):
    query = db.query(models.Application).filter(models.Application.applicant_id == user_id)
    if status:
        query = query.filter(models.Application.status == status)
    rows = query.order_by(models.Application.updated_at.desc()).all()

    out = []
    for row in rows:
        listing = db.query(models.JobListing).filter(models.JobListing.id == row.job_listing_id).first()
        if not listing:
            continue
        recruiter = db.query(models.UserDB).filter(models.UserDB.id == listing.recruiter_id).first()
        profile = (
            db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == listing.recruiter_id).first()
            if recruiter
            else None
        )

        company = profile.company_name if profile else (recruiter.name if recruiter else "Unknown")
        if q:
            ql = q.lower()
            blob = f"{listing.role_title} {company} {listing.location} {listing.department}".lower()
            if ql not in blob:
                continue

        out.append(
            {
                "id": row.id,
                "job_listing_id": row.job_listing_id,
                "status": row.status,
                "recruiter_note": row.recruiter_note,
                "updated_at": to_iso(row.updated_at),
                "resume": {
                    "id": row.resume_id,
                    "filename": row.resume_filename_snapshot,
                    "score": row.resume_score_snapshot,
                    "suggested_role": row.resume_role_snapshot,
                    "deleted": bool(row.resume_deleted),
                },
                "job": {
                    "role_title": listing.role_title,
                    "company_name": company,
                    "location": listing.location,
                    "department": listing.department,
                    "ctc": listing.ctc,
                },
            }
        )
    return out


@router.patch("/applications/{application_id}/withdraw", tags=["Applications"])
def withdraw_application(application_id: int, user_id: int, db=Depends(get_db)):
    record = (
        db.query(models.Application)
        .filter(models.Application.id == application_id, models.Application.applicant_id == user_id)
        .first()
    )
    if not record:
        return {"error": "Application not found"}
    record.status = "withdrawn"
    record.updated_at = datetime.utcnow()
    db.commit()
    log_audit(db, "application.withdraw", actor_id=user_id, target_type="application", target_id=record.id)
    return {"message": "Application withdrawn"}


@router.get("/recruiter/applications", tags=["Applications"])
def recruiter_applications(
    recruiter_id: int,
    listing_id: int | None = None,
    status: str = "",
    q: str = "",
    sort_by: str = Query("latest", pattern="^(latest|match|score)$"),
    db=Depends(get_db),
):
    recruiter = get_user_or_404(db, recruiter_id)
    if recruiter.role != "recruiter":
        return {"error": "Only recruiters can access this"}

    listings_query = db.query(models.JobListing).filter(models.JobListing.recruiter_id == recruiter_id)
    if listing_id:
        listings_query = listings_query.filter(models.JobListing.id == listing_id)
    listings = listings_query.all()
    listing_ids = [l.id for l in listings]

    if not listing_ids:
        return []

    app_query = db.query(models.Application).filter(models.Application.job_listing_id.in_(listing_ids))
    if status:
        app_query = app_query.filter(models.Application.status == status)
    app_rows = app_query.order_by(models.Application.updated_at.desc()).all()

    listing_map = {l.id: l for l in listings}
    out = []
    for row in app_rows:
        applicant = db.query(models.UserDB).filter(models.UserDB.id == row.applicant_id).first()
        if not applicant:
            continue
        resume = None
        if row.resume_id:
            resume = (
                db.query(models.Resume)
                .filter(models.Resume.id == row.resume_id, models.Resume.user_id == applicant.id)
                .first()
            )
        if not resume and row.resume_id is None and not row.resume_deleted:
            resume = get_latest_resume(db, applicant.id)

        listing = listing_map.get(row.job_listing_id)
        if not listing:
            continue

        rule_score = 0
        vector_score = 0.0
        hybrid = 0
        if resume:
            metrics = evaluate_resume_for_job_with_db(db, resume, listing)
            rule_score = metrics["rule_score"]
            vector_score = metrics["vector_score"]
            hybrid = metrics["match"]
            scoring_engine = metrics["scoring_engine"]
            penalty_total = metrics["penalty_total"]
        elif row.resume_score_snapshot is not None or row.resume_role_snapshot:
            rule_score = compute_job_match(
                applicant_role=row.resume_role_snapshot or "",
                applicant_skills=[],
                applicant_score=row.resume_score_snapshot or 0,
                job_role=listing.role_title,
                job_skills_str=listing.skills,
                job_min_score=listing.min_score,
                job_department=listing.department,
            )
            hybrid = int(round(HYBRID_RULE_WEIGHT * rule_score))
            scoring_engine = "fallback_hybrid"
            penalty_total = 0
        else:
            scoring_engine = "fallback_hybrid"
            penalty_total = 0

        if q:
            ql = q.lower()
            blob = f"{applicant.name} {applicant.email} {listing.role_title} {listing.department}".lower()
            if ql not in blob:
                continue

        out.append(
            {
                "id": row.id,
                "status": row.status,
                "recruiter_note": row.recruiter_note,
                "updated_at": to_iso(row.updated_at),
                "job_listing_id": listing.id,
                "job_title": listing.role_title,
                "applicant_id": applicant.id,
                "name": applicant.name,
                "email": applicant.email,
                "score": resume.score if resume else row.resume_score_snapshot,
                "analysis": resume.analysis if resume else None,
                "suggested_role": resume.suggested_role if resume else (row.resume_role_snapshot or ""),
                "resume_filename": (
                    resume.original_filename if resume and resume.original_filename else (resume.filename if resume else row.resume_filename_snapshot)
                ),
                "resume_deleted": bool(row.resume_deleted),
                "resume_download_url": f"/recruiter/applications/{row.id}/resume?recruiter_id={recruiter_id}",
                "match": hybrid,
                "rule_score": rule_score,
                "vector_score": round(vector_score, 2),
                "penalty_total": penalty_total,
                "scoring_engine": scoring_engine,
            }
        )

    if sort_by == "match":
        out.sort(key=lambda x: x["match"], reverse=True)
    elif sort_by == "score":
        out.sort(key=lambda x: (x["score"] or 0), reverse=True)
    else:
        out.sort(key=lambda x: x["updated_at"] or "", reverse=True)

    return out


@router.get("/applications/{job_id}/recommended-resume", tags=["Applications"])
def recommended_resume_for_job(job_id: int, user_id: int, db=Depends(get_db)):
    user = get_user_or_404(db, user_id)
    if user.role != "applicant":
        return {"error": "Only applicants can get recommendations"}

    job = db.query(models.JobListing).filter(models.JobListing.id == job_id).first()
    if not job or job.status != "active":
        return {"error": "Job is unavailable"}

    resumes = (
        db.query(models.Resume)
        .filter(models.Resume.user_id == user_id, models.Resume.is_deleted == False)
        .order_by(models.Resume.is_active.desc(), models.Resume.id.desc())
        .all()
    )
    if not resumes:
        return {"error": "Upload at least one resume first"}

    scored = []
    for resume in resumes:
        metrics = evaluate_resume_for_job_with_db(db, resume, job)
        scored.append(
            {
                "id": resume.id,
                "filename": resume.original_filename or resume.filename,
                "score": resume.score,
                "suggested_role": resume.suggested_role or "",
                "is_active": bool(resume.is_active),
                "rule_score": metrics["rule_score"],
                "vector_score": round(metrics["vector_score"], 2),
                "hybrid_score": metrics["match"],
                "penalty_total": metrics["penalty_total"],
                "scoring_engine": metrics["scoring_engine"],
            }
        )

    scored.sort(key=lambda x: x["hybrid_score"], reverse=True)
    best = scored[0]
    return {
        "job_id": job.id,
        "recommended_resume_id": best["id"],
        "recommended_hybrid_score": best["hybrid_score"],
        "resumes": scored,
    }


@router.patch("/applications/{application_id}/status", tags=["Applications"])
def recruiter_update_application_status(application_id: int, recruiter_id: int, payload: ApplicationStatusUpdate, db=Depends(get_db)):
    record = db.query(models.Application).filter(models.Application.id == application_id).first()
    if not record:
        return {"error": "Application not found"}

    listing = db.query(models.JobListing).filter(models.JobListing.id == record.job_listing_id).first()
    if not listing or listing.recruiter_id != recruiter_id:
        return {"error": "Not authorized"}

    allowed = {"reviewed", "shortlisted", "rejected", "applied", "saved", "withdrawn"}
    status = payload.status.strip().lower()
    if status not in allowed:
        return {"error": f"Invalid status. Allowed: {sorted(allowed)}"}

    record.status = status
    record.last_status_updated_by = recruiter_id
    record.updated_at = datetime.utcnow()
    db.commit()
    log_audit(
        db,
        "application.status_update",
        actor_id=recruiter_id,
        target_type="application",
        target_id=record.id,
        detail=f"status={status}",
    )
    return {"message": "Application status updated", "status": status}


@router.patch("/applications/{application_id}/note", tags=["Applications"])
def recruiter_update_note(application_id: int, recruiter_id: int, payload: RecruiterNoteUpdate, db=Depends(get_db)):
    record = db.query(models.Application).filter(models.Application.id == application_id).first()
    if not record:
        return {"error": "Application not found"}

    listing = db.query(models.JobListing).filter(models.JobListing.id == record.job_listing_id).first()
    if not listing or listing.recruiter_id != recruiter_id:
        return {"error": "Not authorized"}

    record.recruiter_note = (payload.recruiter_note or "").strip()[:1000]
    record.updated_at = datetime.utcnow()
    db.commit()
    log_audit(db, "application.note_update", actor_id=recruiter_id, target_type="application", target_id=record.id)
    return {"message": "Recruiter note updated"}


@router.get("/recruiter/applications/{application_id}/resume", tags=["Applications"])
def recruiter_download_application_resume(application_id: int, recruiter_id: int, db=Depends(get_db)):
    record = db.query(models.Application).filter(models.Application.id == application_id).first()
    if not record:
        return {"error": "Application not found"}

    listing = db.query(models.JobListing).filter(models.JobListing.id == record.job_listing_id).first()
    if not listing or listing.recruiter_id != recruiter_id:
        return {"error": "Not authorized"}

    if not record.resume_id:
        return {"error": "Resume file is unavailable for this application"}

    resume = (
        db.query(models.Resume)
        .filter(models.Resume.id == record.resume_id, models.Resume.user_id == record.applicant_id)
        .first()
    )
    if not resume or not resume.storage_path or not os.path.exists(resume.storage_path):
        return {"error": "Resume file not found"}

    filename = resume.original_filename or record.resume_filename_snapshot or "resume.pdf"
    return FileResponse(
        path=resume.storage_path,
        media_type=resume.mime_type or "application/pdf",
        filename=filename,
    )
