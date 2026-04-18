from contextlib import asynccontextmanager
from datetime import datetime
import hashlib
import os
import re
import uuid

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import Base, SessionLocal, engine
import models
from matching import compute_job_match, normalize_app_status, sanitize_markdown
from schemas import (
    ApplicationCreate,
    ApplicationStatusUpdate,
    JobListingCreate,
    JobListingUpdate,
    RecruiterNoteUpdate,
    RecruiterRegister,
    UserCreate,
    UserLogin,
)
from utils import (
    analyze_resume,
    compute_final_score,
    extract_skills_from_analysis,
    extract_text_from_pdf,
)
from vector_store import vector_store

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
HYBRID_VECTOR_WEIGHT = float(os.getenv("HYBRID_VECTOR_WEIGHT", "0.55"))
HYBRID_RULE_WEIGHT = max(0.0, 1.0 - HYBRID_VECTOR_WEIGHT)


# ===================== STARTUP =====================
os.makedirs(UPLOAD_DIR, exist_ok=True)
Base.metadata.create_all(bind=engine)


def ensure_schema_updates() -> None:
    """Run lightweight additive schema updates for existing databases."""
    ddl = [
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT FALSE",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS mime_type VARCHAR DEFAULT 'application/pdf'",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS file_size INTEGER DEFAULT 0",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS storage_path VARCHAR DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ NULL",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE job_listings ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ NULL",
        "ALTER TABLE job_listings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE job_listings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        """
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            applicant_id INTEGER NOT NULL REFERENCES users(id),
            job_listing_id INTEGER NOT NULL REFERENCES job_listings(id),
            status VARCHAR DEFAULT 'saved',
            recruiter_note TEXT DEFAULT '',
            last_status_updated_by INTEGER NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT unique_application UNIQUE(applicant_id, job_listing_id)
        )
        """,
    ]
    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))


ensure_schema_updates()


def seed_admin() -> None:
    db = SessionLocal()
    try:
        admin = db.query(models.UserDB).filter(models.UserDB.email == "admin@preplace.smvdu").first()
        if not admin:
            admin_user = models.UserDB(
                name="PREPLACE Admin",
                email="admin@preplace.smvdu",
                password="admin@123",
                role="admin",
            )
            db.add(admin_user)
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_admin()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================== HELPERS =====================
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
        .filter(models.Resume.user_id == user_id)
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
    return (
        f"Suggested role: {resume.suggested_role}. Score: {resume.score}. "
        f"Analysis: {resume.analysis}"
    )


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


def ensure_recruiter_owns_listing(db, recruiter_id: int, listing_id: int):
    listing = db.query(models.JobListing).filter(models.JobListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.recruiter_id != recruiter_id:
        raise HTTPException(status_code=403, detail="Not authorized for this listing")
    return listing


# ===================== AUTH =====================
@app.post("/register")
def register_user(user: UserCreate):
    db = SessionLocal()
    try:
        existing = db.query(models.UserDB).filter(models.UserDB.email == user.email).first()
        if existing:
            return {"error": "Email already registered"}

        new_user = models.UserDB(name=user.name, email=user.email, password=user.password, role=user.role)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"message": "User saved in database"}
    finally:
        db.close()


@app.post("/register-recruiter")
def register_recruiter(data: RecruiterRegister):
    db = SessionLocal()
    try:
        existing = db.query(models.UserDB).filter(models.UserDB.email == data.email).first()
        if existing:
            return {"error": "Email already registered"}

        new_user = models.UserDB(name=data.name, email=data.email, password=data.password, role="recruiter")
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        profile = models.RecruiterProfile(
            user_id=new_user.id,
            company_name=data.company_name,
            roles_hiring=data.roles_hiring,
            status="pending",
        )
        db.add(profile)
        db.commit()
        return {"message": "Recruiter registered successfully. Awaiting admin approval."}
    finally:
        db.close()


@app.post("/login")
def login(user: UserLogin):
    db = SessionLocal()
    try:
        existing_user = db.query(models.UserDB).filter(models.UserDB.email == user.email).first()
        if not existing_user:
            return {"error": "User not found"}
        if existing_user.password != user.password:
            return {"error": "Incorrect password"}

        result = {
            "message": "Login successful",
            "user": {
                "id": existing_user.id,
                "name": existing_user.name,
                "email": existing_user.email,
                "role": existing_user.role,
            },
        }

        if existing_user.role == "recruiter":
            profile = db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == existing_user.id).first()
            if profile:
                result["user"]["company_name"] = profile.company_name
                result["user"]["roles_hiring"] = profile.roles_hiring
                result["user"]["status"] = profile.status

        return result
    finally:
        db.close()


# ===================== RESUMES =====================
@app.post("/upload-resume")
def upload_resume(user_id: int, file: UploadFile = File(...)):
    db = SessionLocal()
    try:
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
            existing_resume.score = final_score
            existing_resume.updated_at = datetime.utcnow()
            db.commit()

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
            suggested_role=suggested_role,
            is_active=True,
            mime_type=file.content_type or "application/pdf",
            file_size=len(file_bytes),
            storage_path=file_location,
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)

        upsert_resume_vector(db, resume)

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
    finally:
        db.close()


@app.get("/my-resumes")
def get_my_resumes(user_id: int):
    db = SessionLocal()
    try:
        resumes = (
            db.query(models.Resume)
            .filter(models.Resume.user_id == user_id)
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
    finally:
        db.close()


@app.patch("/my-resumes/{resume_id}/activate")
def activate_resume(resume_id: int, user_id: int):
    db = SessionLocal()
    try:
        resume = db.query(models.Resume).filter(models.Resume.id == resume_id, models.Resume.user_id == user_id).first()
        if not resume:
            return {"error": "Resume not found"}
        db.query(models.Resume).filter(models.Resume.user_id == user_id).update({"is_active": False})
        resume.is_active = True
        resume.updated_at = datetime.utcnow()
        db.commit()
        return {"message": "Active resume updated"}
    finally:
        db.close()


@app.delete("/my-resumes/{resume_id}")
def delete_resume(resume_id: int, user_id: int):
    db = SessionLocal()
    try:
        resume = db.query(models.Resume).filter(models.Resume.id == resume_id, models.Resume.user_id == user_id).first()
        if not resume:
            return {"error": "Resume not found"}

        was_active = bool(resume.is_active)
        if resume.storage_path and os.path.exists(resume.storage_path):
            try:
                os.remove(resume.storage_path)
            except OSError:
                pass

        vector_store.delete_resume(resume.id)
        db.query(models.Application).filter(models.Application.applicant_id == user_id).delete()
        db.delete(resume)
        db.commit()

        if was_active:
            latest = (
                db.query(models.Resume)
                .filter(models.Resume.user_id == user_id)
                .order_by(models.Resume.id.desc())
                .first()
            )
            if latest:
                latest.is_active = True
                db.commit()

        return {"message": "Resume deleted"}
    finally:
        db.close()


# ===================== JOB LISTINGS =====================
@app.post("/job-listings")
def create_job_listing(recruiter_id: int, job: JobListingCreate):
    db = SessionLocal()
    try:
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
        return {"message": "Job listing submitted for admin approval", "id": listing.id}
    finally:
        db.close()


@app.get("/job-listings")
def get_job_listings(
    recruiter_id: int,
    q: str = "",
    status: str = "",
    sort_by: str = Query("latest", pattern="^(latest|oldest|role)$"),
):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@app.put("/job-listings/{listing_id}")
def update_job_listing(listing_id: int, recruiter_id: int, payload: JobListingUpdate):
    db = SessionLocal()
    try:
        listing = ensure_recruiter_owns_listing(db, recruiter_id, listing_id)

        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "description":
                setattr(listing, key, sanitize_markdown(value or ""))
            else:
                setattr(listing, key, value)

        listing.updated_at = datetime.utcnow()
        if listing.status in {"active", "rejected"}:
            listing.status = "pending_approval"

        db.commit()
        db.refresh(listing)
        upsert_job_vector(db, listing)
        return {"message": "Job listing updated", "status": listing.status}
    finally:
        db.close()


@app.delete("/job-listings/{listing_id}")
def delete_job_listing(listing_id: int, recruiter_id: int):
    db = SessionLocal()
    try:
        listing = ensure_recruiter_owns_listing(db, recruiter_id, listing_id)
        vector_store.delete_job(listing.id)
        db.query(models.Application).filter(models.Application.job_listing_id == listing.id).delete()
        db.delete(listing)
        db.commit()
        return {"message": "Job listing deleted"}
    finally:
        db.close()


@app.patch("/job-listings/{listing_id}/toggle")
def toggle_job_listing(listing_id: int):
    db = SessionLocal()
    try:
        listing = db.query(models.JobListing).filter(models.JobListing.id == listing_id).first()
        if not listing:
            return {"error": "Listing not found"}
        if listing.status == "pending_approval":
            return {"error": "Cannot toggle a pending listing. Wait for admin approval."}
        listing.status = "closed" if listing.status == "active" else "active"
        listing.updated_at = datetime.utcnow()
        db.commit()
        upsert_job_vector(db, listing)
        return {"message": "Status updated", "status": listing.status}
    finally:
        db.close()


# ===================== MATCHING =====================
@app.get("/matched-jobs")
def get_matched_jobs(
    user_id: int,
    q: str = "",
    department: str = "",
    min_match: int = Query(0, ge=0, le=100),
    sort_by: str = Query("hybrid", pattern="^(hybrid|rule|vector)$"),
):
    db = SessionLocal()
    try:
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
            hybrid = int(round(HYBRID_RULE_WEIGHT * rule_score + HYBRID_VECTOR_WEIGHT * vector_score))
            if hybrid < min_match:
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
                    "match": hybrid,
                    "rule_score": rule_score,
                    "vector_score": round(vector_score, 2),
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
    finally:
        db.close()


@app.get("/job-listings/{listing_id}/matched-candidates")
def matched_candidates_for_listing(
    listing_id: int,
    recruiter_id: int,
    q: str = "",
    status: str = "",
):
    db = SessionLocal()
    try:
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
            rule_score = compute_job_match(
                applicant_role=latest_resume.suggested_role or "",
                applicant_skills=applicant_skills,
                applicant_score=latest_resume.score or 0,
                job_role=listing.role_title,
                job_skills_str=listing.skills,
                job_min_score=listing.min_score,
                job_department=listing.department,
            )
            vector_score = float(vector_scores.get(latest_resume.id, 0.0))
            hybrid = int(round(HYBRID_RULE_WEIGHT * rule_score + HYBRID_VECTOR_WEIGHT * vector_score))

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
                    "rule_score": rule_score,
                    "vector_score": round(vector_score, 2),
                    "match": hybrid,
                    "application_id": app_state.id if app_state else None,
                    "application_status": app_status,
                    "recruiter_note": app_state.recruiter_note if app_state else "",
                }
            )

        result.sort(key=lambda x: x["match"], reverse=True)
        return result
    finally:
        db.close()


# ===================== APPLICATION WORKFLOW =====================
@app.post("/applications")
def create_or_update_application(user_id: int, payload: ApplicationCreate):
    db = SessionLocal()
    try:
        user = get_user_or_404(db, user_id)
        if user.role != "applicant":
            return {"error": "Only applicants can apply"}

        job = db.query(models.JobListing).filter(models.JobListing.id == payload.job_listing_id).first()
        if not job or job.status != "active":
            return {"error": "Job is unavailable"}

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
                status=new_status,
                recruiter_note="",
            )
            db.add(app_record)
        else:
            app_record.status = new_status
            app_record.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(app_record)
        return {"message": "Application updated", "application_id": app_record.id, "status": app_record.status}
    finally:
        db.close()


@app.get("/my-applications")
def my_applications(user_id: int, status: str = "", q: str = ""):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@app.patch("/applications/{application_id}/withdraw")
def withdraw_application(application_id: int, user_id: int):
    db = SessionLocal()
    try:
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
        return {"message": "Application withdrawn"}
    finally:
        db.close()


@app.get("/recruiter/applications")
def recruiter_applications(
    recruiter_id: int,
    listing_id: int | None = None,
    status: str = "",
    q: str = "",
    sort_by: str = Query("latest", pattern="^(latest|match|score)$"),
):
    db = SessionLocal()
    try:
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
            resume = get_latest_resume(db, applicant.id)
            listing = listing_map.get(row.job_listing_id)
            if not listing:
                continue

            skills = extract_skills_from_analysis(resume.analysis if resume else "")
            rule_score = compute_job_match(
                applicant_role=resume.suggested_role if resume else "",
                applicant_skills=skills,
                applicant_score=resume.score if resume else 0,
                job_role=listing.role_title,
                job_skills_str=listing.skills,
                job_min_score=listing.min_score,
                job_department=listing.department,
            )
            vector_score = 0.0
            if resume:
                vector_score = float(vector_store.query_resumes(job_vector_text(listing), top_k=50).get(resume.id, 0.0))
            hybrid = int(round(HYBRID_RULE_WEIGHT * rule_score + HYBRID_VECTOR_WEIGHT * vector_score))

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
                    "score": resume.score if resume else None,
                    "analysis": resume.analysis if resume else None,
                    "suggested_role": resume.suggested_role if resume else "",
                    "match": hybrid,
                    "rule_score": rule_score,
                    "vector_score": round(vector_score, 2),
                }
            )

        if sort_by == "match":
            out.sort(key=lambda x: x["match"], reverse=True)
        elif sort_by == "score":
            out.sort(key=lambda x: (x["score"] or 0), reverse=True)
        else:
            out.sort(key=lambda x: x["updated_at"] or "", reverse=True)

        return out
    finally:
        db.close()


@app.patch("/applications/{application_id}/status")
def recruiter_update_application_status(application_id: int, recruiter_id: int, payload: ApplicationStatusUpdate):
    db = SessionLocal()
    try:
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
        return {"message": "Application status updated", "status": status}
    finally:
        db.close()


@app.patch("/applications/{application_id}/note")
def recruiter_update_note(application_id: int, recruiter_id: int, payload: RecruiterNoteUpdate):
    db = SessionLocal()
    try:
        record = db.query(models.Application).filter(models.Application.id == application_id).first()
        if not record:
            return {"error": "Application not found"}

        listing = db.query(models.JobListing).filter(models.JobListing.id == record.job_listing_id).first()
        if not listing or listing.recruiter_id != recruiter_id:
            return {"error": "Not authorized"}

        record.recruiter_note = (payload.recruiter_note or "").strip()[:1000]
        record.updated_at = datetime.utcnow()
        db.commit()
        return {"message": "Recruiter note updated"}
    finally:
        db.close()


# ===================== APPLICANTS =====================
@app.get("/applicants")
def get_all_applicants(
    q: str = "",
    min_score: int = Query(0, ge=0, le=100),
    sort_by: str = Query("rank", pattern="^(rank|score|latest)$"),
):
    db = SessionLocal()
    try:
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

        return result
    finally:
        db.close()


# ===================== ADMIN =====================
@app.get("/admin/recruiters")
def admin_get_recruiters():
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@app.patch("/admin/recruiters/{user_id}/status")
def admin_update_recruiter_status(user_id: int, status: str):
    db = SessionLocal()
    try:
        profile = db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == user_id).first()
        if not profile:
            return {"error": "Recruiter profile not found"}
        profile.status = status
        db.commit()
        return {"message": f"Recruiter status updated to {status}"}
    finally:
        db.close()


@app.delete("/admin/recruiters/{user_id}")
def admin_delete_recruiter(user_id: int):
    db = SessionLocal()
    try:
        listing_ids = [x.id for x in db.query(models.JobListing).filter(models.JobListing.recruiter_id == user_id).all()]
        if listing_ids:
            db.query(models.Application).filter(models.Application.job_listing_id.in_(listing_ids)).delete()
            for listing_id in listing_ids:
                vector_store.delete_job(listing_id)

        db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == user_id).delete()
        db.query(models.JobListing).filter(models.JobListing.recruiter_id == user_id).delete()
        db.query(models.UserDB).filter(models.UserDB.id == user_id).delete()
        db.commit()
        return {"message": "Recruiter deleted"}
    finally:
        db.close()


@app.get("/admin/job-listings")
def admin_get_all_job_listings():
    db = SessionLocal()
    try:
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
    finally:
        db.close()


@app.patch("/admin/job-listings/{listing_id}/status")
def admin_update_job_status(listing_id: int, status: str):
    db = SessionLocal()
    try:
        listing = db.query(models.JobListing).filter(models.JobListing.id == listing_id).first()
        if not listing:
            return {"error": "Listing not found"}
        listing.status = status
        listing.updated_at = datetime.utcnow()
        db.commit()
        upsert_job_vector(db, listing)
        return {"message": f"Job listing status updated to {status}"}
    finally:
        db.close()


@app.get("/admin/stats")
def admin_stats():
    db = SessionLocal()
    try:
        total_applicants = db.query(models.UserDB).filter(models.UserDB.role == "applicant").count()
        total_recruiters = db.query(models.UserDB).filter(models.UserDB.role == "recruiter").count()
        pending_recruiters = db.query(models.RecruiterProfile).filter(models.RecruiterProfile.status == "pending").count()
        total_resumes = db.query(models.Resume).count()
        total_listings = db.query(models.JobListing).count()
        pending_jobs = db.query(models.JobListing).filter(models.JobListing.status == "pending_approval").count()
        total_applications = db.query(models.Application).count()

        return {
            "total_applicants": total_applicants,
            "total_recruiters": total_recruiters,
            "pending_recruiters": pending_recruiters,
            "total_resumes": total_resumes,
            "total_listings": total_listings,
            "pending_jobs": pending_jobs,
            "total_applications": total_applications,
            "vector_enabled": vector_store.enabled,
        }
    finally:
        db.close()
