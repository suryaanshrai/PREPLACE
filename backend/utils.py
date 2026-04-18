import os
from google import genai
import pdfplumber
import time
import re
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def extract_text_from_pdf(file_path: str) -> str:
    text = ""

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

    return text


# ═══════════════════════════════════════════════════════════════════
# KEYWORD PENALTY MODEL
# Scans resume text for important technical keywords.
# Missing keywords incur a penalty. Final Score = Gemini Score - Penalty
# ═══════════════════════════════════════════════════════════════════

# Keywords grouped by category with their penalty weight if MISSING
KEYWORD_CATEGORIES = {
    "version_control": {
        "keywords": ["git", "github", "gitlab", "bitbucket", "version control"],
        "penalty": 3,       # Missing version control = -3
        "label": "Version Control (Git/GitHub)",
    },
    "coding_practice": {
        "keywords": ["leetcode", "codeforces", "codechef", "hackerrank", "competitive programming", "hackerearth"],
        "penalty": 2,
        "label": "Competitive Programming Platforms",
    },
    "projects": {
        "keywords": ["project", "built", "developed", "implemented", "created", "designed"],
        "penalty": 4,       # No projects mentioned = -4
        "label": "Projects / Hands-On Work",
    },
    "programming_languages": {
        "keywords": ["python", "java", "javascript", "c++", "c#", "typescript", "golang", "rust", "kotlin", "swift"],
        "penalty": 3,       # No programming language = -3
        "label": "Programming Languages",
    },
    "web_technologies": {
        "keywords": ["react", "angular", "vue", "node", "express", "django", "flask", "fastapi", "spring", "html", "css"],
        "penalty": 2,
        "label": "Web Technologies/Frameworks",
    },
    "databases": {
        "keywords": ["sql", "mysql", "postgresql", "mongodb", "redis", "firebase", "database"],
        "penalty": 2,
        "label": "Databases",
    },
    "cloud_devops": {
        "keywords": ["aws", "azure", "gcp", "docker", "kubernetes", "k8s", "ci/cd", "jenkins", "devops", "cloud"],
        "penalty": 1,
        "label": "Cloud / DevOps",
    },
    "data_ml": {
        "keywords": ["machine learning", "ml", "deep learning", "tensorflow", "pytorch", "pandas", "numpy", "data science", "nlp", "ai"],
        "penalty": 1,
        "label": "Data Science / ML",
    },
    "soft_skills": {
        "keywords": ["leadership", "teamwork", "communication", "problem solving", "collaboration", "management"],
        "penalty": 1,
        "label": "Soft Skills",
    },
    "certifications": {
        "keywords": ["certificate", "certified", "certification", "coursera", "udemy", "edx", "nptel"],
        "penalty": 1,
        "label": "Certifications / Online Learning",
    },
    "internship_experience": {
        "keywords": ["intern", "internship", "experience", "worked at", "employed", "company"],
        "penalty": 2,
        "label": "Internship / Work Experience",
    },
}


def compute_keyword_penalty(resume_text: str) -> dict:
    """
    Scans resume text for important keywords.
    Returns:
        {
            "total_penalty": int,
            "missing": [{"category": str, "label": str, "penalty": int}, ...],
            "found": [{"category": str, "label": str}, ...],
            "details": str   # Human-readable summary
        }
    """
    if not resume_text:
        return {"total_penalty": 0, "missing": [], "found": [], "details": "No text to scan."}

    lower_text = resume_text.lower()
    total_penalty = 0
    missing = []
    found = []

    for cat_id, cat in KEYWORD_CATEGORIES.items():
        # Check if ANY keyword from this category exists in the resume
        has_keyword = any(kw in lower_text for kw in cat["keywords"])

        if has_keyword:
            found.append({"category": cat_id, "label": cat["label"]})
        else:
            total_penalty += cat["penalty"]
            missing.append({
                "category": cat_id,
                "label": cat["label"],
                "penalty": cat["penalty"],
            })

    # Build details string
    lines = []
    if missing:
        lines.append("Missing Keywords (penalties applied):")
        for m in missing:
            lines.append(f"  - {m['label']}: -{m['penalty']} pts")
    if found:
        lines.append(f"\nKeywords Found ({len(found)}/{len(KEYWORD_CATEGORIES)} categories):")
        for f_ in found:
            lines.append(f"  ✓ {f_['label']}")
    lines.append(f"\nTotal Penalty: -{total_penalty} pts")

    return {
        "total_penalty": total_penalty,
        "missing": missing,
        "found": found,
        "details": "\n".join(lines),
    }


