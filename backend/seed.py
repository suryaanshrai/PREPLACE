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
        """**About the Role**

We're not hiring resumes — we're hiring builders. You'll work across the stack, shipping real features that go straight to production. This is a 6-month internship with a strong potential for a full-time offer based on performance.

**What You'll Do**

- Build and maintain backend services in Python (FastAPI), including REST and WebSocket APIs for data ingestion and product features
- Work with PostgreSQL — schema design, query optimisation, and migrations
- Develop and modify frontend components in React; build operator-facing dashboards and iterate based on team feedback
- Write clean, tested code and participate in peer code reviews; maintain internal documentation
- Help with containerised deployments using Docker across dev and staging environments
- Debug issues end-to-end — trace a bug from a React component through an API to a misconfigured service

**Requirements**

- Strong fundamentals in data structures, algorithms, and systems thinking
- Proficiency in Python — you write clean, maintainable code, not just scripts that work once
- Working knowledge of JavaScript/React — enough to build and modify frontend components
- Comfortable on Linux: CLI, processes, basic networking
- Understanding of REST APIs, client-server architecture, and async patterns

**Nice to Have**

- Familiarity with Docker and containers
- Exposure to cloud platforms (AWS/GCP)
- Experience with PostgreSQL or similar relational databases
- Basic CI/CD knowledge (GitHub Actions)""",
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
        """**About the Role**

We are building scalable backend systems that power our core product. As a Backend Engineer, you will own services end-to-end — from design to deployment to reliability. You'll work in a small, high-ownership team where your decisions directly shape the architecture.

**What You'll Do**

- Design and build scalable RESTful APIs and microservices using Python (FastAPI/Django)
- Integrate ML/data pipelines into backend systems and internal services
- Build and maintain async job systems — background workers, retries, idempotency, and state tracking
- Work with message brokers (Redis/RabbitMQ) for event-driven communication between services
- Design and manage cloud infrastructure on AWS/GCP; deploy services using Docker and CI/CD pipelines (GitHub Actions)
- Implement logging, monitoring, and alerting across distributed workflows (Prometheus, Grafana)
- Contribute to architecture decisions, database modelling, and backend scaling strategies
- Conduct code reviews and mentor junior engineers

**Requirements**

- 1–2 years of hands-on backend development experience
- Strong Python skills; proficiency in FastAPI or similar frameworks
- Solid experience with PostgreSQL and SQL query optimisation
- Experience building and consuming REST APIs at scale
- Familiarity with Docker and CI/CD workflows
- Understanding of distributed systems, async processing, and microservices architecture

**Nice to Have**

- Experience with Kubernetes or container orchestration
- Infrastructure-as-code experience (Terraform/Pulumi)
- Exposure to observability tools (OpenTelemetry, Grafana)
- Prior work integrating ML models or LLM pipelines into production systems""",
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
        """**About the Role**

We're looking for a Frontend Developer to own the user-facing layer of our product. You'll work in a cross-functional squad alongside backend engineers, designers, and a product manager to deliver fast, polished, and accessible web experiences.

**What You'll Do**

- Develop and maintain responsive web interfaces using React and TypeScript
- Build reusable, performant component libraries and design system primitives
- Translate Figma designs and wireframes into high-quality, pixel-accurate code
- Integrate RESTful APIs and manage client-side state (Redux or Context API)
- Optimise frontend performance — lazy loading, code splitting, bundle size, rendering efficiency
- Ensure cross-browser and cross-device compatibility; write unit and integration tests
- Participate in code reviews, maintain technical documentation, and contribute to frontend architecture decisions
- Collaborate asynchronously in a remote-first environment

**Requirements**

- 1–2 years of experience in frontend development
- Strong proficiency in React.js and its core principles (hooks, component lifecycle, reconciliation)
- Solid TypeScript skills; you write type-safe code without fighting the compiler
- Good understanding of HTML5, CSS3, and responsive design
- Experience consuming REST APIs and handling async data flows
- Familiarity with Git, PR workflows, and agile development practices

**Nice to Have**

- Experience with micro-frontend architecture or design systems
- Familiarity with testing frameworks (Jest, React Testing Library)
- Exposure to Next.js or SSR patterns
- Understanding of web accessibility (WCAG) standards""",
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
        """**About the Role**

We are looking for a Data Analyst who is equally comfortable writing complex SQL and explaining a trend to a non-technical stakeholder. You'll work directly with business teams to turn raw data into decisions — building dashboards, running analyses, and flagging what matters.

**What You'll Do**

- Write advanced SQL queries (window functions, CTEs, complex multi-table joins) against our data warehouse (PostgreSQL/BigQuery)
- Build and maintain interactive dashboards in Tableau and Power BI for business stakeholders across growth, operations, and finance
- Use Python (Pandas, NumPy) for exploratory data analysis, statistical modelling, and automating recurring reports
- Identify trends, anomalies, and business insights; present findings clearly with supporting visualisations
- Implement data quality checks and validation frameworks to ensure data integrity
- Collaborate with the data engineering team to define requirements for automated pipelines
- Respond to ad-hoc analysis requests with quick, well-documented turnarounds

**Requirements**

- Strong SQL skills — you're comfortable with window functions, subqueries, and query optimisation
- Hands-on Python experience for data analysis (Pandas, NumPy)
- Experience building dashboards in Tableau or Power BI
- Analytical mindset with strong attention to detail
- Good communication skills — able to translate data findings into business language

**Nice to Have**

- Experience with a cloud data warehouse (BigQuery, Redshift, or Snowflake)
- Familiarity with dbt or similar data transformation tools
- Exposure to A/B testing and statistical significance frameworks
- Degree in Computer Science, Statistics, Mathematics, or a related field""",
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
        """**About the Role**

We're looking for an ML Intern with a genuine curiosity for applied machine learning. You'll work alongside senior data scientists on real datasets, building and evaluating models that go into production — not toy projects. Internship duration is 3–6 months with potential for full-time conversion based on performance.

**What You'll Do**

- Preprocess, clean, and explore real-world datasets using Pandas and NumPy
- Implement, train, and benchmark classification, regression, and clustering models using Scikit-learn and TensorFlow/PyTorch
- Conduct feature engineering and hyperparameter tuning; track experiments systematically (MLflow or similar)
- Evaluate model performance using appropriate metrics; write clear experiment reports
- Assist in integrating trained models into backend APIs for inference
- Collaborate with the data engineering team to understand data pipelines and upstream quality issues
- Present findings and model results to the team in weekly syncs

**Requirements**

- Strong Python programming skills
- Solid understanding of core ML concepts — supervised/unsupervised learning, overfitting, cross-validation, evaluation metrics
- Hands-on experience with Scikit-learn, Pandas, and NumPy
- Ability to read, understand, and adapt existing ML code
- Currently pursuing or recently completed a degree in CS, Data Science, Statistics, or related field

**Nice to Have**

- Experience with deep learning frameworks (TensorFlow or PyTorch)
- Familiarity with MLflow or experiment tracking tools
- Exposure to cloud platforms (AWS SageMaker, GCP Vertex AI)
- Prior project or kaggle competition experience""",
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
