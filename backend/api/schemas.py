from typing import Literal
from pydantic import BaseModel

class SearchJobsRequest(BaseModel):
    query: str
    max_jobs: int = 5
    strategy: str = "keyword_injection"


class ReviewDecisionRequest(BaseModel):
    job_id: str
    decision: Literal["proceed", "skip"]


class UserDataRequest(BaseModel):
    full_name: str
    first_name: str
    last_name: str
    email: str
    phone: str
    linkedin_url: str
    github_url: str | None = None
