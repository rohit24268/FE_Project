from pydantic import BaseModel


class ChatTurn(BaseModel):
    role: str
    content: str


class InvestigateRequest(BaseModel):
    analysis_id: str
    question: str
    history: list[ChatTurn] = []
