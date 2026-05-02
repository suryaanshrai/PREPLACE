from contextlib import asynccontextmanager
import os

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
        "ALTER TABLE penalty_rules DROP CONSTRAINT IF EXISTS unique_penalty_scope_category",
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
            admin_password = os.getenv("ADMIN_PASSWORD")
            if not admin_password:
                import warnings
                admin_password = "admin@123"
                warnings.warn(
                    "ADMIN_PASSWORD env var is not set. Using insecure default 'admin@123'. "
                    "Set ADMIN_PASSWORD before deploying to production.",
                    stacklevel=2,
                )
            admin_user = models.UserDB(
                name="PREPLACE Admin",
                email="admin@preplace.smvdu",
                password=hash_password(admin_password),
                role="admin",
            )
            db.add(admin_user)
            db.commit()
        # Never overwrite an existing admin password on startup — doing so would
        # silently undo any operator password change.
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
                    "**About the Role**\n\n"
                    "A 6-month engineering internship working on real production systems — not toy projects. "
                    "You'll ship features end-to-end alongside senior engineers and be expected to take ownership of what you build.\n\n"
                    "**What You'll Do**\n\n"
                    "- Build and maintain backend API endpoints using Python (FastAPI or Django)\n"
                    "- Write clean, tested code using pytest; follow Git and GitHub PR workflows\n"
                    "- Work with PostgreSQL databases — write queries, design schemas, run migrations\n"
                    "- Build and integrate REST endpoints; participate in peer code reviews\n"
                    "- Implement basic authentication and session handling using JWT\n"
                    "- Gain hands-on exposure to Docker for local development and service containerisation\n"
                    "- Deploy services to AWS or GCP staging environments\n\n"
                    "**Requirements**\n\n"
                    "- Proficiency in Python — you write clean, maintainable code, not just scripts\n"
                    "- Solid understanding of data structures, algorithms, and REST principles\n"
                    "- Familiarity with Git and collaborative development workflows\n"
                    "- Basic SQL knowledge — SELECT, JOIN, GROUP BY, subqueries\n"
                    "- Enrolled in or recently completed a CS or related degree\n\n"
                    "**Nice to Have**\n\n"
                    "- Exposure to Docker or containerised development\n"
                    "- Familiarity with PostgreSQL or any relational database\n"
                    "- Basic understanding of CI/CD and automated testing\n"
                    "- Any prior internship or open-source contribution"
                ),
                "category": "Engineering",
            },
            {
                "title": "Data Analyst (Entry)",
                "role_title": "Data Analyst",
                "description": (
                    "**About the Role**\n\n"
                    "We're looking for a Data Analyst who is equally comfortable writing complex SQL and "
                    "explaining a trend to a non-technical stakeholder. You'll work directly with business "
                    "teams to turn raw data into decisions.\n\n"
                    "**What You'll Do**\n\n"
                    "- Write advanced SQL queries (CTEs, window functions, multi-table joins) against PostgreSQL and MySQL\n"
                    "- Build and maintain interactive dashboards in Tableau and Power BI for business stakeholders\n"
                    "- Use Python (Pandas, NumPy) for exploratory data analysis and automating recurring reports\n"
                    "- Perform ETL pipeline work using Airflow or dbt; validate and clean data at ingestion\n"
                    "- Conduct statistical analysis and surface actionable business insights\n"
                    "- Work with Spark/PySpark for large-scale data processing tasks\n"
                    "- Present findings clearly with supporting visualisations and written commentary\n\n"
                    "**Requirements**\n\n"
                    "- Strong SQL skills — window functions, subqueries, and query optimisation\n"
                    "- Hands-on Python experience for data analysis (Pandas, NumPy)\n"
                    "- Experience building dashboards in Tableau or Power BI\n"
                    "- Proficiency with Excel including VLOOKUP, Pivot Tables, and advanced formulas\n"
                    "- Strong communication skills — able to translate data into business language\n\n"
                    "**Nice to Have**\n\n"
                    "- Experience with a cloud data warehouse (BigQuery, Redshift, or Snowflake)\n"
                    "- Familiarity with dbt or similar data transformation tools\n"
                    "- Exposure to A/B testing and statistical significance frameworks\n"
                    "- Degree in Computer Science, Statistics, Mathematics, or related field"
                ),
                "category": "Data",
            },
            {
                "title": "Frontend Developer (React)",
                "role_title": "Frontend Developer",
                "description": (
                    "**About the Role**\n\n"
                    "We're hiring a Frontend Developer to own the user-facing layer of our product. "
                    "You'll work in a cross-functional squad alongside backend engineers and designers "
                    "to deliver fast, polished, and accessible web experiences.\n\n"
                    "**What You'll Do**\n\n"
                    "- Develop and maintain responsive web interfaces using React and TypeScript\n"
                    "- Build reusable, performant component libraries and design system primitives\n"
                    "- Translate Figma designs into high-quality, pixel-accurate code\n"
                    "- Consume RESTful and GraphQL APIs; manage client-side state (Redux or Context API)\n"
                    "- Optimise frontend performance — lazy loading, code splitting, bundle size\n"
                    "- Write unit and integration tests using Jest and Cypress\n"
                    "- Ensure cross-browser and cross-device compatibility\n\n"
                    "**Requirements**\n\n"
                    "- Strong proficiency in React.js and its core principles (hooks, lifecycle, reconciliation)\n"
                    "- Solid TypeScript skills — type-safe code without fighting the compiler\n"
                    "- Good understanding of HTML5, CSS3, and responsive design\n"
                    "- Experience consuming REST APIs and handling async data flows\n"
                    "- Familiarity with Git, PR workflows, and agile development\n\n"
                    "**Nice to Have**\n\n"
                    "- Experience with Next.js or SSR/SSG patterns\n"
                    "- Familiarity with Vue or Angular\n"
                    "- Exposure to micro-frontend architecture or design systems\n"
                    "- Understanding of web accessibility (WCAG) standards"
                ),
                "category": "Engineering",
            },
            {
                "title": "Backend Developer (Node/Python)",
                "role_title": "Backend Developer",
                "description": (
                    "**About the Role**\n\n"
                    "We're hiring a Backend Developer to design, build, and scale the services that power our core platform. "
                    "You'll own APIs and microservices end-to-end — from architecture decisions to production reliability.\n\n"
                    "**What You'll Do**\n\n"
                    "- Design and build scalable RESTful APIs using Python (FastAPI/Django/Flask) or Node.js (Express/NestJS)\n"
                    "- Architect microservices and distributed systems; integrate PostgreSQL and MySQL for relational storage\n"
                    "- Use Redis or MongoDB for caching and flexible data models\n"
                    "- Containerise workloads with Docker; deploy via Kubernetes with CI/CD pipelines on AWS or GCP\n"
                    "- Implement authentication and authorisation using OAuth 2.0 and JWT\n"
                    "- Write comprehensive tests with pytest or Jest; enforce quality through code reviews\n"
                    "- Participate in architecture discussions and contribute to technical roadmap decisions\n\n"
                    "**Requirements**\n\n"
                    "- 1–3 years of hands-on backend development experience\n"
                    "- Strong Python or Node.js skills with production API development experience\n"
                    "- Solid experience with PostgreSQL and SQL query optimisation\n"
                    "- Understanding of distributed systems, async processing, and microservices patterns\n"
                    "- Familiarity with Docker and CI/CD workflows\n\n"
                    "**Nice to Have**\n\n"
                    "- Experience with Kubernetes or container orchestration\n"
                    "- Exposure to message brokers (Kafka, RabbitMQ, Redis Streams)\n"
                    "- Infrastructure-as-code experience (Terraform/Pulumi)\n"
                    "- Prior work with high-traffic, low-latency production systems"
                ),
                "category": "Engineering",
            },
            {
                "title": "Full Stack Developer",
                "role_title": "Full Stack Developer",
                "description": (
                    "**About the Role**\n\n"
                    "We're looking for a Full Stack Developer who is comfortable owning features from database schema "
                    "to React component — someone who doesn't wait to be handed a ticket and prefers to ship.\n\n"
                    "**What You'll Do**\n\n"
                    "- Build end-to-end web application features using React/Next.js on the frontend and FastAPI/Django on the backend\n"
                    "- Design and query PostgreSQL and MongoDB databases; implement caching with Redis\n"
                    "- Build and consume GraphQL and REST APIs; implement OAuth 2.0 and JWT authentication\n"
                    "- Deploy services using Docker and CI/CD pipelines on AWS\n"
                    "- Write automated tests with pytest and Jest; maintain high code coverage\n"
                    "- Participate in system design discussions and help define technical architecture\n"
                    "- Review and mentor peers through PR review processes\n\n"
                    "**Requirements**\n\n"
                    "- 1–3 years of full-stack development experience\n"
                    "- Proficiency in React (hooks, state management) and Python or Node.js for backend\n"
                    "- Solid SQL skills and experience with relational database design\n"
                    "- Working knowledge of REST API design principles\n"
                    "- Comfortable with Docker, Git, and collaborative development workflows\n\n"
                    "**Nice to Have**\n\n"
                    "- Experience with Next.js or SSR patterns\n"
                    "- Familiarity with GraphQL\n"
                    "- Exposure to cloud platforms (AWS, GCP, or Azure)\n"
                    "- Prior experience in a startup or high-ownership environment"
                ),
                "category": "Engineering",
            },
            {
                "title": "Machine Learning Engineer",
                "role_title": "ML Engineer",
                "description": (
                    "**About the Role**\n\n"
                    "We are building intelligent systems and need an ML Engineer who can take models from research "
                    "to production. You'll work across the full ML lifecycle — data, training, evaluation, deployment, and monitoring.\n\n"
                    "**What You'll Do**\n\n"
                    "- Build, train, and deploy ML and deep learning models using Python, PyTorch, TensorFlow, and scikit-learn\n"
                    "- Work with LLMs, RAG pipelines, and embeddings using LangChain, LlamaIndex, and HuggingFace Transformers\n"
                    "- Design and maintain MLOps infrastructure; orchestrate data workflows with Airflow\n"
                    "- Implement classification, regression, clustering, and anomaly detection algorithms\n"
                    "- Apply NLP, computer vision, and generative AI techniques to real product problems\n"
                    "- Deploy models to production on AWS or GCP; use Docker for reproducible environments\n"
                    "- Track and document experiments rigorously; ensure reproducibility across runs\n\n"
                    "**Requirements**\n\n"
                    "- Strong Python skills with hands-on ML model development experience\n"
                    "- Proficiency in PyTorch or TensorFlow and scikit-learn\n"
                    "- Solid understanding of ML fundamentals — bias/variance, cross-validation, evaluation metrics\n"
                    "- Experience with Pandas and NumPy for data processing\n"
                    "- Familiarity with SQL for data querying and feature extraction\n\n"
                    "**Nice to Have**\n\n"
                    "- Experience with LLMs, RAG, or vector databases (Pinecone, Weaviate, Chroma)\n"
                    "- Familiarity with MLflow or experiment tracking tools\n"
                    "- Exposure to Spark and distributed training\n"
                    "- Cloud ML platform experience (AWS SageMaker, GCP Vertex AI)"
                ),
                "category": "Data/AI",
            },
            {
                "title": "DevOps / Cloud Engineer",
                "role_title": "DevOps Engineer",
                "description": (
                    "**About the Role**\n\n"
                    "We are looking for a DevOps/Cloud Engineer to own our infrastructure and deployment pipelines. "
                    "You'll enable the engineering team to ship faster and more reliably — from CI/CD to cloud infrastructure to observability.\n\n"
                    "**What You'll Do**\n\n"
                    "- Design, build, and maintain CI/CD pipelines using GitHub Actions, GitLab CI, Jenkins, or Azure DevOps\n"
                    "- Containerise applications with Docker; orchestrate deployments on Kubernetes using Helm\n"
                    "- Provision and manage cloud infrastructure on AWS, GCP, and Azure using Terraform and Ansible\n"
                    "- Set up monitoring, alerting, and observability using Prometheus, Grafana, and Datadog\n"
                    "- Implement SRE practices — SLOs, error budgets, runbooks, incident response\n"
                    "- Automate operational tasks using Python and Bash scripting on Linux systems\n"
                    "- Apply security best practices — authentication, encryption, SSL/TLS, secrets management\n\n"
                    "**Requirements**\n\n"
                    "- Hands-on experience with Docker and Kubernetes in production\n"
                    "- Proficiency with at least one major cloud provider (AWS, GCP, or Azure)\n"
                    "- Experience writing infrastructure-as-code with Terraform or Ansible\n"
                    "- Strong Linux systems knowledge and scripting skills (Python or Bash)\n"
                    "- Familiarity with CI/CD tooling and GitOps practices\n\n"
                    "**Nice to Have**\n\n"
                    "- Experience with service meshes (Istio, Linkerd)\n"
                    "- Familiarity with SonarQube or code quality gates\n"
                    "- Multi-cloud or hybrid cloud experience\n"
                    "- Knowledge of FinOps or cloud cost optimisation"
                ),
                "category": "Engineering",
            },
            {
                "title": "UI/UX Designer",
                "role_title": "UX Designer",
                "description": (
                    "**About the Role**\n\n"
                    "We're hiring a UI/UX Designer to define how our product looks, feels, and behaves. "
                    "You'll work closely with engineers and product managers to design interfaces that are intuitive, "
                    "accessible, and delightful to use.\n\n"
                    "**What You'll Do**\n\n"
                    "- Design intuitive, accessible interfaces using Figma and design thinking methodologies\n"
                    "- Conduct user research, define personas, and map user journeys\n"
                    "- Create wireframes, interactive prototypes, and high-fidelity mockups\n"
                    "- Collaborate with React/TypeScript frontend engineers to ensure design fidelity\n"
                    "- Define and maintain a component design system and interaction pattern library\n"
                    "- Run usability tests and iterate designs based on qualitative and quantitative feedback\n"
                    "- Ensure WCAG accessibility compliance across all user-facing surfaces\n\n"
                    "**Requirements**\n\n"
                    "- Strong proficiency in Figma — components, auto layout, prototyping, and variants\n"
                    "- Solid grasp of UX principles, information architecture, and interaction design\n"
                    "- Experience conducting and synthesising user research\n"
                    "- Portfolio demonstrating shipped product work, not just mockups\n"
                    "- Ability to communicate design decisions clearly to engineers and stakeholders\n\n"
                    "**Nice to Have**\n\n"
                    "- Experience building or maintaining a design system at scale\n"
                    "- Basic front-end knowledge (HTML/CSS) to aid developer handoff\n"
                    "- Familiarity with analytics tools (Mixpanel, Hotjar) for data-driven iteration\n"
                    "- Exposure to motion design or micro-interaction design"
                ),
                "category": "Design",
            },
            {
                "title": "Cybersecurity Analyst",
                "role_title": "Security Analyst",
                "description": (
                    "**About the Role**\n\n"
                    "We are looking for a Cybersecurity Analyst to safeguard our platform, infrastructure, and user data. "
                    "You'll identify risks, design controls, and respond to threats — with a strong bias towards preventative security.\n\n"
                    "**What You'll Do**\n\n"
                    "- Identify, assess, and mitigate security vulnerabilities across web applications and cloud infrastructure\n"
                    "- Implement and review authentication/authorisation systems (OAuth 2.0, JWT, SAML, RBAC)\n"
                    "- Conduct threat modelling, security audits, and OWASP Top 10 assessments\n"
                    "- Perform penetration testing and vulnerability scanning on web apps and APIs\n"
                    "- Apply encryption, SSL/TLS configuration, and secure coding practices across services\n"
                    "- Respond to security incidents — triage, investigation, containment, and post-mortems\n"
                    "- Ensure compliance with relevant security and data privacy frameworks\n\n"
                    "**Requirements**\n\n"
                    "- Solid understanding of application security concepts and common attack vectors\n"
                    "- Experience with OWASP Top 10, threat modelling, and security code review\n"
                    "- Knowledge of authentication protocols — OAuth 2.0, JWT, SAML\n"
                    "- Familiarity with network security, TLS, and encryption fundamentals\n"
                    "- Python scripting skills for automation and tooling\n\n"
                    "**Nice to Have**\n\n"
                    "- Experience with AWS or Azure cloud security services (IAM, Security Hub, GuardDuty)\n"
                    "- Exposure to SIEM tools (Splunk, Elastic SIEM)\n"
                    "- Security certifications (CEH, OSCP, CompTIA Security+)\n"
                    "- Prior experience in bug bounty programmes or red-teaming"
                ),
                "category": "Security",
            },
            {
                "title": "Mobile Developer (React Native/Flutter)",
                "role_title": "Mobile Developer",
                "description": (
                    "**About the Role**\n\n"
                    "We're building mobile experiences used by thousands of people daily and need a Mobile Developer "
                    "who takes ownership of the app layer — from architecture to App Store submission.\n\n"
                    "**What You'll Do**\n\n"
                    "- Build and maintain cross-platform mobile applications using React Native and/or Flutter\n"
                    "- Develop native iOS features in Swift (Xcode) and native Android features in Kotlin (Android Studio) where needed\n"
                    "- Integrate RESTful APIs and backend services; handle JSON serialisation and local storage (SQLite)\n"
                    "- Implement native device features — camera, GPS, BLE, push notifications\n"
                    "- Apply MVVM or similar architecture patterns; manage application state efficiently\n"
                    "- Set up CI/CD pipelines for mobile; publish and manage releases on the App Store and Google Play\n"
                    "- Write tests, profile performance, and optimise rendering across device types\n\n"
                    "**Requirements**\n\n"
                    "- Hands-on experience shipping mobile apps with React Native or Flutter\n"
                    "- Proficiency in TypeScript (React Native) or Dart (Flutter)\n"
                    "- Experience integrating REST APIs in a mobile context\n"
                    "- Understanding of mobile app architecture patterns (MVVM, BLoC)\n"
                    "- Familiarity with Git and mobile CI/CD workflows (Fastlane, Bitrise, or similar)\n\n"
                    "**Nice to Have**\n\n"
                    "- Experience with native Swift or Kotlin development\n"
                    "- Familiarity with mobile analytics and crash reporting (Firebase, Sentry)\n"
                    "- Experience with BLE or hardware device integrations\n"
                    "- Prior App Store or Google Play submission and review experience"
                ),
                "category": "Engineering",
            },
        ]
        existing = {t.title: t for t in db.query(models.ScoringTemplate).all()}
        for row in defaults:
            if row["title"] not in existing:
                db.add(models.ScoringTemplate(**row, is_active=True, created_by=1))
            else:
                # Update description so scoring stays accurate as templates evolve
                existing[row["title"]].description = row["description"]
                existing[row["title"]].role_title = row["role_title"]

        db.commit()
    finally:
        db.close()


