import json
import os
from fastapi import FastAPI, Response

from .execution_utils import execute_in_docker
from .model.request import RunPOC
from pathlib import Path

from .llm_utils import infer_schema, generate_plan, generate_code

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/", status_code=200)
def run_poc(run_poc: RunPOC, response: Response) -> dict:

    schemas = [infer_schema(f) for f in run_poc.input_files]
    print(f"Schemas inferred: {[s['filename'] for s in schemas]}")

    plan = generate_plan(run_poc.nl_prompt, schemas)
    print(f"Pipeline plan:\n{json.dumps(plan, indent=2)}")

    if plan.get("ambiguities"):
        print(f"\nAmbiguities detected: {plan['ambiguities']}")
        return  # In full system: show UI disambiguation prompt

    code = generate_code(plan, schemas)
    print(f"\nGenerated code:\n{code}")

    success, stdout, stderr = execute_in_docker(code, run_poc.input_files)

    if success:
        print(f"\nExecution succeeded. Output files:\n{stdout}")
        response.status_code = 200
        return {"message": "Success", "output_files": stdout.splitlines()}
    else:
        print(f"\nExecution failed with error:\n{stderr}")
        response.status_code = 500
        return {"message": "Execution failed", "error": stderr}
