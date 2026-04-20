from .auth import router as auth_router
from .resumes import router as resumes_router
from .jobs import router as jobs_router
from .applications import router as applications_router
from .admin import router as admin_router
from .linkedin import router as linkedin_router

__all__ = [
    "auth_router",
    "resumes_router",
    "jobs_router",
    "applications_router",
    "admin_router",
    "linkedin_router",
]
