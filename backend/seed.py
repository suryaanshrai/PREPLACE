"""
seed.py — Standalone demo-data seeder for PREPLACE.

Run from the backend/ directory after a fresh server start:
    python seed.py

The script is fully idempotent — safe to re-run at any time.
Each entity group is looked up before inserting, so existing rows are skipped.

Entities seeded
---------------
1. Users          — 1 admin, 2 recruiters, 3 applicants
2. RecruiterProfiles — approved profiles for both recruiters
3. JobListings    — 5 active listings (3 TechCorp, 2 DataCo)
4. Resumes        — 1 stub row per applicant  (no PDF on disk)
5. Applications   — 6 rows with realistic statuses

Excluded (already handled by main.py on startup)
-------------------------------------------------
- ScoringTemplates and PenaltyRules
"""

import hashlib
import sys

from database import SessionLocal, engine
import models
from models import Base
from security import hash_password

# ---------------------------------------------------------------------------
# Demo credentials (printed at the end for quick reference)
# ---------------------------------------------------------------------------
RECRUITER_PASSWORD = "recruiter@123"
APPLICANT_PASSWORD = "applicant@123"
ADMIN_PASSWORD = "admin@123"

# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

USERS = [
    # (name, email, password, role)
    ("PREPLACE Admin",   "admin@preplace.smvdu", ADMIN_PASSWORD,     "admin"),
    ("Priya Sharma",     "priya@techcorp.com",   RECRUITER_PASSWORD,  "recruiter"),
    ("Rahul Mehta",      "rahul@dataco.com",      RECRUITER_PASSWORD,  "recruiter"),
    ("Alice Fernandez",  "alice@example.com",     APPLICANT_PASSWORD,  "applicant"),
    ("Bob Singh",        "bob@example.com",       APPLICANT_PASSWORD,  "applicant"),
    ("Charlie Nair",     "charlie@example.com",   APPLICANT_PASSWORD,  "applicant"),
]

RECRUITER_PROFILES = [
    # (email, company_name, roles_hiring)
    (
        "priya@techcorp.com",
        "TechCorp Inc.",
        "SDE Intern,Backend Engineer,Frontend Developer",
    ),
    (
        "rahul@dataco.com",
        "DataCo Analytics",
        "Data Analyst,ML Intern",
    ),
]

# (recruiter_email, role_title, department, job_type, location, ctc, description, skills, min_cgpa, min_score, experience)
JOB_LISTINGS = [
    (
        "priya@techcorp.com",
        "SDE Intern",
        "Engineering",
        "Internship",
        "Remote",
        "₹20,000/month",
        "Build backend APIs and contribute to core product features using Python, FastAPI, and PostgreSQL. Write clean, tested code and participate in code reviews.",
        "Python,FastAPI,PostgreSQL,Docker,Git",
        7.0,
        60,
        "Fresher (0 years)",
    ),
    (
        "priya@techcorp.com",
        "Backend Engineer",
        "Engineering",
        "Full-Time",
        "Bangalore",
        "₹12-18 LPA",
        "Design and implement scalable REST microservices. Own service reliability, contribute to architecture decisions, and mentor junior engineers.",
        "Python,SQL,REST,Microservices,Docker,Kubernetes",
        7.5,
        65,
        "1-2 years",
    ),
    (
        "priya@techcorp.com",
        "Frontend Developer",
        "Engineering",
        "Full-Time",
        "Remote",
        "₹10-15 LPA",
        "Build responsive React applications, consume REST APIs, and improve UI/UX quality and performance across the product.",
        "React,TypeScript,CSS,HTML,REST,Git",
        7.0,
        60,
        "1-2 years",
    ),
    (
        "rahul@dataco.com",
        "Data Analyst",
        "Data",
        "Full-Time",
        "Delhi",
        "₹8-12 LPA",
        "Analyze large datasets, build dashboards in Tableau, and generate actionable business insights using SQL and Python.",
        "Python,SQL,Tableau,Pandas,Excel,Power BI",
        7.0,
        58,
        "Fresher (0 years)",
    ),
    (
        "rahul@dataco.com",
        "ML Intern",
        "Data",
        "Internship",
        "Remote",
        "₹15,000/month",
        "Assist in building and evaluating machine learning models. Work with real-world datasets and contribute to model deployment pipelines.",
        "Python,ML,TensorFlow,Scikit-learn,Pandas,NumPy",
        7.5,
        62,
        "Fresher (0 years)",
    ),
]