def seed_penalty_defaults() -> None:
    db = SessionLocal()
    try:
        existing = (
            db.query(models.PenaltyRule)
            .filter(models.PenaltyRule.recruiter_id.is_(None), models.PenaltyRule.listing_id.is_(None))
            .count()
        )
        if existing > 0:
            return

        defaults = [
            {
                "category": "backend_core",
                "label": "Backend Core",
                "keywords": "python,fastapi,django,node.js,express,api,microservices",
                "penalty_value": 2,
            },
            {
                "category": "data_storage",
                "label": "Data Storage",
                "keywords": "sql,postgresql,mysql,mongodb,redis",
                "penalty_value": 2,
            },
            {
                "category": "devops_delivery",
                "label": "Delivery & Ops",
                "keywords": "docker,kubernetes,ci/cd,github-actions,aws,gcp,azure",
                "penalty_value": 2,
            },
            {
                "category": "quality_engineering",
                "label": "Testing & Quality",
                "keywords": "pytest,jest,unittest,testing,code review",
                "penalty_value": 1,
            },
        ]

        for rule in defaults:
            db.add(
                models.PenaltyRule(
                    recruiter_id=None,
                    listing_id=None,
                    category=rule["category"],
                    label=rule["label"],
                    keywords=rule["keywords"],
                    penalty_value=rule["penalty_value"],
                    is_active=True,
                    created_by=1,
                )
            )
        db.commit()
    finally:
        db.close()


