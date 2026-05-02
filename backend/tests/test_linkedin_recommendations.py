from types import SimpleNamespace

from routers.linkedin import (
    _dedupe_jobs,
    _has_meaningful_overrides,
    _keyword_sequence,
    _merge_search_params,
    _normalize_search_params,
    _score_and_filter_jobs,
)


def test_normalize_search_params_clamps_and_sanitizes():
    out = _normalize_search_params(
        {
            "keyword": "  Backend Developer  ",
            "location": "  Bengaluru ",
            "experienceLevel": "Senior",
            "jobType": "Contract",
            "remoteFilter": "on site",
            "limit": 999,
            "adjacentKeywords": ["Backend Engineer", "backend engineer", "Python Developer"],
        }
    )

    assert out["keyword"] == "Backend Developer"
    assert out["location"] == "Bengaluru"
    assert out["experienceLevel"] == "senior"
    assert out["jobType"] == "contract"
    assert out["remoteFilter"] == "on-site"
    assert out["limit"] == 25
    assert out["adjacentKeywords"] == ["Backend Engineer", "Python Developer"]


def test_merge_search_params_and_override_flags():
    base = {
        "keyword": "Backend Developer",
        "location": "",
        "experienceLevel": "entry level",
        "jobType": "",
        "remoteFilter": "",
        "limit": 10,
        "adjacentKeywords": ["Backend Engineer", "Python Developer"],
    }

    merged, explicit_location, include_adjacent = _merge_search_params(
        base,
        {
            "location": "Delhi",
            "limit": 5,
            "include_adjacent_keywords": False,
        },
    )

    assert merged["location"] == "Delhi"
    assert merged["limit"] == 5
    assert merged["adjacentKeywords"] == []
    assert explicit_location is True
    assert include_adjacent is False


def test_keyword_sequence_primary_then_adjacent():
    params = {
        "keyword": "Backend Developer",
        "adjacentKeywords": ["Backend Engineer", "Python Developer"],
    }
    with_adjacent = _keyword_sequence(params, include_adjacent_keywords=True)
    primary_only = _keyword_sequence(params, include_adjacent_keywords=False)

    assert with_adjacent == ["Backend Developer", "Backend Engineer", "Python Developer"]
    assert primary_only == ["Backend Developer"]


def test_dedupe_jobs_uses_url_or_metadata_key():
    jobs = [
        {"jobUrl": "https://linkedin.com/jobs/1", "position": "Backend Engineer", "company": "A"},
        {"jobUrl": "https://linkedin.com/jobs/1", "position": "Backend Engineer", "company": "A"},
        {"position": "Backend Engineer", "company": "A", "location": "Remote"},
        {"position": "Backend Engineer", "company": "A", "location": "Remote"},
    ]

    deduped = _dedupe_jobs(jobs)
    assert len(deduped) == 2


def test_score_and_filter_jobs_balanced_filters_irrelevant_and_respects_location_toggle():
    resume = SimpleNamespace(
        suggested_role="Backend Developer",
        score=88,
        analysis="Strong with Python, FastAPI, PostgreSQL, Docker",
    )
    jobs = [
        {
            "position": "Backend Engineer",
            "company": "Acme",
            "location": "Delhi",
            "description": "Build APIs with Python and FastAPI",
            "jobUrl": "https://linkedin.com/jobs/100",
        },
        {
            "position": "Social Media Manager",
            "company": "BrandX",
            "location": "Delhi",
            "description": "Marketing strategy and social growth",
            "jobUrl": "https://linkedin.com/jobs/200",
        },
        {
            "position": "Backend Engineer",
            "company": "RemoteCo",
            "location": "New York",
            "description": "Python backend services",
            "jobUrl": "https://linkedin.com/jobs/300",
        },
    ]

    search_params = {"location": "Delhi"}

    strict_location = _score_and_filter_jobs(
        jobs,
        resume,
        search_params,
        explicit_location=True,
    )
    assert len(strict_location) == 1
    assert strict_location[0]["position"] == "Backend Engineer"

    relaxed_location = _score_and_filter_jobs(
        jobs,
        resume,
        search_params,
        explicit_location=False,
    )
    assert len(relaxed_location) == 2
    assert all(item["position"] == "Backend Engineer" for item in relaxed_location)


def test_has_meaningful_overrides_behavior():
    assert _has_meaningful_overrides({}) is False
    assert _has_meaningful_overrides({"keyword": "   "}) is False
    assert _has_meaningful_overrides({"include_adjacent_keywords": False}) is True
    assert _has_meaningful_overrides({"keyword": "Backend Engineer"}) is True
