from pydantic import BaseModel
from typing import Optional, List

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "applicant"

class UserLogin(BaseModel): 
    email: str
    password: str

class RecruiterRegister(BaseModel):
    name: str           # recruiter's name
    email: str
    password: str
    company_name: str
    roles_hiring: str = ""

class JobListingCreate(BaseModel):
    role_title: str
    department: str = ""
    job_type: str = "Internship"
    location: str = ""
    ctc: str = ""
    description: str = ""
    skills: str = ""          # comma-separated
    min_cgpa: float = 0
    min_score: int = 0
    experience: str = "Fresher (0 years)"


class JobListingUpdate(BaseModel):
    role_title: Optional[str] = None
    department: Optional[str] = None
    job_type: Optional[str] = None
    location: Optional[str] = None
    ctc: Optional[str] = None
    description: Optional[str] = None
    skills: Optional[str] = None
    min_cgpa: Optional[float] = None
    min_score: Optional[int] = None
    experience: Optional[str] = None


class ApplicationCreate(BaseModel):
    job_listing_id: int
    action: str = "apply"  # apply | save


class ApplicationStatusUpdate(BaseModel):
    status: str


class RecruiterNoteUpdate(BaseModel):
    recruiter_note: str