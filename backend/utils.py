import os
import json
from google import genai
import pdfplumber
import time
import re
from typing import Any
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
        # Use word-boundary matching so short keywords like "ml", "ai", "sql"
        # don't fire on partial matches inside longer words (e.g. "email" for "ml").
        has_keyword = any(
            re.search(r"\b" + re.escape(kw) + r"\b", lower_text)
            for kw in cat["keywords"]
        )

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

    from google.genai.errors import ClientError, ServerError

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
                if response.text:
                    return response.text
                break
            except ClientError as e:
                if e.code == 429:
                    # Quota exhausted — try next model, no point retrying this one
                    break
                if e.code in (400, 401, 403):
                    return "AI service unavailable: API key is invalid or has been revoked."
                break
            except ServerError:
                # 503 overloaded — retry once, then move to next model
                if attempt == 0:
                    time.sleep(2)
            except Exception as e:
                print("REAL ERROR:", e)
                break

    return "AI quota exceeded or service unavailable. Your resume was saved — please try again shortly."


# ═══════════════════════════════════════════════════════════════════
# LINKEDIN SEARCH PARAMETER EXTRACTION
# Prompts Gemini to derive job search parameters from a resume so we
# can surface relevant LinkedIn job recommendations.
# ═══════════════════════════════════════════════════════════════════

_EXPERIENCE_LEVELS = {"internship", "entry level", "associate", "senior", "director", "executive"}
_JOB_TYPES = {"full time", "part time", "contract", "temporary", "volunteer", "internship"}
_REMOTE_FILTERS = {"on-site", "on site", "remote", "hybrid"}
_MAX_ADJACENT_KEYWORDS = 7


def _normalize_keyword(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())[:80]


def _dedupe_keywords(candidates: list[str], primary: str = "", limit: int = 5) -> list[str]:
    seen = set()
    out = []
    primary_lower = (primary or "").strip().lower()
    for candidate in candidates:
        kw = _normalize_keyword(candidate)
        if not kw:
            continue
        lower = kw.lower()
        if lower == primary_lower or lower in seen:
            continue
        seen.add(lower)
        out.append(kw)
        if len(out) >= max(1, min(limit, _MAX_ADJACENT_KEYWORDS)):
            break
    return out


def _extract_suggested_role(analysis_text: str) -> str:
    if not analysis_text:
        return ""
    role_match = re.search(r"Suggested Role:\s*(.+)", analysis_text, re.IGNORECASE)
    if role_match:
        return _normalize_keyword(role_match.group(1).rstrip("."))
    return ""


def _fallback_linkedin_keywords(resume_text: str, analysis_text: str) -> tuple[str, list[str]]:
    """Build deterministic role-centric keyword fallbacks when LLM output is unavailable."""
    primary = _extract_suggested_role(analysis_text)
    lowered = f"{analysis_text}\n{resume_text}".lower()

    if not primary:
        role_rules = [
            ("backend", "Backend Developer"),
            ("fastapi", "Backend Developer"),
            ("django", "Backend Developer"),
            ("flask", "Backend Developer"),
            ("react", "Frontend Developer"),
            ("frontend", "Frontend Developer"),
            ("ui", "UI/UX Designer"),
            ("ux", "UI/UX Designer"),
            ("data analyst", "Data Analyst"),
            ("machine learning", "ML Engineer"),
            ("devops", "DevOps Engineer"),
            ("product", "Product Manager"),
        ]
        for token, role in role_rules:
            if token in lowered:
                primary = role
                break

    if not primary:
        primary = "Software Engineer"

    adjacency_map = {
        "backend developer": ["Backend Engineer", "Python Developer", "API Developer", "Software Engineer"],
        "frontend developer": ["Frontend Engineer", "React Developer", "UI Developer", "Software Engineer"],
        "full-stack developer": ["Full Stack Engineer", "Software Engineer", "Backend Developer", "Frontend Developer"],
        "data analyst": ["Business Analyst", "Data Associate", "Analytics Engineer", "Junior Data Analyst"],
        "ml engineer": ["Machine Learning Engineer", "Data Scientist", "AI Engineer", "NLP Engineer"],
        "devops engineer": ["Site Reliability Engineer", "Platform Engineer", "Cloud Engineer", "Infrastructure Engineer"],
        "ui/ux designer": ["Product Designer", "UX Designer", "UI Designer", "Visual Designer"],
        "software engineer": ["Software Developer", "Backend Developer", "Full Stack Developer", "Application Engineer"],
    }

    adjacent = adjacency_map.get(primary.lower(), ["Software Engineer", "Backend Developer", "Frontend Developer"])
    return primary, _dedupe_keywords(adjacent, primary=primary, limit=5)