# (applicant_email, filename, score, suggested_role)
RESUMES = [
    ("alice@example.com",   "alice_resume.pdf",   78, "SDE Intern"),
    ("bob@example.com",     "bob_resume.pdf",     72, "Backend Engineer"),
    ("charlie@example.com", "charlie_resume.pdf", 65, "Data Analyst"),
]

# (applicant_email, job_role_title, status)
APPLICATIONS = [
    ("alice@example.com",   "SDE Intern",         "applied"),
    ("alice@example.com",   "Data Analyst",       "saved"),
    ("bob@example.com",     "Backend Engineer",   "applied"),
    ("bob@example.com",     "Frontend Developer", "saved"),
    ("charlie@example.com", "ML Intern",          "applied"),
    ("charlie@example.com", "Data Analyst",       "shortlisted"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_hash(email: str) -> str:
    """Deterministic stub hash derived from the applicant's email."""
    return hashlib.sha256(f"seed:resume:{email}".encode()).hexdigest()


def _section(title: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}")


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_users(db) -> dict[str, int]:
    """Seed users. Returns {email: user_id} for all demo users."""
    _section("1 / 5  Users")
    id_map: dict[str, int] = {}

    for name, email, password, role in USERS:
        existing = db.query(models.UserDB).filter(models.UserDB.email == email).first()
        if existing:
            print(f"  SKIP   {email!r}  (already exists, id={existing.id})")
            id_map[email] = existing.id
        else:
            user = models.UserDB(
                name=name,
                email=email,
                password=hash_password(password),
                role=role,
            )
            db.add(user)
            db.flush()  # get the auto-generated id before commit
            print(f"  SEED   {email!r}  role={role!r}  id={user.id}")
            id_map[email] = user.id

    db.commit()
    return id_map


def seed_recruiter_profiles(db, id_map: dict[str, int]) -> None:
    _section("2 / 5  Recruiter Profiles")

    for email, company_name, roles_hiring in RECRUITER_PROFILES:
        user_id = id_map.get(email)
        if not user_id:
            print(f"  SKIP   {email!r}  (user not found)")
            continue

        existing = (
            db.query(models.RecruiterProfile)
            .filter(models.RecruiterProfile.user_id == user_id)
            .first()
        )
        if existing:
            print(f"  SKIP   {email!r}  (profile already exists)")
        else:
            profile = models.RecruiterProfile(
                user_id=user_id,
                company_name=company_name,
                roles_hiring=roles_hiring,
                status="approved",
            )
            db.add(profile)
            print(f"  SEED   {email!r}  company={company_name!r}")

    db.commit()


def seed_job_listings(db, id_map: dict[str, int]) -> None:
    _section("3 / 5  Job Listings")

    for row in JOB_LISTINGS:
        (
            recruiter_email, role_title, department, job_type, location,
            ctc, description, skills, min_cgpa, min_score, experience,
        ) = row

        recruiter_id = id_map.get(recruiter_email)
        if not recruiter_id:
            print(f"  SKIP   {role_title!r}  (recruiter {recruiter_email!r} not found)")
            continue

        existing = (
            db.query(models.JobListing)
            .filter(
                models.JobListing.recruiter_id == recruiter_id,
                models.JobListing.role_title == role_title,
            )
            .first()
        )
        if existing:
            print(f"  SKIP   {role_title!r}  by {recruiter_email!r}  (already exists)")
        else:
            listing = models.JobListing(
                recruiter_id=recruiter_id,
                role_title=role_title,
                department=department,
                job_type=job_type,
                location=location,
                ctc=ctc,
                description=description,
                skills=skills,
                min_cgpa=min_cgpa,
                min_score=min_score,
                experience=experience,
                status="active",
            )
            db.add(listing)
            print(f"  SEED   {role_title!r}  by {recruiter_email!r}")

    db.commit()


def seed_resumes(db, id_map: dict[str, int]) -> dict[str, int]:
    """Seed stub resume rows. Returns {applicant_email: resume_id}."""
    _section("4 / 5  Resumes (stub records)")
    resume_map: dict[str, int] = {}

    for email, filename, score, suggested_role in RESUMES:
        user_id = id_map.get(email)
        if not user_id:
            print(f"  SKIP   {email!r}  (user not found)")
            continue

        file_hash = _file_hash(email)
        existing = (
            db.query(models.Resume)
            .filter(
                models.Resume.user_id == user_id,
                models.Resume.file_hash == file_hash,
            )
            .first()
        )
        if existing:
            print(f"  SKIP   {email!r}  (resume already exists, id={existing.id})")
            resume_map[email] = existing.id
        else:
            resume = models.Resume(
                user_id=user_id,
                filename=filename,
                original_filename=filename,
                file_hash=file_hash,
                score=score,
                suggested_role=suggested_role,
                is_active=True,
                mime_type="application/pdf",
                file_size=0,
                storage_path="",
                parsed_text="",
                scoring_engine="legacy",
                scoring_version="v1",
            )
            db.add(resume)
            db.flush()
            print(f"  SEED   {email!r}  score={score}  role={suggested_role!r}  id={resume.id}")
            resume_map[email] = resume.id

    db.commit()
    return resume_map


def seed_applications(
    db,
    id_map: dict[str, int],
    resume_map: dict[str, int],
) -> None:
    _section("5 / 5  Applications")

    for applicant_email, role_title, status in APPLICATIONS:
        applicant_id = id_map.get(applicant_email)
        if not applicant_id:
            print(f"  SKIP   {applicant_email!r} → {role_title!r}  (applicant not found)")
            continue

        # Find the job listing by role_title (unique enough for seed data)
        listing = (
            db.query(models.JobListing)
            .filter(models.JobListing.role_title == role_title)
            .first()
        )
        if not listing:
            print(f"  SKIP   {applicant_email!r} → {role_title!r}  (job listing not found)")
            continue

        existing = (
            db.query(models.Application)
            .filter(
                models.Application.applicant_id == applicant_id,
                models.Application.job_listing_id == listing.id,
            )
            .first()
        )
        if existing:
            print(
                f"  SKIP   {applicant_email!r} → {role_title!r}  "
                f"(application already exists, status={existing.status!r})"
            )
        else:
            resume_id = resume_map.get(applicant_email)
            resume_score = None
            resume_filename = ""
            resume_role = ""
            if resume_id:
                r = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
                if r:
                    resume_score = r.score
                    resume_filename = r.original_filename or r.filename or ""
                    resume_role = r.suggested_role or ""

            app = models.Application(
                applicant_id=applicant_id,
                job_listing_id=listing.id,
                resume_id=resume_id,
                status=status,
                resume_filename_snapshot=resume_filename,
                resume_score_snapshot=resume_score,
                resume_role_snapshot=resume_role,
                resume_deleted=False,
            )
            db.add(app)
            print(f"  SEED   {applicant_email!r} → {role_title!r}  status={status!r}")

    db.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("\n" + "=" * 50)
    print("  PREPLACE — Demo Data Seeder")
    print("=" * 50)

    # Ensure all tables exist — safe on both fresh and existing databases
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        id_map = seed_users(db)
        seed_recruiter_profiles(db, id_map)
        seed_job_listings(db, id_map)
        resume_map = seed_resumes(db, id_map)
        seed_applications(db, id_map, resume_map)
    except Exception as exc:
        db.rollback()
        print(f"\n[ERROR] Seeding failed: {exc}")
        sys.exit(1)
    finally:
        db.close()

    print("\n" + "=" * 50)
    print("  Seeding complete!")
    print("=" * 50)
    print("\nDemo credentials")
    print("  Admin      admin@preplace.smvdu  /  admin@123")
    print("  Recruiter  priya@techcorp.com    /  recruiter@123")
    print("  Recruiter  rahul@dataco.com      /  recruiter@123")
    print("  Applicant  alice@example.com     /  applicant@123")
    print("  Applicant  bob@example.com       /  applicant@123")
    print("  Applicant  charlie@example.com   /  applicant@123")
    print()


if __name__ == "__main__":
    main()
