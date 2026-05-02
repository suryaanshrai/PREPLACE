import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body

import models
import schemas
from matching import compute_job_match
from utils import get_linkedin_search_params, extract_skills_from_analysis
from .common import get_db, get_latest_resume, get_user_or_404

router = APIRouter()

CACHE_TTL_MINUTES = 60
LINKEDIN_WORKER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "linkedin_worker")
MIN_BALANCED_MATCH_SCORE = 30
DEFAULT_QUERY_LIMIT = 10
MAX_QUERY_LIMIT = 25
MAX_ADJACENT_KEYWORDS = 7

_EXPERIENCE_LEVELS = {"internship", "entry level", "associate", "senior", "director", "executive"}
_JOB_TYPES = {"full time", "part time", "contract", "temporary", "volunteer", "internship"}
_REMOTE_FILTERS = {"on-site", "on site", "remote", "hybrid"}


def _run_linkedin_search(params: dict) -> dict:
    """Spawn a Node.js subprocess to query LinkedIn. Returns parsed result dict."""
    try:
        result = subprocess.run(
            ["node", "search.js", json.dumps(params)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=LINKEDIN_WORKER_DIR,
        )
        stdout = result.stdout.strip()
        if not stdout:
            stderr = result.stderr.strip()[:300]
            return {"jobs": [], "error": f"Worker produced no output. stderr: {stderr}"}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # Safety net: if any stray text prefixed the JSON, find the last {...} block
            import re as _re
            m = _re.search(r'(\{.*\})\s*$', stdout, _re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
            stderr = result.stderr.strip()[:200]
            return {"jobs": [], "error": f"Worker returned invalid JSON. stderr: {stderr}"}
    except subprocess.TimeoutExpired:
        return {"jobs": [], "error": "LinkedIn search timed out (30s)."}
    except FileNotFoundError:
        return {"jobs": [], "error": "Node.js not found. Ensure Node.js is installed and on PATH."}
    except Exception as exc:
        return {"jobs": [], "error": str(exc)}


def _build_response(cache: models.LinkedInCache) -> dict:
    try:
        jobs = json.loads(cache.results_json or "[]")
    except Exception:
        jobs = []
    try:
        search_params = json.loads(cache.search_params_json or "{}")
    except Exception:
        search_params = {}
    meta = search_params.pop("_meta", {}) if isinstance(search_params, dict) else {}
    return {
        "jobs": jobs,
        "search_params": search_params,
        "cached_at": cache.cached_at.isoformat() if cache.cached_at else None,
        "expires_at": cache.expires_at.isoformat() if cache.expires_at else None,
        "from_cache": True,
        "total_fetched": int(meta.get("total_fetched", len(jobs))),
        "total_after_filter": int(meta.get("total_after_filter", len(jobs))),
        "keywords_used": meta.get("keywords_used", []),
        "filter_mode": meta.get("filter_mode", "balanced"),
        **({"filter_warning": meta["filter_warning"]} if meta.get("filter_warning") else {}),
        **({"rate_limit_warning": meta["rate_limit_warning"]} if meta.get("rate_limit_warning") else {}),
    }


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _dedupe_keywords(candidates: list[str], primary: str = "") -> list[str]:
    seen = set()
    out = []
    primary_lower = (primary or "").strip().lower()
    for candidate in candidates:
        keyword = _clean_text(str(candidate))[:80]
        if not keyword:
            continue
        lower = keyword.lower()
        if lower == primary_lower or lower in seen:
            continue
        seen.add(lower)
        out.append(keyword)
        if len(out) >= MAX_ADJACENT_KEYWORDS:
            break
    return out


def _clamp_limit(value: Optional[int]) -> int:
    if value is None:
        return DEFAULT_QUERY_LIMIT
    return max(1, min(MAX_QUERY_LIMIT, int(value)))


def _normalize_search_params(raw: dict) -> dict:
    keyword = _clean_text(str(raw.get("keyword", "")))[:100]
    location = _clean_text(str(raw.get("location", "")))[:100]
    exp = _clean_text(str(raw.get("experienceLevel", "")).lower())
    if exp not in _EXPERIENCE_LEVELS:
        exp = "entry level"

    job_type = _clean_text(str(raw.get("jobType", "")).lower())
    if job_type not in _JOB_TYPES:
        job_type = ""

    remote = _clean_text(str(raw.get("remoteFilter", "")).lower())
    if remote == "on site":
        remote = "on-site"
    if remote not in _REMOTE_FILTERS:
        remote = ""

    raw_adjacent = raw.get("adjacentKeywords", [])
    adjacent = raw_adjacent if isinstance(raw_adjacent, list) else []

    return {
        "keyword": keyword,
        "location": location,
        "experienceLevel": exp,
        "jobType": job_type,
        "remoteFilter": remote,
        "limit": _clamp_limit(raw.get("limit")),
        "adjacentKeywords": _dedupe_keywords([str(x) for x in adjacent], primary=keyword),
    }


def _collect_overrides(
    keyword: Optional[str],
    location: Optional[str],
    experience_level: Optional[str],
    job_type: Optional[str],
    remote_filter: Optional[str],
    limit: Optional[int],
    include_adjacent_keywords: Optional[bool],
    payload: Optional[schemas.LinkedInSearchOverrides],
) -> dict:
    payload_data = payload.dict(exclude_none=True) if payload else {}
    query_data = {
        "keyword": keyword,
        "location": location,
        "experienceLevel": experience_level,
        "jobType": job_type,
        "remoteFilter": remote_filter,
        "limit": limit,
        "include_adjacent_keywords": include_adjacent_keywords,
    }
    for key, value in query_data.items():
        if value is not None:
            payload_data[key] = value
    return payload_data


def _has_meaningful_overrides(overrides: dict) -> bool:
    if not overrides:
        return False
    for key, value in overrides.items():
        if key == "include_adjacent_keywords":
            if value is False:
                return True
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False


def _merge_search_params(base_params: dict, overrides: dict) -> tuple[dict, bool, bool]:
    merged = _normalize_search_params(base_params or {})
    explicit_location = False

    if "keyword" in overrides and overrides.get("keyword") is not None:
        candidate = _clean_text(str(overrides.get("keyword")))
        if candidate:
            merged["keyword"] = candidate[:100]

    if "location" in overrides and overrides.get("location") is not None:
        candidate = _clean_text(str(overrides.get("location")))
        merged["location"] = candidate[:100]
        explicit_location = bool(candidate)

    if "experienceLevel" in overrides and overrides.get("experienceLevel") is not None:
        exp = _clean_text(str(overrides.get("experienceLevel")).lower())
        if exp in _EXPERIENCE_LEVELS:
            merged["experienceLevel"] = exp

    if "jobType" in overrides and overrides.get("jobType") is not None:
        jt = _clean_text(str(overrides.get("jobType")).lower())
        if jt in _JOB_TYPES:
            merged["jobType"] = jt

    if "remoteFilter" in overrides and overrides.get("remoteFilter") is not None:
        rf = _clean_text(str(overrides.get("remoteFilter")).lower())
        if rf == "on site":
            rf = "on-site"
        if rf in _REMOTE_FILTERS:
            merged["remoteFilter"] = rf

    if "limit" in overrides and overrides.get("limit") is not None:
        merged["limit"] = _clamp_limit(int(overrides.get("limit")))

    if "adjacentKeywords" in overrides and isinstance(overrides.get("adjacentKeywords"), list):
        merged["adjacentKeywords"] = _dedupe_keywords(
            [str(x) for x in overrides.get("adjacentKeywords", [])],
            primary=merged.get("keyword", ""),
        )

    include_adjacent_keywords = bool(overrides.get("include_adjacent_keywords", True))
    if not include_adjacent_keywords:
        merged["adjacentKeywords"] = []

    merged["adjacentKeywords"] = _dedupe_keywords(merged.get("adjacentKeywords", []), primary=merged.get("keyword", ""))
    return merged, explicit_location, include_adjacent_keywords


def _keyword_sequence(search_params: dict, include_adjacent_keywords: bool) -> list[str]:
    primary = _clean_text(search_params.get("keyword", "")) or "Software Engineer"
    keywords = [primary]
    if include_adjacent_keywords:
        keywords.extend(_dedupe_keywords(search_params.get("adjacentKeywords", []), primary=primary))
    return keywords


def _job_identity_key(job: dict) -> str:
    job_url = _clean_text(str(job.get("jobUrl", ""))).lower()
    if job_url:
        return f"url::{job_url}"
    position = _clean_text(str(job.get("position", ""))).lower()
    company = _clean_text(str(job.get("company", ""))).lower()
    location = _clean_text(str(job.get("location", ""))).lower()
    return f"meta::{position}|{company}|{location}"


def _dedupe_jobs(jobs: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        key = _job_identity_key(job)
        if key in seen:
            continue
        seen.add(key)
        out.append(job)
    return out


def _location_matches(expected_location: str, job_location: str) -> bool:
    expected = _clean_text(expected_location).lower()
    actual = _clean_text(job_location).lower()
    if not expected or not actual:
        return True
    return expected in actual or actual in expected


def _has_role_overlap(applicant_role: str, job_role: str) -> bool:
    app_words = set(_clean_text(applicant_role).lower().split())
    job_words = set(_clean_text(job_role).lower().split())
    filler = {"intern", "senior", "junior", "lead", "associate", "the", "a", "an", "for"}
    app_clean = app_words - filler
    job_clean = job_words - filler
    if not app_clean or not job_clean:
        return False
    return bool(app_clean & job_clean)


def _score_and_filter_jobs(
    jobs: list[dict],
    resume,
    search_params: dict,
    explicit_location: bool,
    min_score: int = MIN_BALANCED_MATCH_SCORE,
) -> list[dict]:
    applicant_role_fallback = (resume.suggested_role or "").strip()
    keyword_fallback = _clean_text(search_params.get("keyword", ""))
    applicant_score = int(resume.score or 0)
    applicant_skills = extract_skills_from_analysis(resume.analysis or "")
    search_location = _clean_text(search_params.get("location", ""))

    filtered = []
    for job in jobs:
        if explicit_location and search_location and not _location_matches(search_location, job.get("location", "")):
            continue

        job_text = " ".join(
            [
                str(job.get("position", "")),
                str(job.get("company", "")),
                str(job.get("location", "")),
                str(job.get("description", "")),
            ]
        ).lower()
        matched_skills = [skill for skill in applicant_skills if skill.lower() in job_text]
        effective_role = _clean_text(str(job.get("search_keyword", ""))) or keyword_fallback or applicant_role_fallback
        job_role = str(job.get("position", ""))

        # Keep results relevant even with lower score threshold.
        if not _has_role_overlap(effective_role, job_role) and not matched_skills:
            continue

        relevance_score = compute_job_match(
            applicant_role=effective_role,
            applicant_skills=applicant_skills,
            applicant_score=applicant_score,
            job_role=job_role,
            job_skills_str=",".join(matched_skills),
            job_min_score=0,
            job_department=str(job.get("company", "")),
        )
        if relevance_score < min_score:
            continue

        enriched = dict(job)
        enriched["relevance_score"] = relevance_score
        if matched_skills:
            enriched["matched_skills"] = matched_skills[:8]
        filtered.append(enriched)

    filtered.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
    return filtered


def _fetch_and_cache(user_id: int, db, overrides: Optional[dict] = None, persist_cache: bool = True) -> dict:
    """Get active resume → Gemini → Node subprocess → upsert cache → return result."""
    resume = get_latest_resume(db, user_id)
    if not resume:
        raise HTTPException(status_code=404, detail="No resume found. Upload a resume first.")

    search_params = get_linkedin_search_params(
        resume_text=resume.parsed_text or "",
        analysis_text=resume.analysis or "",
    )
    overrides = overrides or {}
    effective_params, explicit_location, include_adjacent_keywords = _merge_search_params(search_params, overrides)
    keywords = _keyword_sequence(effective_params, include_adjacent_keywords)

    aggregate_jobs = []
    errors = []
    keywords_used = []
    rate_limited = False

    for keyword in keywords:
        run_params = dict(effective_params)
        run_params["keyword"] = keyword
        run_params.pop("adjacentKeywords", None)

        worker_result = _run_linkedin_search(run_params)
        result_jobs = worker_result.get("jobs", []) or []
        if result_jobs:
            keywords_used.append(keyword)
            for job in result_jobs:
                if isinstance(job, dict):
                    job["search_keyword"] = keyword
                    aggregate_jobs.append(job)

        if worker_result.get("error"):
            err_msg = worker_result["error"]
            errors.append(f"{keyword}: {err_msg}")
            if "rate limit" in err_msg.lower() or "429" in err_msg:
                rate_limited = True

        deduped_preview = _dedupe_jobs(aggregate_jobs)
        filtered_preview = _score_and_filter_jobs(
            deduped_preview,
            resume,
            effective_params,
            explicit_location=explicit_location,
            min_score=MIN_BALANCED_MATCH_SCORE,
        )
        if len(filtered_preview) >= effective_params.get("limit", DEFAULT_QUERY_LIMIT):
            break

    deduped_jobs = _dedupe_jobs(aggregate_jobs)
    filtered_jobs = _score_and_filter_jobs(
        deduped_jobs,
        resume,
        effective_params,
        explicit_location=explicit_location,
        min_score=MIN_BALANCED_MATCH_SCORE,
    )
    jobs = filtered_jobs[: effective_params.get("limit", DEFAULT_QUERY_LIMIT)]
    error = " | ".join(errors[:2]) if errors else None

    metadata = {
        "total_fetched": len(aggregate_jobs),
        "total_after_filter": len(jobs),
        "keywords_used": keywords_used,
        "filter_mode": "balanced",
        "filter_warning": "No relevant jobs after filtering." if aggregate_jobs and not jobs else "",
        "rate_limit_warning": "LinkedIn is rate-limiting requests. Results may be incomplete. Try again in a few minutes." if rate_limited else "",
    }

    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(minutes=CACHE_TTL_MINUTES)
    if persist_cache:
        cache = db.query(models.LinkedInCache).filter(models.LinkedInCache.user_id == user_id).first()
        stored_params = dict(effective_params)
        stored_params["include_adjacent_keywords"] = include_adjacent_keywords
        stored_params["_meta"] = metadata

        if cache:
            cache.results_json = json.dumps(jobs)
            cache.search_params_json = json.dumps(stored_params)
            cache.cached_at = now
            cache.expires_at = expires_at
        else:
            cache = models.LinkedInCache(
                user_id=user_id,
                results_json=json.dumps(jobs),
                search_params_json=json.dumps(stored_params),
                cached_at=now,
                expires_at=expires_at,
            )
            db.add(cache)
        db.commit()
        db.refresh(cache)

    return {
        "jobs": jobs,
        "search_params": {
            **effective_params,
            "include_adjacent_keywords": include_adjacent_keywords,
        },
        "cached_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "from_cache": False,
        "total_fetched": metadata["total_fetched"],
        "total_after_filter": metadata["total_after_filter"],
        "keywords_used": metadata["keywords_used"],
        "filter_mode": metadata["filter_mode"],
        **({"filter_warning": metadata["filter_warning"]} if metadata["filter_warning"] else {}),
        **({"rate_limit_warning": metadata["rate_limit_warning"]} if metadata["rate_limit_warning"] else {}),
        **({"error": error} if error else {}),
    }


@router.get("/linkedin-recommendations", tags=["LinkedIn"])
def get_linkedin_recommendations(
    user_id: int,
    keyword: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    experience_level: Optional[str] = Query(default=None, alias="experienceLevel"),
    job_type: Optional[str] = Query(default=None, alias="jobType"),
    remote_filter: Optional[str] = Query(default=None, alias="remoteFilter"),
    limit: Optional[int] = Query(default=None),
    include_adjacent_keywords: Optional[bool] = Query(default=True),
    db=Depends(get_db),
):
    """
    Returns LinkedIn job recommendations for the authenticated applicant based on their active resume.
    Results are cached per user for 60 minutes. Pass ?user_id=<id>.
    """
    user = get_user_or_404(db, user_id)
    if user.role != "applicant":
        raise HTTPException(status_code=403, detail="Only applicants can access LinkedIn recommendations.")

    overrides = _collect_overrides(
        keyword=keyword,
        location=location,
        experience_level=experience_level,
        job_type=job_type,
        remote_filter=remote_filter,
        limit=limit,
        include_adjacent_keywords=include_adjacent_keywords,
        payload=None,
    )
    has_overrides = _has_meaningful_overrides(overrides)

    now = datetime.now(tz=timezone.utc)
    cache = db.query(models.LinkedInCache).filter(models.LinkedInCache.user_id == user_id).first()

    cache_expires = cache.expires_at if (cache and cache.expires_at and cache.expires_at.tzinfo) else (cache.expires_at.replace(tzinfo=timezone.utc) if (cache and cache.expires_at) else None)
    if (not has_overrides) and cache and cache_expires and cache_expires > now:
        return _build_response(cache)

    return _fetch_and_cache(user_id, db, overrides=overrides, persist_cache=not has_overrides)


@router.post("/linkedin-recommendations/refresh", tags=["LinkedIn"])
def refresh_linkedin_recommendations(
    user_id: int,
    keyword: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    experience_level: Optional[str] = Query(default=None, alias="experienceLevel"),
    job_type: Optional[str] = Query(default=None, alias="jobType"),
    remote_filter: Optional[str] = Query(default=None, alias="remoteFilter"),
    limit: Optional[int] = Query(default=None),
    include_adjacent_keywords: Optional[bool] = Query(default=True),
    payload: Optional[schemas.LinkedInSearchOverrides] = Body(default=None),
    db=Depends(get_db),
):
    """
    Force-refreshes LinkedIn job recommendations by clearing the cache and fetching new results.
    """
    user = get_user_or_404(db, user_id)
    if user.role != "applicant":
        raise HTTPException(status_code=403, detail="Only applicants can access LinkedIn recommendations.")

    overrides = _collect_overrides(
        keyword=keyword,
        location=location,
        experience_level=experience_level,
        job_type=job_type,
        remote_filter=remote_filter,
        limit=limit,
        include_adjacent_keywords=include_adjacent_keywords,
        payload=payload,
    )
    has_overrides = _has_meaningful_overrides(overrides)

    if not has_overrides:
        cache = db.query(models.LinkedInCache).filter(models.LinkedInCache.user_id == user_id).first()
        if cache:
            db.delete(cache)
            db.commit()

    return _fetch_and_cache(user_id, db, overrides=overrides, persist_cache=not has_overrides)
