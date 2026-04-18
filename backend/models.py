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
    indexed_at = Column(DateTime(timezone=True), nullable=True)
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


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    applicant_id = Column(Integer, ForeignKey("users.id"), index=True)
    job_listing_id = Column(Integer, ForeignKey("job_listings.id"), index=True)
    status = Column(String, default="saved")
    recruiter_note = Column(Text, default="")
    last_status_updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("applicant_id", "job_listing_id", name="unique_application"),
    )