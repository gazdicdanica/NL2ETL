import json
from fastapi import FastAPI
from .model.request import RunPOC
from pathlib import Path

from .utils import infer_schema, generate_plan, generate_code

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/")
def run_poc(run_poc: RunPOC) -> dict:

    schemas = [infer_schema(f) for f in run_poc.input_files]
    print(f"Schemas inferred: {[s['filename'] for s in schemas]}")

    plan = generate_plan(run_poc.nl_prompt, schemas)
    print(f"Pipeline plan:\n{json.dumps(plan, indent=2)}")

    if plan.get("ambiguities"):
        print(f"\nAmbiguities detected: {plan['ambiguities']}")
        return  # In full system: show UI disambiguation prompt

    code = generate_code(plan, schemas)
    print(f"\nGenerated code:\n{code}")

    scripts_dir = (Path(__file__).parent / "../output").resolve()
    file_path = scripts_dir / "test.py"

    file_path.write_text(code, encoding="utf-8")

    print(f"Saved script to: {file_path}")

    return {"message": "Success"}