def get_linkedin_search_params(resume_text: str, analysis_text: str = "") -> dict:
    """
    Uses Gemini to extract LinkedIn job search parameters from a resume.
    Returns a dict with keys: keyword, location, experienceLevel, jobType, remoteFilter.
    Falls back to safe defaults if Gemini is unavailable or returns unparseable output.
    """
    fallback_keyword, fallback_adjacent = _fallback_linkedin_keywords(resume_text, analysis_text)
    defaults = {
        "keyword": fallback_keyword,
        "location": "",
        "experienceLevel": "entry level",
        "jobType": "",
        "remoteFilter": "",
        "adjacentKeywords": fallback_adjacent,
    }

    if client is None:
        return defaults

    context = f"Resume text (truncated):\n{resume_text[:2500]}"
    if analysis_text and analysis_text.strip():
        context += f"\n\nAI Analysis:\n{analysis_text[:800]}"

    prompt = f"""You are a job search assistant. Based on the following resume, extract the best LinkedIn job search parameters.

{context}

Return ONLY a valid JSON object with these exact keys (no markdown, no explanation):
- "keyword": a concise job title or skill keyword (e.g. "Software Engineer", "Data Analyst", "React Developer")
- "adjacentKeywords": an array of 3-7 closely related role keywords; keep in same role family and avoid unrelated domains
- "location": the candidate's city/country if mentioned, otherwise empty string
- "experienceLevel": one of: internship, entry level, associate, senior, director, executive
- "jobType": one of: full time, part time, contract, temporary, volunteer, internship — or empty string
- "remoteFilter": one of: on-site, remote, hybrid — or empty string

JSON output only:"""

    from google.genai.errors import ClientError, ServerError

    models_to_try = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

    for model_name in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                raw = response.text or ""
                # Strip possible markdown code fences
                raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
                parsed = json.loads(raw)

                result = dict(defaults)
                result["keyword"] = _normalize_keyword(str(parsed.get("keyword", ""))) or fallback_keyword
                result["location"] = str(parsed.get("location", "")).strip()[:100]

                raw_adjacent = parsed.get("adjacentKeywords", parsed.get("adjacent_keywords", []))
                if isinstance(raw_adjacent, list):
                    result["adjacentKeywords"] = _dedupe_keywords(
                        [str(item) for item in raw_adjacent],
                        primary=result["keyword"],
                        limit=5,
                    )
                else:
                    result["adjacentKeywords"] = list(fallback_adjacent)

                exp = str(parsed.get("experienceLevel", "")).strip().lower()
                if exp in _EXPERIENCE_LEVELS:
                    result["experienceLevel"] = exp

                jt = str(parsed.get("jobType", "")).strip().lower()
                if jt in _JOB_TYPES:
                    result["jobType"] = jt

                rf = str(parsed.get("remoteFilter", "")).strip().lower()
                if rf in _REMOTE_FILTERS:
                    result["remoteFilter"] = rf

                return result
            except ClientError as e:
                if e.code == 429:
                    break  # Quota exhausted — try next model
                break  # 400/401/403 or other client error — bail entirely
            except ServerError:
                if attempt == 0:
                    time.sleep(2)
            except Exception:
                break

    return defaults


def _clean_json_text(raw: str) -> str:
    """Strip code fences so model output can be safely parsed as JSON."""
    cleaned = re.sub(r"```(?:json)?", "", raw or "")
    return cleaned.strip().strip("`").strip()


