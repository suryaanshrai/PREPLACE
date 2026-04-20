import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

import models
from utils import get_linkedin_search_params
from .common import get_db, get_latest_resume, get_user_or_404

router = APIRouter()

CACHE_TTL_MINUTES = 60
LINKEDIN_WORKER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "linkedin_worker")


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
    return {
        "jobs": jobs,
        "search_params": search_params,
        "cached_at": cache.cached_at.isoformat() if cache.cached_at else None,
        "expires_at": cache.expires_at.isoformat() if cache.expires_at else None,
        "from_cache": True,
    }


def _fetch_and_cache(user_id: int, db) -> dict:
    """Get active resume → Gemini → Node subprocess → upsert cache → return result."""
    resume = get_latest_resume(db, user_id)
    if not resume:
        raise HTTPException(status_code=404, detail="No resume found. Upload a resume first.")

    search_params = get_linkedin_search_params(
        resume_text=resume.parsed_text or "",
        analysis_text=resume.analysis or "",
    )

    worker_result = _run_linkedin_search(search_params)
    jobs = worker_result.get("jobs", [])
    error = worker_result.get("error")

    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(minutes=CACHE_TTL_MINUTES)

    cache = db.query(models.LinkedInCache).filter(models.LinkedInCache.user_id == user_id).first()
    if cache:
        cache.results_json = json.dumps(jobs)
        cache.search_params_json = json.dumps(search_params)
        cache.cached_at = now
        cache.expires_at = expires_at
    else:
        cache = models.LinkedInCache(
            user_id=user_id,
            results_json=json.dumps(jobs),
            search_params_json=json.dumps(search_params),
            cached_at=now,
            expires_at=expires_at,
        )
        db.add(cache)
    db.commit()
    db.refresh(cache)

    return {
        "jobs": jobs,
        "search_params": search_params,
        "cached_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "from_cache": False,
        **({"error": error} if error else {}),
    }


@router.get("/linkedin-recommendations", tags=["LinkedIn"])
def get_linkedin_recommendations(user_id: int, db=Depends(get_db)):
    """
    Returns LinkedIn job recommendations for the authenticated applicant based on their active resume.
    Results are cached per user for 60 minutes. Pass ?user_id=<id>.
    """
    user = get_user_or_404(db, user_id)
    if user.role != "applicant":
        raise HTTPException(status_code=403, detail="Only applicants can access LinkedIn recommendations.")

    now = datetime.now(tz=timezone.utc)
    cache = db.query(models.LinkedInCache).filter(models.LinkedInCache.user_id == user_id).first()

    if cache and cache.expires_at and cache.expires_at.replace(tzinfo=timezone.utc) > now:
        return _build_response(cache)

    return _fetch_and_cache(user_id, db)


@router.post("/linkedin-recommendations/refresh", tags=["LinkedIn"])
def refresh_linkedin_recommendations(user_id: int, db=Depends(get_db)):
    """
    Force-refreshes LinkedIn job recommendations by clearing the cache and fetching new results.
    """
    user = get_user_or_404(db, user_id)
    if user.role != "applicant":
        raise HTTPException(status_code=403, detail="Only applicants can access LinkedIn recommendations.")

    cache = db.query(models.LinkedInCache).filter(models.LinkedInCache.user_id == user_id).first()
    if cache:
        db.delete(cache)
        db.commit()

    return _fetch_and_cache(user_id, db)
