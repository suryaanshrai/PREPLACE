# PREPLACE

PREPLACE is a role-based hiring platform with applicant resume analysis, recruiter job workflows, and admin moderation.

## What Was Added

- Recruiter job posting lifecycle with markdown descriptions and edit/delete controls.
- Resume management improvements: validation, active resume selection, delete support.
- Hybrid matching (rule-based + vector similarity via ChromaDB + sentence-transformers).
- Candidate application workflow: save/apply/withdraw + status timeline.
- Recruiter pipeline controls: update candidate status and add recruiter notes.
- Search/filter/sort support for job and applicant workflows.

## Local Setup

### Backend

1. Create environment file:
   - Copy `backend/.env.example` to `backend/.env`.
2. Install dependencies:
   - `pip install -r backend/requirements.txt`
3. Start API:
   - `uvicorn main:app --reload` (run from `backend/`)

### Frontend

1. Install dependencies:
   - `npm install` (run from `frontend/`)
2. Start app:
   - `npm run dev`

## Git Workflow Convention

- Branch naming:
  - `feature/<short-topic>`
  - `fix/<short-topic>`
  - `chore/<short-topic>`
- Commit format:
  - `feat: ...`
  - `fix: ...`
  - `chore: ...`
  - `test: ...`

Example:
- `feature/hybrid-matching`
- `feat: add hybrid vector + rule matching endpoints`

## Notes

- If ChromaDB or sentence-transformers is unavailable, matching falls back to rule-based ranking.
- Existing DBs are updated with additive schema SQL on startup for smoother local migration.
