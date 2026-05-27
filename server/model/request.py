from pydantic import BaseModel


class RunPOC(BaseModel):
    nl_prompt: str
    input_files: list[str]