def compute_final_score(gemini_score: int, resume_text: str) -> dict:
    """
    Final Score = max(Gemini Score - Keyword Penalty, 1)
    Returns full breakdown for display.
    """
    penalty_result = compute_keyword_penalty(resume_text)
    penalty = penalty_result["total_penalty"]
    raw = gemini_score or 0
    final = max(raw - penalty, 1)  # Never go below 1

    return {
        "gemini_score": raw,
        "penalty": penalty,
        "final_score": final,
        "penalty_details": penalty_result["details"],
        "missing_keywords": penalty_result["missing"],
        "found_keywords": penalty_result["found"],
    }


def extract_skills_from_analysis(analysis_text: str) -> list:
    """Extract skill-like keywords from AI analysis text."""
    if not analysis_text:
        return []
    skill_pool = [
        'python', 'java', 'javascript', 'c++', 'c#', 'react', 'node', 'nodejs',
        'sql', 'mysql', 'postgresql', 'mongodb', 'html', 'css', 'typescript',
        'docker', 'kubernetes', 'k8s', 'aws', 'azure', 'gcp', 'git', 'linux',
        'machine learning', 'ml', 'deep learning', 'nlp', 'tensorflow', 'pytorch',
        'data science', 'data analysis', 'statistics', 'pandas', 'numpy',
        'flask', 'django', 'fastapi', 'spring', 'angular', 'vue',
        'devops', 'ci/cd', 'rest', 'api', 'microservices',
        'algorithms', 'dsa', 'data structures', 'oop',
        'figma', 'ui/ux', 'design', 'product management',
        'excel', 'tableau', 'power bi', 'analytics',
        'communication', 'leadership', 'teamwork', 'problem solving',
        'leetcode', 'codeforces', 'codechef', 'hackerrank', 'github',
    ]
    lower = analysis_text.lower()
    return [s for s in skill_pool if s in lower]


def analyze_resume(text: str):
    if not text.strip():
        return "Could not extract text from resume"

    if client is None:
        return "AI service unavailable: GEMINI_API_KEY not configured."

    prompt = f"""
You are an expert ATS (Applicant Tracking System) and senior technical recruiter.

Your task is to evaluate the following resume with STRICT, REALISTIC, and CRITICAL judgment.

SCORING GUIDELINES:
- 50–65 → Below average (weak, generic, or lacks clarity)
- 65–75 → Average (basic but lacks impact or specificity)
- 75–85 → Good (clear, relevant, some measurable impact)
- 85–92 → Strong (well-structured, impactful, quantified)
- 92–97 → Excellent (highly competitive, strong achievements)
- 97–100 → Rare top-tier (exceptional, near perfect)

IMPORTANT RULES:
- Be HARSH but fair (avoid inflated scores)
- Do NOT give similar resumes the same score unless truly identical
- Penalize vague statements like "worked on", "helped with"
- Reward quantified impact (%, numbers, metrics)
- Reward clarity, structure, and relevance
- Penalize grammar issues, redundancy, or poor formatting
- Penalize lack of projects, internships, or real-world experience
- Consider ATS readability (keywords, formatting, sections)

EVALUATION CRITERIA:
1. Content Quality (depth, relevance)
2. Impact & Achievements (quantified results)
3. Clarity & Structure (readability, organization)
4. Skills & Keywords (ATS optimization)
5. Experience/Projects Quality

OUTPUT FORMAT (STRICT — DO NOT DEVIATE):

Score: <integer between 1-100>

Strong Points:
- <short, specific strength>
- <short, specific strength>
- <short, specific strength>

Improvements:
- <clear, actionable improvement>
- <clear, actionable improvement>
- <clear, actionable improvement>

CONSTRAINTS:
- Max 5 points per section
- Each point must be under 12 words
- No paragraphs
- No explanations outside sections
- No extra headings
- No markdown formatting
- Do NOT repeat points
- Keep feedback concise and actionable

Suggested Role: <single best-fit job role like "SDE Intern", "Data Scientist", "ML Engineer", "Frontend Developer", "Backend Developer", "Full-Stack Developer", "DevOps Engineer", "Product Manager", "Business Analyst", "UI/UX Designer" based on resume content>

Resume:
{text[:3000]}
"""

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]

    for model_name in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                print("REAL ERROR:", e)
                if "503" in str(e):
                    time.sleep(2)
                else:
                    break
       
    return "AI service overloaded. Try again later."

