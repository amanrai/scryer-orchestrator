from pydantic import BaseModel


class HookSummary(BaseModel):
    name: str


class HookDetail(BaseModel):
    name: str
    content: str


class HookCreate(BaseModel):
    name: str
    content: str = ""


class HookUpdate(BaseModel):
    content: str
