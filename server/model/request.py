from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class RunPOC(BaseModel):
    nl_prompt: str
    input_files: list[str]