def _fallback_resume_insights(
    resume_text: str,
    role_mode: str,
    target_role: str,
    suggested_role: str,
    note: str,
) -> dict[str, Any]:
    """Return deterministic guidance when LLM output is unavailable."""
    lowered = (resume_text or "").lower()
    has_projects = any(k in lowered for k in ["project", "built", "developed", "implemented"])
    has_metrics = bool(re.search(r"\b\d+\s*[%x]|\b\d{2,}\b", lowered))
    has_keywords = any(k in lowered for k in ["python", "java", "react", "sql", "aws", "docker"])

    resolved_role = (target_role or suggested_role or "General Role").strip()
    mode = "targeted" if role_mode == "targeted" else "general"

    sections = [
        {
            "title": "Role Alignment",
            "summary": f"Guidance tuned for {resolved_role} in {mode} mode.",
            "insights": [
                "Resume should mirror the role title and primary competency keywords.",
                "Top skills should appear in summary, experience, and projects sections.",
            ],
            "actionable_steps": [
                f"Add a role-focused headline aligned to {resolved_role}.",
                "Reorder bullets so role-relevant work appears first.",
            ],
        },
        {
            "title": "Experience Impact",
            "summary": "Stronger impact statements improve recruiter confidence.",
            "insights": [
                "Quantified outcomes are easier to trust than task-only bullets.",
                "Action-result format improves readability and ATS relevance.",
            ],
            "actionable_steps": [
                "Rewrite each bullet as action + scope + measurable outcome.",
                "Include delivery metrics such as latency, cost, quality, or growth.",
            ],
        },
        {
            "title": "Skills Coverage",
            "summary": "Coverage across core tools should be explicit and current.",
            "insights": [
                "Missing tool keywords can reduce shortlist probability.",
                "Skill-to-project mapping helps prove depth, not just familiarity.",
            ],
            "actionable_steps": [
                "Map each listed skill to at least one project or work bullet.",
                "Keep the skills section concise and grouped by domain.",
            ],
        },
        {
            "title": "ATS Readability",
            "summary": "Formatting consistency prevents parser drop-offs.",
            "insights": [
                "Simple formatting helps ATS systems parse sections reliably.",
                "Keyword stuffing hurts readability and can weaken human review.",
            ],
            "actionable_steps": [
                "Use clear section headings and consistent date/location formatting.",
                "Remove decorative icons/tables that can break text extraction.",
            ],
        },
    ]

    # Small deterministic personalization from resume content.
    if not has_projects:
        sections[1]["insights"].append("Projects appear underrepresented for role readiness.")
        sections[1]["actionable_steps"].append("Add 2 project entries with stack, scope, and outcomes.")
    if not has_metrics:
        sections[1]["insights"].append("Most bullets may be descriptive without measurable impact.")
        sections[1]["actionable_steps"].append("Add at least one metric to each experience/project section.")
    if not has_keywords:
        sections[2]["insights"].append("Core technical keywords are currently sparse.")
        sections[2]["actionable_steps"].append("Add concrete tools used in coursework/projects/work.")

    action_plan = [
        {
            "priority": "high",
            "step": "Align resume headline and summary to the target role.",
            "why_it_matters": "Improves role relevance in first-pass screening.",
            "timeframe": "30-45 minutes",
        },
        {
            "priority": "high",
            "step": "Convert bullets into quantified impact statements.",
            "why_it_matters": "Demonstrates ownership and measurable outcomes.",
            "timeframe": "1-2 hours",
        },
        {
            "priority": "medium",
            "step": "Map each key skill to proof in project/experience bullets.",
            "why_it_matters": "Reduces skill-claim ambiguity for recruiters.",
            "timeframe": "45-60 minutes",
        },
        {
            "priority": "medium",
            "step": "Clean ATS formatting and heading consistency.",
            "why_it_matters": "Improves parser success and scan speed.",
            "timeframe": "30 minutes",
        },
    ]

    return {
        "headline": f"Actionable insights for {resolved_role}",
        "role_mode": mode,
        "target_role": resolved_role,
        "sections": sections,
        "action_plan": action_plan,
        "source": "fallback",
        "note": note,
    }


