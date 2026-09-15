from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class RunPOC(BaseModel):
    nl_prompt: str
    run_id: str


@dataclass
class PresignRequest(BaseModel):
    file_names: list[str]
