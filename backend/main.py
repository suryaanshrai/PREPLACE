from contextlib import asynccontextmanager
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import Base, SessionLocal, engine
import models
from security import hash_password
from routers import admin_router, applications_router, auth_router, jobs_router, linkedin_router, resumes_router

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")


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
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS parsed_text TEXT DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS scoring_engine VARCHAR DEFAULT 'legacy'",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS scoring_version VARCHAR DEFAULT 'v1'",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS score_breakdown_json TEXT DEFAULT ''",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ NULL",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE job_listings ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ NULL",
        "ALTER TABLE job_listings ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE job_listings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS resume_id INTEGER NULL REFERENCES resumes(id)",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS resume_filename_snapshot VARCHAR DEFAULT ''",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS resume_score_snapshot INTEGER NULL",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS resume_role_snapshot VARCHAR DEFAULT ''",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS resume_deleted BOOLEAN DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS idx_applications_resume_id ON applications(resume_id)",
        """
        CREATE TABLE IF NOT EXISTS scoring_templates (
            id SERIAL PRIMARY KEY,
            title VARCHAR NOT NULL,
            role_title VARCHAR NOT NULL,
            description TEXT DEFAULT '',
            category VARCHAR DEFAULT 'General',
            is_active BOOLEAN DEFAULT TRUE,
            created_by INTEGER NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS penalty_rules (
            id SERIAL PRIMARY KEY,
            recruiter_id INTEGER NULL REFERENCES users(id),
            listing_id INTEGER NULL REFERENCES job_listings(id),
            category VARCHAR NOT NULL,
            label VARCHAR NOT NULL,
            keywords TEXT DEFAULT '',
            penalty_value INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_by INTEGER NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT unique_penalty_scope_category UNIQUE (recruiter_id, listing_id, category)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_penalty_rules_recruiter_listing ON penalty_rules(recruiter_id, listing_id)",
        """
        UPDATE applications a
        SET
            resume_id = sub.id,
            resume_filename_snapshot = CASE
                WHEN COALESCE(a.resume_filename_snapshot, '') = '' THEN COALESCE(sub.original_filename, sub.filename, 'Resume')
                ELSE a.resume_filename_snapshot
            END,
            resume_score_snapshot = COALESCE(a.resume_score_snapshot, sub.score),
            resume_role_snapshot = CASE
                WHEN COALESCE(a.resume_role_snapshot, '') = '' THEN COALESCE(sub.suggested_role, '')
                ELSE a.resume_role_snapshot
            END,
            resume_deleted = FALSE
        FROM (
            SELECT DISTINCT ON (r.user_id) r.id, r.user_id, r.original_filename, r.filename, r.score, r.suggested_role
            FROM resumes r
            ORDER BY r.user_id, r.is_active DESC, r.id DESC
        ) AS sub
        WHERE a.applicant_id = sub.user_id
          AND a.resume_id IS NULL AND COALESCE(a.resume_deleted, FALSE) = FALSE
        """,
        """
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            applicant_id INTEGER NOT NULL REFERENCES users(id),
            job_listing_id INTEGER NOT NULL REFERENCES job_listings(id),
            resume_id INTEGER NULL REFERENCES resumes(id),
            status VARCHAR DEFAULT 'saved',
            recruiter_note TEXT DEFAULT '',
            resume_filename_snapshot VARCHAR DEFAULT '',
            resume_score_snapshot INTEGER NULL,
            resume_role_snapshot VARCHAR DEFAULT '',
            resume_deleted BOOLEAN DEFAULT FALSE,
            last_status_updated_by INTEGER NULL REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT unique_application UNIQUE(applicant_id, job_listing_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS linkedin_cache (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
            results_json TEXT DEFAULT '[]',
            search_params_json TEXT DEFAULT '{}',
            cached_at TIMESTAMPTZ DEFAULT NOW(),
            expires_at TIMESTAMPTZ NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            actor_id INTEGER NULL REFERENCES users(id),
            action VARCHAR,
            target_type VARCHAR DEFAULT '',
            target_id INTEGER NULL,
            detail TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
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
                password=hash_password("admin@123"),
                role="admin",
            )
            db.add(admin_user)
            db.commit()
        elif not str(admin.password).startswith("pbkdf2$"):
            admin.password = hash_password("admin@123")
            db.commit()
    finally:
        db.close()


def seed_scoring_defaults() -> None:
    db = SessionLocal()
    try:
        defaults = [
            {
                "title": "Software Development Engineer (Intern)",
                "role_title": "SDE Intern",
                "description": (
                    "Build and maintain backend APIs and product features using Python, FastAPI, or Django with PostgreSQL and Redis. "
                    "Write clean, well-tested code, participate in code reviews, and contribute to CI/CD workflows using Docker and Git. "
                    "Collaborate with senior engineers on system design, debugging, and performance optimization. "
                    "Experience with REST APIs, object-oriented programming, and basic cloud tools (AWS/GCP) is a plus."
                ),
                "category": "Engineering",
            },
            {
                "title": "Data Analyst (Entry)",
                "role_title": "Data Analyst",
                "description": (
                    "Analyze large structured and unstructured datasets to generate actionable business insights using Python, Pandas, and SQL. "
                    "Build and maintain dashboards and reports in Tableau, Power BI, or Looker. "
                    "Collaborate with product and engineering teams to define KPIs and support data-driven decision-making. "
                    "Experience with data cleaning, A/B testing, statistical analysis, and Excel or Google Sheets is expected."
                ),
                "category": "Data",
            },
            {
                "title": "Frontend Developer (React)",
                "role_title": "Frontend Developer",
                "description": (
                    "Build performant, accessible, and responsive web interfaces using React, TypeScript, and CSS. "
                    "Consume REST and GraphQL APIs, manage application state, and write unit and integration tests. "
                    "Collaborate with designers to translate Figma mockups into pixel-perfect components. "
                    "Experience with Vite or Webpack, component libraries, and web performance optimization is preferred."
                ),
                "category": "Engineering",
            },
            {
                "title": "Backend Developer (Node/Python)",
                "role_title": "Backend Developer",
                "description": (
                    "Design, build, and maintain scalable server-side services, RESTful APIs, and microservices using Python (Django, FastAPI, Flask) or Node.js (Express). "
                    "Manage relational and NoSQL databases including PostgreSQL, MySQL, MongoDB, and Redis. "
                    "Implement authentication, authorization, and security best practices; deploy services using Docker, Kubernetes, and cloud platforms (AWS, GCP). "
                    "Write automated tests, participate in code reviews, and contribute to CI/CD pipelines and system architecture decisions."
                ),
                "category": "Engineering",
            },
            {
                "title": "Full Stack Developer",
                "role_title": "Full Stack Developer",
                "description": (
                    "Develop end-to-end web applications covering both React or Vue frontend interfaces and Python or Node.js backend services. "
                    "Design and integrate REST or GraphQL APIs, manage PostgreSQL or MongoDB databases, and handle authentication flows. "
                    "Deploy applications using Docker, cloud platforms (AWS/GCP/Azure), and CI/CD pipelines. "
                    "Solid understanding of software architecture, testing, and agile collaboration is required."
                ),
                "category": "Engineering",
            },
            {
                "title": "Machine Learning Engineer",
                "role_title": "ML Engineer",
                "description": (
                    "Build, train, evaluate, and deploy machine learning and deep learning models using Python, PyTorch, TensorFlow, or scikit-learn. "
                    "Develop data pipelines, feature engineering workflows, and model monitoring systems using tools like MLflow, Airflow, or Kubeflow. "
                    "Collaborate with data scientists and engineers to productionize models as REST APIs or batch inference jobs. "
                    "Experience with NLP, computer vision, LLMs, RAG pipelines, or recommendation systems is a strong advantage."
                ),
                "category": "Data/AI",
            },
            {
                "title": "DevOps / Cloud Engineer",
                "role_title": "DevOps Engineer",
                "description": (
                    "Manage and optimize CI/CD pipelines using GitHub Actions, Jenkins, or GitLab CI; containerize applications with Docker and orchestrate with Kubernetes. "
                    "Provision and maintain cloud infrastructure on AWS, GCP, or Azure using Terraform or Ansible. "
                    "Monitor system reliability with tools like Prometheus, Grafana, and ELK; implement incident response and on-call workflows. "
                    "Strong experience with Linux administration, networking, security hardening, and infrastructure-as-code practices is required."
                ),
                "category": "Engineering",
            },
            {
                "title": "UI/UX Designer",
                "role_title": "UX Designer",
                "description": (
                    "Design intuitive, accessible, and visually consistent user interfaces and experiences for web and mobile products using Figma or Sketch. "
                    "Conduct user research, usability testing, and competitive analysis to inform design decisions. "
                    "Create wireframes, prototypes, and design systems; collaborate closely with frontend engineers during implementation. "
                    "Strong portfolio demonstrating interaction design, information architecture, and visual design skills is expected."
                ),
                "category": "Design",
            },
            {
                "title": "Cybersecurity Analyst",
                "role_title": "Security Analyst",
                "description": (
                    "Identify, assess, and remediate security vulnerabilities across applications, networks, and infrastructure. "
                    "Conduct penetration testing, threat modelling, and security audits; monitor systems with SIEM tools like Splunk or QRadar. "
                    "Implement and enforce security frameworks such as ISO 27001, NIST, or OWASP; respond to security incidents and manage CVEs. "
                    "Experience with ethical hacking, network security, identity management, and cloud security is highly desirable."
                ),
                "category": "Security",
            },
            {
                "title": "Mobile Developer (React Native/Flutter)",
                "role_title": "Mobile Developer",
                "description": (
                    "Build and maintain cross-platform iOS and Android applications using React Native or Flutter with clean, maintainable code. "
                    "Integrate REST APIs, handle device permissions, push notifications, and native device features such as camera and GPS. "
                    "Publish apps to the App Store and Google Play; manage app performance, crash reporting, and CI/CD with tools like Fastlane. "
                    "Experience with state management (Redux, Riverpod), TypeScript, and native module bridging is preferred."
                ),
                "category": "Engineering",
            },
        ]
        existing = {t.title: t for t in db.query(models.ScoringTemplate).all()}
        for row in defaults:
            if row["title"] not in existing:
                db.add(models.ScoringTemplate(**row, is_active=True, created_by=1))
            else:
                # Update description/role_title in case they were enriched
                t = existing[row["title"]]
                t.description = row["description"]
                t.role_title = row["role_title"]

        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_admin()
    seed_scoring_defaults()
    yield


OPENAPI_TAGS = [
    {"name": "Auth", "description": "Registration, login, and token validation."},
    {"name": "Resumes", "description": "Resume upload and resume management endpoints."},
    {"name": "Jobs", "description": "Job listing CRUD and state transitions."},
    {"name": "Matching", "description": "Hybrid vector + rules matching endpoints."},
    {"name": "Applications", "description": "Candidate applications and recruiter pipeline actions."},
    {"name": "Applicants", "description": "Applicant listing and ranking endpoints."},
    {"name": "Admin", "description": "Administrative moderation and platform controls."},
    {"name": "Analytics", "description": "Recruiter and applicant analytics summaries."},
    {"name": "Audit", "description": "Audit trail and traceability endpoints."},
]


app = FastAPI(lifespan=lifespan, openapi_tags=OPENAPI_TAGS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(resumes_router)
app.include_router(jobs_router)
app.include_router(applications_router)
app.include_router(admin_router)
app.include_router(linkedin_router)
