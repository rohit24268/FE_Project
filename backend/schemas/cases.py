from typing import Optional
from pydantic import BaseModel, model_validator


class CreateCaseRequest(BaseModel):
    title: Optional[str] = None
    case_name: Optional[str] = None
    description: str = ""
    investigator: str = ""
    status: str = "open"

    @model_validator(mode="after")
    def validate_title(self):
        val = (self.title or self.case_name or "").strip()
        if not val:
            raise ValueError("title or case_name cannot be empty")
        self.title = val
        self.case_name = val
        return self


class UpdateCaseRequest(BaseModel):
    description: Optional[str] = None
    investigator: Optional[str] = None
