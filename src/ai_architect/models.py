import re
from pydantic import BaseModel, Field, field_validator


class ClarifyQuestion(BaseModel):
    id: str
    label: str
    question: str
    hint: str = ""
    options: list[str] = Field(default_factory=list)
    allow_custom: bool = True

    @field_validator("id", mode="before")
    @classmethod
    def slugify_id(cls, v):
        return re.sub(r"[^a-z0-9_]", "_", str(v).lower().strip())

    @field_validator("options", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v or []


class ClarifyDecision(BaseModel):
    needs_clarification: bool = False
    questions: list[ClarifyQuestion] = Field(default_factory=list)


class ClarifyRequest(BaseModel):
    product_idea: str


class ClarifyResponse(BaseModel):
    needs_clarification: bool
    questions: list[ClarifyQuestion]


class GenerateRequest(BaseModel):
    product_idea: str
    answers: dict[str, str] = Field(default_factory=dict)
    questions: list[dict] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    requirements: str
    architecture: str
