from pydantic import BaseModel


class CreateCaseRequest(BaseModel):
    title: str
    description: str = ""
    investigator: str = ""
    status: str = "open"


class LinkAnalysisRequest(BaseModel):
    analysis_id: str