def migrate_ml_engineer_template() -> None:
    """
    Update the ML Engineer scoring template to use more discriminating language.
    Moves Docker/AWS/GCP to 'Nice to Have' and adds MLflow/Kubeflow/DVC/feature
    engineering to Requirements, so PRECISE can better distinguish ML engineers
    from backend developers who've touched LLM tooling in a course.
    Runs as a live-DB migration on every startup — idempotent via a sentinel phrase.
    """
    SENTINEL = "MLflow, Kubeflow, DVC"
    NEW_DESCRIPTION = (
        "**About the Role**\n\n"
        "We are building intelligent systems and need an ML Engineer who can take models from research "
        "to production. You'll work across the full ML lifecycle — data, training, evaluation, deployment, and monitoring.\n\n"
        "**What You'll Do**\n\n"
        "- Build, train, and deploy ML and deep learning models using Python, PyTorch, TensorFlow, and scikit-learn\n"
        "- Design and execute feature engineering pipelines; apply dimensionality reduction and feature selection\n"
        "- Implement and iterate on classification, regression, clustering, and anomaly detection algorithms\n"
        "- Work with LLMs, RAG pipelines, and embeddings using LangChain, LlamaIndex, and HuggingFace Transformers\n"
        "- Track experiments rigorously with MLflow or similar; manage model registry and reproducibility\n"
        "- Apply NLP, computer vision, and generative AI techniques to real product problems\n"
        "- Maintain MLOps infrastructure using Kubeflow or Airflow; version datasets and models with DVC\n\n"
        "**Requirements**\n\n"
        "- Strong Python skills with hands-on ML model development and experimentation experience\n"
        "- Proficiency in PyTorch or TensorFlow and scikit-learn — you train, evaluate, and iterate models\n"
        "- Solid understanding of ML fundamentals: bias/variance, cross-validation, evaluation metrics\n"
        "- Experience with experiment tracking tools (MLflow, Weights & Biases, DVC)\n"
        "- Familiarity with feature engineering, data preprocessing, and Pandas/NumPy\n"
        "- Working knowledge of SQL for data querying and feature extraction\n\n"
        "**Nice to Have**\n\n"
        "- Deployment experience: containerising models with Docker, serving on AWS SageMaker or GCP Vertex AI\n"
        "- Exposure to distributed training and Spark for large-scale data\n"
        "- Experience with Kubeflow Pipelines or MLflow model serving\n"
        "- Familiarity with vector databases (Pinecone, Weaviate, Chroma) for RAG architectures"
    )
    db = SessionLocal()
    try:
        tmpl = (
            db.query(models.ScoringTemplate)
            .filter(models.ScoringTemplate.role_title == "ML Engineer")
            .first()
        )
        if tmpl is None or (tmpl.description or "").find(SENTINEL) != -1:
            return  # Not found or already migrated
        tmpl.description = NEW_DESCRIPTION
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_admin()
    seed_scoring_defaults()
    seed_penalty_defaults()
    migrate_ml_engineer_template()
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

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