def _normalize_resume_insights(parsed: dict[str, Any], role_mode: str, target_role: str, suggested_role: str) -> dict[str, Any]:
    """Normalize model output to a predictable contract for the frontend."""
    resolved_role = (target_role or suggested_role or "General Role").strip()
    mode = "targeted" if role_mode == "targeted" else "general"

    headline = str(parsed.get("headline", "")).strip() or f"Actionable insights for {resolved_role}"

    sections_raw = parsed.get("sections", [])
    sections: list[dict[str, Any]] = []
    if isinstance(sections_raw, list):
        for item in sections_raw[:6]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip() or "Insights"
            summary = str(item.get("summary", "")).strip()
            insights = item.get("insights", [])
            action_steps = item.get("actionable_steps", [])

            if not isinstance(insights, list):
                insights = [str(insights)] if insights else []
            if not isinstance(action_steps, list):
                action_steps = [str(action_steps)] if action_steps else []

            insights = [str(x).strip() for x in insights if str(x).strip()][:5]
            action_steps = [str(x).strip() for x in action_steps if str(x).strip()][:5]
            sections.append(
                {
                    "title": title,
                    "summary": summary,
                    "insights": insights,
                    "actionable_steps": action_steps,
                }
            )

    action_plan_raw = parsed.get("action_plan", [])
    action_plan: list[dict[str, str]] = []
    if isinstance(action_plan_raw, list):
        for item in action_plan_raw[:8]:
            if not isinstance(item, dict):
                continue
            priority = str(item.get("priority", "medium")).strip().lower()
            if priority not in {"high", "medium", "low"}:
                priority = "medium"
            step = str(item.get("step", "")).strip()
            why = str(item.get("why_it_matters", "")).strip()
            timeframe = str(item.get("timeframe", "")).strip()
            if step:
                action_plan.append(
                    {
                        "priority": priority,
                        "step": step,
                        "why_it_matters": why,
                        "timeframe": timeframe,
                    }
                )

    if not sections or not action_plan:
        return _fallback_resume_insights(
            resume_text="",
            role_mode=mode,
            target_role=resolved_role,
            suggested_role=suggested_role,
            note="LLM output was incomplete. Returned deterministic guidance.",
        )

    return {
        "headline": headline,
        "role_mode": mode,
        "target_role": resolved_role,
        "sections": sections,
        "action_plan": action_plan,
        "source": "llm",
        "note": "",
    }


def generate_resume_insights(
    resume_text: str,
    role_mode: str = "general",
    target_role: str = "",
    suggested_role: str = "",
) -> dict[str, Any]:
    """Generate structured, actionable resume insights independent of score computation."""
    mode = "targeted" if role_mode == "targeted" else "general"
    resolved_role = (target_role or suggested_role or "General Role").strip()

    if not (resume_text or "").strip():
        return _fallback_resume_insights(
            resume_text=resume_text,
            role_mode=mode,
            target_role=resolved_role,
            suggested_role=suggested_role,
            note="No resume text available for insights.",
        )

    if client is None:
        return _fallback_resume_insights(
            resume_text=resume_text,
            role_mode=mode,
            target_role=resolved_role,
            suggested_role=suggested_role,
            note="LLM service unavailable. Configure GEMINI_API_KEY to enable AI insights.",
        )

    prompt = f"""
You are a senior resume reviewer and hiring coach.

Task:
Generate role-aware resume insights with targeted sections and practical actions.

Mode: {mode}
Target role: {resolved_role}

Rules:
- Return ONLY valid JSON.
- Do not include markdown, code fences, or commentary.
- Keep language concise and actionable.
- Every section must include both insight bullets and action steps.
- Prioritize actions by impact.

Required JSON shape:
{{
  "headline": "short title",
  "sections": [
    {{
      "title": "Role Alignment",
      "summary": "one sentence",
      "insights": ["...", "..."],
      "actionable_steps": ["...", "..."]
    }}
  ],
  "action_plan": [
    {{
      "priority": "high|medium|low",
      "step": "specific task",
      "why_it_matters": "short reason",
      "timeframe": "estimated effort/time"
    }}
  ]
}}

Resume text:
{resume_text[:4000]}
"""

    from google.genai.errors import ClientError, ServerError

    models_to_try = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    for model_name in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                raw = _clean_json_text(response.text or "")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("LLM output is not a JSON object")
                return _normalize_resume_insights(parsed, mode, resolved_role, suggested_role)
            except (json.JSONDecodeError, ValueError):
                break
            except ClientError as e:
                if e.code == 429:
                    break
                if e.code in (400, 401, 403):
                    return _fallback_resume_insights(
                        resume_text=resume_text,
                        role_mode=mode,
                        target_role=resolved_role,
                        suggested_role=suggested_role,
                        note="LLM request was rejected. Check API key or model access.",
                    )
                break
            except ServerError:
                if attempt == 0:
                    time.sleep(2)
            except Exception:
                break

    return _fallback_resume_insights(
        resume_text=resume_text,
        role_mode=mode,
        target_role=resolved_role,
        suggested_role=suggested_role,
        note="LLM unavailable or returned malformed output. Returned deterministic guidance.",
    )

