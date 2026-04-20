from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func
from database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    original_filename = Column(String)
    file_hash = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))
    score = Column(Integer)
    analysis = Column(String)
    suggested_role = Column(String, default="")
    is_active = Column(Boolean, default=False)
    mime_type = Column(String, default="application/pdf")
    file_size = Column(Integer, default=0)
    storage_path = Column(String, default="")
    parsed_text = Column(Text, default="")
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    scoring_engine = Column(String, default="legacy")
    scoring_version = Column(String, default="v1")
    score_breakdown_json = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("user_id", "file_hash", name="unique_user_resume"),
    )


class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True)
    password = Column(String)
    role = Column(String, default="applicant")


class RecruiterProfile(Base):
    __tablename__ = "recruiter_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    company_name = Column(String)
    roles_hiring = Column(String, default="")
    status = Column(String, default="approved")  # approved / pending


class JobListing(Base):
    __tablename__ = "job_listings"

    id = Column(Integer, primary_key=True, index=True)
    recruiter_id = Column(Integer, ForeignKey("users.id"))
    role_title = Column(String)
    department = Column(String, default="")
    job_type = Column(String, default="Internship")
    location = Column(String, default="")
    ctc = Column(String, default="")
    description = Column(Text, default="")
    skills = Column(String, default="")        # comma-separated
    min_cgpa = Column(Float, default=0)
    min_score = Column(Integer, default=0)
    experience = Column(String, default="Fresher (0 years)")
    status = Column(String, default="active")  # pending_approval / active / closed / rejected
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ScoringTemplate(Base):
    __tablename__ = "scoring_templates"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    role_title = Column(String, nullable=False)
    description = Column(Text, default="")
    category = Column(String, default="General")
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PenaltyRule(Base):
    __tablename__ = "penalty_rules"

    id = Column(Integer, primary_key=True, index=True)
    recruiter_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    listing_id = Column(Integer, ForeignKey("job_listings.id"), nullable=True, index=True)
    category = Column(String, nullable=False)
    label = Column(String, nullable=False)
    keywords = Column(Text, default="")
    penalty_value = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("recruiter_id", "listing_id", "category", name="unique_penalty_scope_category"),
    )


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    applicant_id = Column(Integer, ForeignKey("users.id"), index=True)
    job_listing_id = Column(Integer, ForeignKey("job_listings.id"), index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=True, index=True)
    status = Column(String, default="saved")
    recruiter_note = Column(Text, default="")
    resume_filename_snapshot = Column(String, default="")
    resume_score_snapshot = Column(Integer, nullable=True)
    resume_role_snapshot = Column(String, default="")
    resume_deleted = Column(Boolean, default=False)
    last_status_updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("applicant_id", "job_listing_id", name="unique_application"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String)
    target_type = Column(String, default="")
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LinkedInCache(Base):
    __tablename__ = "linkedin_cache"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    results_json = Column(Text, default="[]")
    search_params_json = Column(Text, default="{}")
    cached_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)