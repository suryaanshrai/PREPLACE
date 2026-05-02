from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(..., min_length=8)
    # role is intentionally not exposed — /register always creates applicants.
    # Kept for backwards-compat with clients that send it; the router ignores it.
    role: str = "applicant"

class UserLogin(BaseModel): 
    email: str
    password: str

class RecruiterRegister(BaseModel):
    name: str           # recruiter's name
    email: EmailStr
    password: str = Field(..., min_length=8)
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
    action: Literal["apply", "save"] = "apply"
    resume_id: Optional[int] = None


class ApplicationStatusUpdate(BaseModel):
    status: str


class RecruiterNoteUpdate(BaseModel):
    recruiter_note: str = Field(..., max_length=1000)


class PenaltyRuleIn(BaseModel):
    category: str
    label: str
    keywords: List[str]
    penalty_value: int
    is_active: bool = True


class PenaltyRulesUpsert(BaseModel):
    rules: List[PenaltyRuleIn]


class ScoringTemplateCreate(BaseModel):
    title: str
    role_title: str
    description: str = ""
    category: str = "General"
    is_active: bool = True


class ScoringTemplateUpdate(BaseModel):
    title: Optional[str] = None
    role_title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class ResumeInsightsRequest(BaseModel):
    resume_id: int
    role_mode: str = "general"  # general | targeted
    target_role: str = ""


class ResumeInsightSection(BaseModel):
    title: str
    summary: str = ""
    insights: List[str] = Field(default_factory=list)
    actionable_steps: List[str] = Field(default_factory=list)


class ResumeInsightAction(BaseModel):
    priority: str  # high | medium | low
    step: str
    why_it_matters: str = ""
    timeframe: str = ""


class ResumeInsightsResponse(BaseModel):
    resume_id: int
    role_mode: str
    target_role: str
    suggested_role: str = ""
    headline: str
    sections: List[ResumeInsightSection]
    action_plan: List[ResumeInsightAction]
    source: str = "llm"
    note: str = ""
    generated_at: datetime


class LinkedInSearchOverrides(BaseModel):
    keyword: Optional[str] = None
    location: Optional[str] = None
    experienceLevel: Optional[str] = None
    jobType: Optional[str] = None
    remoteFilter: Optional[str] = None
    limit: Optional[int] = Field(default=None, ge=1, le=25)
    include_adjacent_keywords: Optional[bool] = True
    adjacentKeywords: Optional[List[str]] = None