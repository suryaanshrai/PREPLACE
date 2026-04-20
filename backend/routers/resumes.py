from datetime import datetime
import hashlib
import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, UploadFile

logger = logging.getLogger(__name__)

import models
from utils import analyze_resume, compute_final_score, extract_text_from_pdf
from vector_store import vector_store
from .common import (
    MAX_UPLOAD_MB,
    UPLOAD_DIR,
    build_scoring_target,
    extract_role,
    get_db,
    get_resume_text_for_scoring,
    get_user_or_404,
    log_audit,
    score_resume_against_target,
    score_from_analysis,
    to_iso,
    upsert_resume_vector,
)

router = APIRouter()


@router.post("/upload-resume", tags=["Resumes"])
def upload_resume(user_id: int, file: UploadFile = File(...), db=Depends(get_db)):
    user = get_user_or_404(db, user_id)
    if user.role != "applicant":
        return {"error": "Only applicants can upload resumes"}

    filename = file.filename or "resume.pdf"
    if not filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are supported"}

    file_bytes = file.file.read()
    if not file_bytes:
        return {"error": "Uploaded file is empty"}

    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        return {"error": f"File too large. Max {MAX_UPLOAD_MB} MB"}

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing_resume = (
        db.query(models.Resume)
        .filter(models.Resume.user_id == user_id, models.Resume.file_hash == file_hash)
        .first()
    )

    if existing_resume:
        cached_gemini = score_from_analysis(existing_resume.analysis or "", existing_resume.score or 0)
        try:
            tmp_path = os.path.join(UPLOAD_DIR, f"tmp_{uuid.uuid4()}_{filename}")
            with open(tmp_path, "wb") as out:
                out.write(file_bytes)
            resume_text = extract_text_from_pdf(tmp_path)
            os.remove(tmp_path)
        except Exception:
            resume_text = existing_resume.analysis or ""

        penalty_info = compute_final_score(cached_gemini, resume_text)
        final_score = penalty_info["final_score"]

        db.query(models.Resume).filter(models.Resume.user_id == user_id).update({"is_active": False})
        existing_resume.is_active = True
        existing_resume.is_deleted = False
        existing_resume.deleted_at = None
        existing_resume.score = final_score
        existing_resume.updated_at = datetime.utcnow()
        db.commit()
        log_audit(db, "resume.activate_cached", actor_id=user_id, target_type="resume", target_id=existing_resume.id)

        return {
            "message": "Using cached result",
            "resume_id": existing_resume.id,
            "score": final_score,
            "analysis": existing_resume.analysis,
            "suggested_role": existing_resume.suggested_role or "",
            "gemini_score": cached_gemini,
            "penalty": penalty_info["penalty"],
            "final_score": final_score,
            "missing_keywords": penalty_info["missing_keywords"],
            "found_keywords": penalty_info["found_keywords"],
        }

    unique_filename = f"{uuid.uuid4()}_{filename}"
    file_location = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_location, "wb") as out:
        out.write(file_bytes)

    try:
        resume_text = extract_text_from_pdf(file_location)
    except Exception:
        os.remove(file_location)
        return {"error": "Unable to parse this PDF. Please upload a text-based PDF."}

    analysis = analyze_resume(resume_text)
    gemini_score = score_from_analysis(analysis, 0)
    penalty_info = compute_final_score(gemini_score, resume_text)
    final_score = penalty_info["final_score"]
    suggested_role = extract_role(analysis)

    db.query(models.Resume).filter(models.Resume.user_id == user_id).update({"is_active": False})
    resume = models.Resume(
        filename=unique_filename,
        original_filename=filename,
        file_hash=file_hash,
        user_id=user_id,
        score=final_score,
        analysis=analysis,
        parsed_text=resume_text,
        suggested_role=suggested_role,
        is_active=True,
        mime_type=file.content_type or "application/pdf",
        file_size=len(file_bytes),
        storage_path=file_location,
        scoring_engine="legacy",
        scoring_version="v1",
        score_breakdown_json=json.dumps(
            {
                "gemini_score": penalty_info["gemini_score"],
                "penalty": penalty_info["penalty"],
                "final_score": final_score,
            }
        ),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    upsert_resume_vector(db, resume)
    log_audit(db, "resume.upload", actor_id=user_id, target_type="resume", target_id=resume.id, detail=f"file={filename}")

    return {
        "message": "Resume uploaded",
        "resume_id": resume.id,
        "score": final_score,
        "analysis": analysis,
        "suggested_role": suggested_role,
        "gemini_score": penalty_info["gemini_score"],
        "penalty": penalty_info["penalty"],
        "final_score": final_score,
        "missing_keywords": penalty_info["missing_keywords"],
        "found_keywords": penalty_info["found_keywords"],
    }


@router.get("/scoring/templates", tags=["Resumes"])
def get_scoring_templates(db=Depends(get_db)):
    rows = (
        db.query(models.ScoringTemplate)
        .filter(models.ScoringTemplate.is_active == True)
        .order_by(models.ScoringTemplate.category.asc(), models.ScoringTemplate.id.asc())
        .all()
    )
    return [
        {
            "id": t.id,
            "title": t.title,
            "role_title": t.role_title,
            "description": t.description,
            "category": t.category,
        }
        for t in rows
    ]


@router.post("/upload-resume-v2", tags=["Resumes"])
def upload_resume_v2(
    user_id: int,
    template_id: int | None = None,
    role_title: str = "",
    job_description: str = "",
    recruiter_id: int | None = None,
    listing_id: int | None = None,
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    user = get_user_or_404(db, user_id)
    if user.role != "applicant":
        return {"error": "Only applicants can upload resumes"}

    filename = file.filename or "resume.pdf"
    if not filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are supported"}

    file_bytes = file.file.read()
    if not file_bytes:
        return {"error": "Uploaded file is empty"}

    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        return {"error": f"File too large. Max {MAX_UPLOAD_MB} MB"}

    unique_filename = f"{uuid.uuid4()}_{filename}"
    file_location = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_location, "wb") as out:
        out.write(file_bytes)

    try:
        resume_text = extract_text_from_pdf(file_location)
    except Exception:
        os.remove(file_location)
        return {"error": "Unable to parse this PDF. Please upload a text-based PDF."}

    if not resume_text.strip():
        os.remove(file_location)
        return {"error": "No text could be extracted from this PDF. Please upload a text-based (non-scanned) PDF."}

    template = None
    if template_id is not None:
        template = db.query(models.ScoringTemplate).filter(models.ScoringTemplate.id == template_id).first()
        if not template:
            return {"error": "Template not found"}

    target_role = (role_title or (template.role_title if template else "") or "").strip()
    target_description = (job_description or (template.description if template else "") or "").strip()
    target_text = build_scoring_target(target_role, target_description)

    analysis = f"V2 deterministic scoring target role: {target_role or 'General Role'}"
    score = 0
    breakdown = {
        "vector_score": 0.0,
        "penalty_total": 0,
        "missing_keywords": [],
        "found_keywords": [],
        "final_score": 0,
        "scoring_engine": "fallback_hybrid",
        "scoring_version": "v2",
        "fallback_reason": "missing_target",
    }

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing_resume = (
        db.query(models.Resume)
        .filter(models.Resume.user_id == user_id, models.Resume.file_hash == file_hash)
        .first()
    )

    if existing_resume:
        # Re-score the cached text against the new target and reactivate
        existing_text = existing_resume.parsed_text or resume_text
        if target_text.strip():
            temp_resume = models.Resume(parsed_text=existing_text, analysis=analysis, score=0, suggested_role=target_role)
            breakdown = score_resume_against_target(
                db, temp_resume, target_text=target_text,
                recruiter_id=recruiter_id, listing_id=listing_id,
            )
            score = breakdown["final_score"]

        db.query(models.Resume).filter(models.Resume.user_id == user_id).update({"is_active": False})
        existing_resume.is_active = True
        existing_resume.is_deleted = False
        existing_resume.deleted_at = None
        existing_resume.score = score
        existing_resume.analysis = analysis
        existing_resume.suggested_role = target_role
        existing_resume.scoring_engine = breakdown["scoring_engine"]
        existing_resume.scoring_version = "v2"
        existing_resume.score_breakdown_json = json.dumps(breakdown)
        existing_resume.updated_at = datetime.utcnow()
        os.remove(file_location)  # new copy not needed
        db.commit()
        db.refresh(existing_resume)
        upsert_resume_vector(db, existing_resume)
        log_audit(db, "resume.upload_v2_cached", actor_id=user_id, target_type="resume", target_id=existing_resume.id,
                  detail=f"template_id={template_id};engine={breakdown['scoring_engine']}")
        logger.info("upload_v2 cached user=%s template=%s engine=%s vector=%.2f final=%s",
                    user_id, template_id, breakdown["scoring_engine"], breakdown["vector_score"], score)
        return {
            "message": "Using cached resume, re-scored with new target",
            "resume_id": existing_resume.id,
            "score": score,
            "final_score": score,
            "analysis": analysis,
            "suggested_role": target_role,
            "vector_score": breakdown["vector_score"],
            "penalty_total": breakdown["penalty_total"],
            "missing_keywords": breakdown["missing_keywords"],
            "found_keywords": breakdown["found_keywords"],
            "scoring_engine": breakdown["scoring_engine"],
            "scoring_version": "v2",
            "fallback_reason": breakdown.get("fallback_reason"),
            "template_id": template_id,
            "template_title": template.title if template else None,
        }

    if target_text.strip():
        temp_resume = models.Resume(parsed_text=resume_text, analysis=analysis, score=0, suggested_role=target_role)
        breakdown = score_resume_against_target(
            db,
            temp_resume,
            target_text=target_text,
            recruiter_id=recruiter_id,
            listing_id=listing_id,
        )
        score = breakdown["final_score"]

    db.query(models.Resume).filter(models.Resume.user_id == user_id).update({"is_active": False})
    resume = models.Resume(
        filename=unique_filename,
        original_filename=filename,
        file_hash=file_hash,
        user_id=user_id,
        score=score,
        analysis=analysis,
        parsed_text=resume_text,
        suggested_role=target_role,
        is_active=True,
        mime_type=file.content_type or "application/pdf",
        file_size=len(file_bytes),
        storage_path=file_location,
        scoring_engine=breakdown["scoring_engine"],
        scoring_version="v2",
        score_breakdown_json=json.dumps(breakdown),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    upsert_resume_vector(db, resume)
    log_audit(
        db,
        "resume.upload_v2",
        actor_id=user_id,
        target_type="resume",
        target_id=resume.id,
        detail=f"template_id={template_id};engine={breakdown['scoring_engine']}",
    )
    logger.info(
        "upload_v2 user=%s template=%s engine=%s vector=%.2f penalty=%s final=%s fallback=%s",
        user_id, template_id, breakdown["scoring_engine"],
        breakdown["vector_score"], breakdown["penalty_total"],
        breakdown["final_score"], breakdown.get("fallback_reason"),
    )

    return {
        "message": "Resume uploaded and scored with V2",
        "resume_id": resume.id,
        "score": score,
        "final_score": score,
        "analysis": analysis,
        "suggested_role": target_role,
        "vector_score": breakdown["vector_score"],
        "penalty_total": breakdown["penalty_total"],
        "missing_keywords": breakdown["missing_keywords"],
        "found_keywords": breakdown["found_keywords"],
        "scoring_engine": breakdown["scoring_engine"],
        "scoring_version": "v2",
        "fallback_reason": breakdown.get("fallback_reason"),
        "template_id": template_id,
        "template_title": template.title if template else None,
    }


@router.get("/my-resumes", tags=["Resumes"])
def get_my_resumes(user_id: int, db=Depends(get_db)):
    resumes = (
        db.query(models.Resume)
        .filter(models.Resume.user_id == user_id, models.Resume.is_deleted == False)
        .order_by(models.Resume.is_active.desc(), models.Resume.id.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "filename": r.original_filename,
            "score": r.score,
            "analysis": r.analysis,
            "suggested_role": r.suggested_role or "",
            "is_active": bool(r.is_active),
            "file_size": r.file_size or 0,
            "created_at": to_iso(r.created_at),
        }
        for r in resumes
    ]


@router.patch("/my-resumes/{resume_id}/activate", tags=["Resumes"])
def activate_resume(resume_id: int, user_id: int, db=Depends(get_db)):
    resume = (
        db.query(models.Resume)
        .filter(models.Resume.id == resume_id, models.Resume.user_id == user_id, models.Resume.is_deleted == False)
        .first()
    )
    if not resume:
        return {"error": "Resume not found"}
    db.query(models.Resume).filter(models.Resume.user_id == user_id, models.Resume.is_deleted == False).update({"is_active": False})
    resume.is_active = True
    resume.updated_at = datetime.utcnow()
    db.commit()
    log_audit(db, "resume.activate", actor_id=user_id, target_type="resume", target_id=resume.id)
    return {"message": "Active resume updated"}


@router.delete("/my-resumes/{resume_id}", tags=["Resumes"])
def delete_resume(resume_id: int, user_id: int, db=Depends(get_db)):
    resume = (
        db.query(models.Resume)
        .filter(models.Resume.id == resume_id, models.Resume.user_id == user_id, models.Resume.is_deleted == False)
        .first()
    )
    if not resume:
        return {"error": "Resume not found"}

    was_active = bool(resume.is_active)

    # Keep file and DB record for recruiter access on linked applications.
    resume.is_deleted = True
    resume.deleted_at = datetime.utcnow()
    resume.is_active = False
    resume.updated_at = datetime.utcnow()
    vector_store.delete_resume(resume.id)

    linked_apps = (
        db.query(models.Application)
        .filter(models.Application.applicant_id == user_id, models.Application.resume_id == resume.id)
        .all()
    )
    for app in linked_apps:
        if not app.resume_filename_snapshot:
            app.resume_filename_snapshot = resume.original_filename or resume.filename or "Resume"
        if app.resume_score_snapshot is None:
            app.resume_score_snapshot = resume.score
        if not app.resume_role_snapshot:
            app.resume_role_snapshot = resume.suggested_role or ""
        app.resume_deleted = True
        app.updated_at = datetime.utcnow()

    deleted_resume_id = resume.id
    db.commit()

    if was_active:
        latest = (
            db.query(models.Resume)
            .filter(models.Resume.user_id == user_id, models.Resume.is_deleted == False)
            .order_by(models.Resume.id.desc())
            .first()
        )
        if latest:
            latest.is_active = True
            db.commit()

    log_audit(db, "resume.delete", actor_id=user_id, target_type="resume", target_id=deleted_resume_id)
    return {"message": "Resume deleted", "applications_preserved": len(linked_apps)}
